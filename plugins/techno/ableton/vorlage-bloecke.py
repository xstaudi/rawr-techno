"""Wie viele Fassungen hat ein Stem (meist other = Synth)? Pegel je Band und 8-Takt-Block, dazu Aehnlichkeit Block gegen Block
(Korrelation der Bandhuellen je 16tel, x10). Bloecke mit 9-10 untereinander sind dieselbe Fassung: ein Loop reicht fuer alle.

Aufruf: python -I vorlage-bloecke.py <stem.wav> <bpm> <start_s>
"""
import sys
import numpy as np
from scipy.signal import butter, sosfiltfilt
import subprocess

SR = 22050
BAND = {'100-300': (100, 300), '300-1k': (300, 1000), '1-3k': (1000, 3000), '3-8k': (3000, 8000)}


def lade(p):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', p, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(r, np.float32).astype(np.float64)


def aehnlichkeit(x, t0, takt):
    g = {b: sosfiltfilt(butter(4, r, 'band', fs=SR, output='sos'), x) for b, r in BAND.items()}
    n = int((len(x) / SR - t0) / takt) // 8
    hop = int(SR * takt / 16)
    pegel, vec = [], []
    for i in range(n):
        a, e = int((t0 + i * 8 * takt) * SR), int((t0 + (i + 1) * 8 * takt) * SR)
        pegel.append([10 * np.log10(np.mean(g[b][a:e] ** 2) + 1e-20) for b in BAND])
        vec.append(np.concatenate([np.log10(np.add.reduceat(g[b][a:e] ** 2, np.arange(0, e - a, hop))[:128] + 1e-12) for b in BAND]))
    V = np.array(vec)
    V = (V - V.mean(1, keepdims=True)) / (V.std(1, keepdims=True) + 1e-12)
    return np.array(pegel), V @ V.T / V.shape[1]


def _selbsttest():
    takt = 4 * 60 / 144
    t = np.arange(int(SR * 8 * takt)) / SR
    a = np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 2.4 * t) > 0)
    b = np.sin(2 * np.pi * 1500 * t) * (np.sin(2 * np.pi * 4.8 * t + 1) > 0)
    _, K = aehnlichkeit(np.concatenate([a, b, a, b, a[:SR]]), 0, takt)  # Fassung A, B, A, B
    assert K[0, 2] > 0.9 and K[0, 1] < 0.5, K.round(1)


if __name__ == '__main__':
    _selbsttest()
    pfad, bpm, t0 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    pegel, K = aehnlichkeit(lade(pfad), t0, 4 * 60 / bpm)
    print('Block    ' + ''.join(f'{b:>9}' for b in BAND))
    for i, p in enumerate(pegel):
        print(f'{i * 8 + 1:3}-{i * 8 + 8:<4} ' + ''.join(f'{v:9.1f}' for v in p))
    print('\nAehnlichkeit x10:\n      ' + ''.join(f'{i * 8 + 1:4}' for i in range(len(K))))
    for i in range(len(K)):
        print(f'{i * 8 + 1:4}  ' + ''.join(f'{int(round(K[i, j] * 10)):4}' for j in range(len(K))))
