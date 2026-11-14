"""Stil-Merkmale je Track fuer die Trennung raw / deep / hypnotic (nach sammlung-raster.py).
Gemessen im Haupt-Groove (32 Takte aus 'raster'), Wiederholung ueber den ganzen Track.

Aufruf: python -I -W ignore sammlung-stil.py <_Stems> [--neu] [--teil i/n]
"""
import argparse, importlib.util, json, sys
from pathlib import Path
import numpy as np
from scipy.signal import stft


def _modul(name, datei):
    s = importlib.util.spec_from_file_location(name, Path(__file__).parent / datei)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


vt = _modul('vt', 'vorlage-transkript.py')
vb = _modul('vb', 'vorlage-bloecke.py')
SR = vt.SR
VERFAHREN = 1


def rms_db(x):
    return float(vt.db(np.sqrt(np.mean(x * x)) + 1e-12))


def spektrum(x):
    f, _, Z = stft(x, SR, nperseg=2048, noverlap=1024)
    return f, np.abs(Z) ** 2


def helligkeit_hz(x):
    f, P = spektrum(x)
    gew = P.sum(0)
    return float(np.sum((f @ P) / (gew + 1e-20) * gew) / (gew.sum() + 1e-20))


def rauheit_db(x):
    # spektrale Flachheit 1-8 kHz: Rauschen und Verzerrung nahe 0 dB, klare Toene weit darunter
    f, P = spektrum(x)
    b = P[(f >= 1000) & (f <= 8000)] + 1e-20
    flach = np.exp(np.mean(np.log(b), 0)) / np.mean(b, 0)
    return float(np.median(10 * np.log10(flach)))


def kick_obertoene_db(drums, t0, bpm, beats):
    # Obertoene 300-3000 Hz gegen Grundton 40-150 Hz in den ersten 40 ms jedes Beats: verzerrte Kicks liegen hoeher
    tief, hoch = vt.huelle(vt.band(drums, 40, 150), 5), vt.huelle(vt.band(drums, 300, 3000), 5)
    w = []
    for k in range(beats):
        a = int((t0 + k * 60 / bpm) * SR)
        e = a + int(SR * .04)
        if e < len(drums):
            w.append(vt.db(hoch[a:e].max()) - vt.db(tief[a:e].max()))
    return float(np.median(w))


def flaeche_db(other, t0, bpm, takte):
    # gefaltete Synth-Huelle je 16tel: Flaechen/Drones nahe 0 dB, kurze Stabs tief darunter
    e = vt.huelle(other, 10)
    sech = 60 / bpm / 4
    pegel = np.array([[e[int((t0 + (i * 16 + j + .5) * sech) * SR)] for j in range(16)] for i in range(takte)])
    m = vt.db(np.median(pegel, 0))
    return float(m.min() - m.max())


def wiederholung(other, start, bpm):
    # mittlere Aehnlichkeit aller lauten 8-Takt-Bloecke untereinander (x10): hypnotische Loops nahe 10
    pegel, K = vb.aehnlichkeit(other, start, 4 * 60 / bpm)
    laut = pegel.sum(1) > pegel.sum(1).max() - 12
    k = K[np.ix_(laut, laut)]
    n = len(k)
    return float((k.sum() - np.trace(k)) / (n * n - n) * 10) if n > 1 else None


def merkmale(ordner, mw):
    r, bpm = mw['raster'], mw['bpm']
    takt = 4 * 60 / bpm
    von = r['start_s'] + (r['groove_takt'] - 1) * takt
    lade = lambda n: vt.lade(str(ordner / f'{n}.flac'))
    drums, other = lade('drums'), lade('other')
    a, e = int(von * SR), int((von + 32 * takt) * SR)
    d, o = drums[a:e], other[a:e]
    takte = int(len(d) / SR / takt)
    return {'verfahren': VERFAHREN,
            'synth_zu_drums_db': round(rms_db(o) - rms_db(d), 1),
            'synth_hell_hz': round(helligkeit_hz(o)),
            'rauheit_db': round(rauheit_db(d + o), 2),
            'kick_obertoene_db': round(kick_obertoene_db(d, 0, bpm, takte * 4), 1),
            'synth_flaeche_db': round(flaeche_db(o, 0, bpm, takte), 1),
            'synth_wiederholung': None if (w := wiederholung(other, r['start_s'], bpm)) is None else round(w, 1)}


def _selbsttest():
    t = np.arange(SR * 2) / SR
    ton, rauschen = np.sin(2 * np.pi * 2000 * t), np.random.default_rng(0).normal(0, 1, len(t))
    assert rauheit_db(rauschen) > rauheit_db(ton) + 20
    assert helligkeit_hz(vt.band(rauschen, 3000, 5000)) > helligkeit_hz(vt.band(rauschen, 200, 400))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    _selbsttest()
    ap = argparse.ArgumentParser()
    ap.add_argument('ordner')
    ap.add_argument('--neu', action='store_true')
    ap.add_argument('--teil', default='1/1')
    a = ap.parse_args()
    i, n = map(int, a.teil.split('/'))
    for f in sorted(Path(a.ordner).glob('*/messwerte.json'))[i - 1::n]:
        mw = json.loads(f.read_text('utf8'))
        if 'raster' not in mw or (mw.get('stil', {}).get('verfahren') == VERFAHREN and not a.neu):
            continue
        try:
            mw['stil'] = merkmale(f.parent, mw)
        except Exception as e:  # ein kaputter Track haelt den Stapel nicht an
            print(f'FEHLER {f.parent.name}: {e}', flush=True)
            continue
        f.write_text(json.dumps(mw, ensure_ascii=False, indent=1), 'utf8')
        print(f.parent.name[:45], mw['stil'], flush=True)
