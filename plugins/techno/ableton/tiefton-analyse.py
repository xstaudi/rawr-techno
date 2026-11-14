# Vermisst Kick und Bass eines Tracks (am besten Demucs-Stems: drums.wav fuer die Kick, bass.wav fuer den Bass).
# Aufruf: python -I tiefton-analyse.py --bpm 144 --drums drums.wav --bass bass.wav [--von 60 --bis 180] [--kick-wav aus.wav]
# Ausgabe: JSON mit Kick-Pitchkurve (Start-/Endfrequenz, Zeitkonstante), Ausklingzeiten und Bass-Raster je 16tel.
import argparse, json, subprocess, sys
import numpy as np
from scipy.signal import butter, sosfiltfilt, find_peaks, hilbert
from scipy.optimize import curve_fit

SR = 44100
NOTEN = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def lesen(pfad, von, bis):
    cmd = ['ffmpeg', '-v', 'error', '-ss', str(von), '-to', str(bis), '-i', pfad, '-vn', '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-']
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, dtype=np.float32).astype(float)


def tiefpass(x, hz):
    return sosfiltfilt(butter(4, hz, 'lowpass', fs=SR, output='sos'), x)


def note(hz):
    m = 69 + 12 * np.log2(hz / 440)
    return f'{NOTEN[int(round(m)) % 12]}{int(round(m)) // 12 - 1} ({m - round(m):+.2f})'


def db(v):
    return float(20 * np.log10(max(v, 1e-9)))


def kick_onsets(x, bpm):
    env = np.abs(hilbert(tiefpass(x, 150)))
    d = np.maximum(np.diff(np.convolve(env, np.ones(64) / 64, 'same')), 0)
    pk, _ = find_peaks(d, distance=int(0.8 * 60 / bpm * SR), height=np.percentile(d, 99.5) * 0.3)
    return pk


def kick_mittel(x, pk, dauer=0.35):
    n = int(dauer * SR)
    hits = [x[p - 64:p - 64 + n] for p in pk if p > 64 and p - 64 + n < len(x)]
    # Median statt Mittel: Hats/Claps auf einzelnen Schlaegen fallen heraus.
    return np.median(np.array(hits), axis=0), len(hits)


def pitchkurve(k):
    lp = tiefpass(k, 400)
    z = np.where((lp[:-1] < 0) & (lp[1:] >= 0))[0]
    z = z + (-lp[z] / (lp[z + 1] - lp[z]))  # lineare Interpolation des Nulldurchgangs
    beginn = np.argmax(np.abs(k) > 0.05 * np.max(np.abs(k)))
    t, f = ((z[1:] + z[:-1]) / 2 - beginn) / SR, SR / np.diff(z)
    # Die ersten 2 ms verzerrt der Filter-Einschwingvorgang, sie verfaelschen sonst den Fit.
    ok = (f > 25) & (f < 400) & (t > 0.002)
    return t[ok], f[ok]


def huelle_abfall(k):
    env = np.convolve(np.abs(hilbert(tiefpass(k, 200))), np.ones(220) / 220, 'same')
    spitze = int(np.argmax(env))
    werte = {}
    for grenze in (6, 20, 40):
        unter = np.where(env[spitze:] < env[spitze] * 10 ** (-grenze / 20))[0]
        werte[f'abfall_{grenze}db_ms'] = round(float(unter[0]) / SR * 1000, 1) if len(unter) else None
    return werte


def kick_werte(k):
    t_voll, f_voll = pitchkurve(k)
    abfall = huelle_abfall(k)
    # Nach dem Kick-Koerper zaehlen Hats und Rauschen als Tonhoehe (Demucs-Drums enden oft nach 70 ms); nur bis -20 dB fitten
    koerper = t_voll < (abfall['abfall_20db_ms'] or 150) / 1000
    t, f = (t_voll[koerper], f_voll[koerper]) if koerper.sum() >= 4 else (t_voll, f_voll)
    werte = {}
    try:
        if len(f) < 4:
            raise RuntimeError
        modell = lambda t, fs, fe, tau: fe + (fs - fe) * np.exp(-t / tau)
        # Grenzen: ohne sie lief der Fit bei Kicks ohne Sweep auf negative Endfrequenz (NaN-Note, 6 Tracks der Sammlung).
        # Startwerte aus der Kurve: feste 150/50 Hz kippten bei trockenen Kicks ins falsche Minimum (Ende 400 Hz)
        p0 = [min(f[0], 999), min(np.median(f[-5:]), 399), 0.015]
        (fs, fe, tau), _ = curve_fit(modell, t, f, p0=p0, bounds=([20, 20, 1e-4], [1000, 400, 2]), maxfev=20000)
        if fe < 21 or fe > 399 or tau > 1.9:  # Fit klebt an der Grenze: kein Messwert
            raise RuntimeError
        werte.update(f_start_hz=round(float(fs), 1), f_end_hz=round(float(fe), 1), f_end_note=note(fe), pitch_tau_ms=round(float(tau) * 1000, 1))
    except RuntimeError:
        werte['pitch_fit'] = 'fehlgeschlagen'
    # leere Tonhoehenkurve (Kick ohne erkennbaren Grundton im Demucs-Stem): fehlender Messwert statt Absturz der Pruefung
    if len(t_voll):
        werte['f_bei_ms'] = {ms: round(float(np.interp(ms / 1000, t_voll, f_voll)), 1) for ms in (5, 10, 20, 40, 80, 150)}
    werte.update(abfall)
    spek = np.abs(np.fft.rfft(k * np.hanning(len(k))))
    fq = np.fft.rfftfreq(len(k), 1 / SR)
    band = lambda lo, hi: float(np.sum(spek[(fq >= lo) & (fq < hi)] ** 2))
    gesamt = band(20, 16000)
    werte['energie_anteil'] = {b: round(band(*r) / gesamt, 3) for b, r in
                              {'20-60': (20, 60), '60-120': (60, 120), '120-300': (120, 300), '300-2k': (300, 2000), '2k-16k': (2000, 16000)}.items()}
    werte['spitze_dbfs'] = round(db(np.max(np.abs(k))), 1)
    return werte


def bass_raster(b, bpm, start):
    # start: Sample des ersten Kick-Schlags; Raster 16 Sechzehntel je Takt, gemittelt ueber alle Takte
    s16 = 60 / bpm / 4 * SR
    lp = tiefpass(b, 250)
    env = np.convolve(np.abs(hilbert(lp)), np.ones(220) / 220, 'same')
    takte = int((len(b) - start) / (16 * s16)) - 1
    pegel, tonhoehe = np.zeros(16), [[] for _ in range(16)]
    for t in range(takte):
        for i in range(16):
            a = int(start + (t * 16 + i) * s16)
            pegel[i] += env[a:a + int(s16)].max()
            seg = lp[a + int(0.1 * s16):a + int(s16)]
            if len(seg) > 256:
                spek = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 16 * len(seg)))
                fq = np.fft.rfftfreq(16 * len(seg), 1 / SR)
                sel = (fq > 30) & (fq < 200)
                tonhoehe[i].append(fq[sel][np.argmax(spek[sel])])
    pegel /= max(takte, 1)
    rel = [round(db(p / pegel.max()), 1) for p in pegel]
    noten = [note(float(np.median(h))) if h else None for h in tonhoehe]
    # Ausklingen einer Bassnote: mittlere Zeit bis -12 dB nach dem lautesten 16tel
    i0 = int(np.argmax(pegel))
    laengen = []
    for t in range(takte):
        a = int(start + (t * 16 + i0) * s16)
        e = env[a:a + int(4 * s16)]
        if len(e) and e.max() > 0:
            u = np.where(e[np.argmax(e):] < e.max() * 10 ** (-12 / 20))[0]
            if len(u): laengen.append(u[0] / SR * 1000)
    return {'pegel_je_16tel_db': rel, 'ton_je_16tel': noten, 'lautestes_16tel': i0,
            'abfall_12db_ms': round(float(np.median(laengen)), 1) if laengen else None,
            'bass_spitze_dbfs': round(db(np.max(np.abs(b))), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bpm', type=float, required=True)
    ap.add_argument('--drums', required=True)
    ap.add_argument('--bass')
    ap.add_argument('--von', type=float, default=60)
    ap.add_argument('--bis', type=float, default=180)
    ap.add_argument('--kick-wav')
    a = ap.parse_args()
    d = lesen(a.drums, a.von, a.bis)
    pk = kick_onsets(d, a.bpm)
    if len(pk) < 8:
        sys.exit(f'nur {len(pk)} Kick-Schlaege gefunden; anderen Ausschnitt waehlen (--von/--bis)')
    k, n = kick_mittel(d, pk)
    aus = {'ausschnitt_s': [a.von, a.bis], 'kick_schlaege': n, 'kick': kick_werte(k)}
    if a.kick_wav:
        pcm = (np.clip(k / np.max(np.abs(k)) * 0.9, -1, 1) * 32767).astype('<i2').tobytes()
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', '-', a.kick_wav], input=pcm, check=True)
    if a.bass:
        aus['bass'] = bass_raster(lesen(a.bass, a.von, a.bis), a.bpm, int(pk[0]))
    print(json.dumps(aus, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
