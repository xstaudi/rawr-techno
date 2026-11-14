"""Messwerte je Library-Sample (Helligkeit, Rauheit, Laenge bis -20 dB, Grundton), zwischengespeichert in
<Samples>/_Stems/_sample-merkmale.json. Damit waehlt stil-rezept.py Klaenge nach dem Stil-Profil statt nach Ordnernamen.

Aufruf (Vorrat fuellen): python -I sample-merkmale.py
"""
import json, os, subprocess, sys
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfiltfilt

SR = 22050
EIG = Path(os.environ.get('TECHNO_LIBRARY', str(Path.home() / 'Music' / 'Samples')))
CACHE = EIG / '_Stems' / '_sample-merkmale.json'
ENDUNGEN = {'.wav', '.aif', '.aiff', '.flac', '.mp3'}
# One-Shots aus gekauften Tracks sind nur zum Nachbau privat, nie Baustoff fuer eigene Tracks
GESPERRT = ('Sammlung', '_Stems', 'Eigene')
ROLLEN = {'kick': ['Kicks/One-Shots'], 'hat': ['HiHats/One-Shots'], 'perc': ['Percussion/One-Shots'], 'synth': ['Synths/One-Shots'],
          'pad': ['Atmo-Pads/One-Shots'], 'fx': ['FX/One-Shots']}


def lade(p):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(p), '-ac', '1', '-ar', str(SR), '-t', '6', '-f', 'f32le', '-'],
                       capture_output=True, check=True).stdout
    return np.frombuffer(r, np.float32).astype(np.float64)


def merkmale(x):
    x = x[:SR * 6]
    hop = 256
    e = np.sqrt(np.convolve(x * x, np.ones(hop) / hop, 'same'))
    spitze = int(np.argmax(e))
    unter = np.where(e[spitze:] < e[spitze] * 0.1)[0]
    dauer = (unter[0] if len(unter) else len(e) - spitze) / SR * 1000
    seg = x[spitze:spitze + min(len(x) - spitze, SR)]
    seg = seg * np.hanning(len(seg))
    P = np.abs(np.fft.rfft(seg, n=1 << 15)) ** 2
    f = np.fft.rfftfreq(1 << 15, 1 / SR)
    hell = float((f * P).sum() / (P.sum() + 1e-20))
    b = P[(f >= 1000) & (f <= 8000)] + 1e-20
    rauh = float(10 * np.log10(np.exp(np.mean(np.log(b))) / np.mean(b)))
    t = (f > 30) & (f < 2000)
    grund = f[t][np.argmax(P[t])]
    return {'hell_hz': round(hell), 'rauheit_db': round(rauh, 1), 'dauer_ms': round(dauer), 'grundton_midi': round(float(69 + 12 * np.log2(grund / 440)), 2)}


def kick_obertoene(x, sr):
    # wie sammlung-stil.kick_obertoene_db: 300-3000 Hz gegen 40-150 Hz in den ersten 40 ms
    n = int(sr * .04)
    band = lambda lo, hi: np.abs(sosfiltfilt(butter(4, [lo, hi], 'band', fs=sr, output='sos'), x[:n * 4]))[:n].max()
    return float(20 * np.log10(band(300, 3000) / (band(40, 150) + 1e-12) + 1e-12))


def kick_merkmale(p):
    # Kick-Werte wie in der Sammlung (tiefton-analyse.kick_werte), dort mit 44,1 kHz gemessen
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(p), '-ac', '1', '-ar', str(_tt().SR), '-t', '1', '-f', 'f32le', '-'],
                       capture_output=True, check=True).stdout
    x = np.frombuffer(r, np.float32).astype(np.float64)
    x = x[max(0, int(np.argmax(np.abs(x) > np.abs(x).max() * 0.1)) - 32):]
    k = np.pad(x, (0, max(0, int(0.35 * _tt().SR) - len(x))))[:int(0.35 * _tt().SR)]
    # Im fast stillen Ausklang zaehlen Rausch-Nulldurchgaenge als Tonhoehe und ziehen den Fit an die 400-Hz-Grenze
    env = np.maximum.accumulate(np.abs(k)[::-1])[::-1]
    k = np.where(env > np.abs(k).max() * 10 ** (-30 / 20), k, 0)
    w = _tt().kick_werte(k)
    return {'f_end_hz': w.get('f_end_hz'), 'abfall_20db_ms': w.get('abfall_20db_ms'), 'obertoene_db': round(kick_obertoene(k, _tt().SR), 1)}


_TT = []


def _tt():
    if not _TT:
        import importlib.util
        s = importlib.util.spec_from_file_location('tt', Path(__file__).parent / 'tiefton-analyse.py')
        m = importlib.util.module_from_spec(s)
        s.loader.exec_module(m)
        _TT.append(m)
    return _TT[0]


def vorrat(rolle):
    """Alle Samples einer Rolle mit Messwerten; neue oder geaenderte Dateien werden nachgemessen."""
    cache = json.loads(CACHE.read_text('utf8')) if CACHE.exists() else {}
    aus, neu = [], 0
    for ordner in ROLLEN[rolle]:
        for p in sorted((EIG / ordner).rglob('*')):
            if p.suffix.lower() not in ENDUNGEN or any(g in str(p) for g in GESPERRT):
                continue
            key, mt = str(p), p.stat().st_mtime
            if cache.get(key, {}).get('mtime') != mt or (rolle == 'kick' and 'f_end_hz' not in cache[key] and not cache[key].get('fehler')):
                try:
                    cache[key] = {'mtime': mt, **merkmale(lade(p)), **(kick_merkmale(p) if rolle == 'kick' else {})}
                except (subprocess.CalledProcessError, ValueError, IndexError, ZeroDivisionError):
                    cache[key] = {'mtime': mt, 'fehler': True}
                neu += 1
            if not cache[key].get('fehler'):
                aus.append({'pfad': key, **cache[key]})
    if neu:
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), 'utf8')
    return aus


def _selbsttest():
    t = np.arange(SR) / SR
    ton = np.sin(2 * np.pi * 110 * t) * np.exp(-t / 0.05)
    m = merkmale(ton)
    assert abs(m['grundton_midi'] - 45) < 0.3 and m['dauer_ms'] < 200, m
    rausch = np.random.default_rng(0).normal(0, 1, SR)
    assert merkmale(rausch)['rauheit_db'] > m['rauheit_db'] + 10


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    _selbsttest()
    for r in ROLLEN:
        print(r, len(vorrat(r)), flush=True)
