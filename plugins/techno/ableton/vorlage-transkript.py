"""Transkribiert eine Vorlage aus Demucs-Stems: Taktraster, Treffer je 16tel und Element, Pegel je Stem und Takt.

Aufruf: python vorlage-transkript.py <stem-ordner> --bpm 144.07 [--mix <original.wav>] [--out transkript.json]
Der Stem-Ordner enthaelt drums/bass/other/vocals.wav (htdemucs). Elemente werden ueber Frequenzbaender des
Drum-Stems getrennt; das ist eine Naeherung, deshalb stehen Pegel je Treffer im Ergebnis, nicht nur 0/1.
"""
import argparse, json, subprocess
import numpy as np
from scipy.signal import butter, sosfiltfilt

SR = 22050
# Band, Fenster fuer den Anstieg (ms): Kick tief und kurz, Hats hoch; Rumble = Dauerpegel zwischen den Kicks
ELEMENTE = {
    'kick': (35, 110),
    'clap': (1200, 3500),
    'hat': (8000, 11000),
    'perc': (300, 900),
}


def lade(pfad):
    roh = subprocess.run(['ffmpeg', '-v', 'error', '-i', pfad, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(roh, dtype=np.float32).astype(np.float64)


def band(x, lo, hi):
    sos = butter(4, [lo, min(hi, SR / 2 - 100)], btype='band', fs=SR, output='sos')
    return sosfiltfilt(sos, x)


def huelle(x, ms=5):
    n = max(1, int(SR * ms / 1000))
    return np.sqrt(np.convolve(x * x, np.ones(n) / n, mode='same'))


def db(v):
    return 20 * np.log10(np.maximum(v, 1e-9))


def einsaetze(env):
    # Kick-Einsaetze: Spitzen der positiven Huellen-Ableitung, mind. 200 ms Abstand
    from scipy.signal import find_peaks
    d = np.maximum(np.diff(env, prepend=env[0]), 0)
    p, _ = find_peaks(d, height=np.percentile(d, 99.5) * 0.3, distance=int(SR * 0.2))
    return p / SR


def tempo_schaetzen(zeiten, bpm, spanne=1.0):
    # Phasen-Kohaerenz der Einsaetze gegen das Viertelraster; Maximum = Tempo, das ueber den ganzen Track haelt
    best = (0, bpm)
    for b in np.arange(bpm - spanne, bpm + spanne, 0.0005):
        k = abs(np.mean(np.exp(2j * np.pi * zeiten * b / 60)))
        if k > best[0]:
            best = (k, b)
    return round(best[1], 4), round(best[0], 3)


def raster_start(drums, bpm):
    # Kick-Anschlag, nicht Kick-Gipfel: bei langem Pitch-Sweep liegt der Tiefton-Gipfel bis 60 ms hinter dem Anschlag.
    # Gefaltete 100-400-Hz-Huelle (Sweep-Beginn plus Klick), vom Gipfel rueckwaerts bis 10 % ueber dem Tal davor.
    # Anker = steilster Anstieg im Kick-Band (40-250 Hz, 10 ms); Rumble im 100-400-Band zog den Start sonst bis 1/16 zu frueh.
    beat = SR * 60 / bpm
    n = int(len(drums) / beat) - 1
    lang = int(beat)
    falte = lambda e: np.mean([e[int(k * beat):int(k * beat) + lang] for k in range(n)], 0)
    k_env = huelle(band(drums, 40, 250), 10)
    anker = int(np.argmax(falte(np.maximum(np.diff(k_env, prepend=k_env[0]), 0)))) + lang
    f2 = np.tile(falte(huelle(band(drums, 100, 400), 1)), 3)
    p = anker + int(np.argmax(f2[anker:anker + int(SR * .03)]))
    vor = int(SR * .04)
    fenster = f2[p - vor:p + 1]
    tal = int(np.argmin(fenster))
    schwelle = fenster[tal] + 0.1 * (fenster[-1] - fenster[tal])
    anschlag = tal + int(np.argmax(fenster[tal:] >= schwelle))
    s = ((p - vor + anschlag) % lang) / SR
    # Anschlag knapp vor Dateibeginn (Export ab Takt 1) landet am Beat-Ende
    return max(0.0, s - lang / SR) if s > lang / SR - 0.01 else s


def _selbsttest():
    # Kick mit Sweep 220 -> 50 Hz alle 0,4167 s ab 0,1 s plus Rumble zwischen den Kicks: Start auf 2 ms genau
    t = np.arange(int(SR * .5)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(50 + 170 * np.exp(-t / .03)) / SR) * np.exp(-t / .25)
    x = np.zeros(SR * 20)
    for k in range(45):
        a = int(SR * (0.1 + k * 60 / 144))
        x[a:a + len(kick)] += kick[:len(x) - a]
        r, n = a + int(SR * .2), int(SR * .15)
        x[r:r + n] += 0.5 * np.sin(2 * np.pi * 49 * np.arange(n) / SR) * np.hanning(n)
    s = raster_start(x, 144)
    assert abs(s - 0.1) < 0.002, s


def treffer(env, t0, bpm, schritte):
    # Anschlagstaerke je 16tel: groesste positive Huellen-Ableitung in [t-15ms, t+25ms]; robust gegen Dauerpegel (Rumble)
    sech = 60 / bpm / 4
    d = np.maximum(np.diff(env, prepend=env[0]), 0)
    d = np.convolve(d, np.ones(int(SR * .002)), mode='same')
    st = []
    for i in range(schritte):
        t = int((t0 + i * sech) * SR)
        w = d[max(0, t - int(SR * .015)):t + int(SR * .025)]
        st.append(db(w.max()) if len(w) else -200)
    st = np.array(st)
    return st - np.percentile(st, 99)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stems')
    ap.add_argument('--bpm', type=float, required=True)
    ap.add_argument('--out', default=None)
    ap.add_argument('--schwelle-db', type=float, default=30.0, help='Treffer bis so viel dB unter dem staerksten Anschlag')
    a = ap.parse_args()
    st = {n: lade(f'{a.stems}/{n}.wav') for n in ('drums', 'bass', 'other', 'vocals')}
    dr = st['drums']
    envs = {k: huelle(band(dr, lo, hi)) for k, (lo, hi) in ELEMENTE.items()}
    a.bpm, koh = tempo_schaetzen(einsaetze(envs['kick']), a.bpm)
    print(f'Tempo {a.bpm} BPM (Kohaerenz {koh})')
    t0 = raster_start(dr, a.bpm)
    takt_s = 60 / a.bpm * 4
    takte = int((len(dr) / SR - t0) / takt_s)
    schritte = takte * 16
    aus = {'bpm': a.bpm, 'start_s': round(t0, 4), 'takte': takte, 'elemente': {}, 'stems_db': {}, 'rumble_db': []}
    for k, env in envs.items():
        staerke = treffer(env, t0, a.bpm, schritte)
        pegel = [round(float(v), 1) if v > -a.schwelle_db else None for v in staerke]
        aus['elemente'][k] = [pegel[i * 16:(i + 1) * 16] for i in range(takte)]
    # Rumble: Tiefton-Pegel auf den 16teln zwischen den Kicks (Mitte des 16tels)
    tief = huelle(band(dr, 35, 100), 20)
    sech = 60 / a.bpm / 4
    rum = [db(tief[int((t0 + (i + 0.5) * sech) * SR)]) for i in range(schritte)]
    ref = max(rum)
    aus['rumble_db'] = [[round(rum[i * 16 + j] - ref, 1) for j in range(16)] for i in range(takte)]
    for n, x in st.items():
        e = []
        for i in range(takte):
            s = x[int((t0 + i * takt_s) * SR):int((t0 + (i + 1) * takt_s) * SR)]
            e.append(round(float(db(np.sqrt(np.mean(s * s)) + 1e-12)), 1))
        aus['stems_db'][n] = e
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            json.dump(aus, f)
    print(f"Start {aus['start_s']} s, {takte} Takte")
    for n, e in aus['stems_db'].items():
        print(f"{n:7} je 8 Takte:", ' '.join(f'{np.mean(e[i:i + 8]):6.1f}' for i in range(0, takte, 8)))


if __name__ == '__main__':
    _selbsttest()
    main()
