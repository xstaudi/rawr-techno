# Erzeugt Kick- und Rumble-One-Shots aus Messwerten (tiefton-analyse.py), eigener Klang statt fremder Samples.
# Aufruf: python -I tiefton-bauen.py kick   --aus kick.wav --f-start 180 --f-end 58.3 --tau 24 --abfall 300 --drive 2.5 [--klick 0.15]
#         python -I tiefton-bauen.py rumble --aus rumble.wav --hz 58.3 --laenge 110 --drive 2 [--hall 0.35]
import argparse, subprocess
import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100


def schreiben(x, pfad):
    x = x / np.max(np.abs(x)) * 10 ** (-1 / 20)  # Spitze -1 dBFS
    x[-int(0.005 * SR):] *= np.linspace(1, 0, int(0.005 * SR))
    pcm = (x * 32767).astype('<i2').tobytes()
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', '-', pfad], input=pcm, check=True)


def saettigen(x, drive):
    return np.tanh(drive * x) / np.tanh(drive) if drive > 0 else x


def huelle(t, angriff_ms, halten_ms, abfall_ms, grenze_db):
    # abfall_ms = Zeit ab Ende des Haltens bis grenze_db unter Spitze
    k = np.log(10 ** (grenze_db / 20)) / (abfall_ms / 1000)
    a = np.minimum(t / (angriff_ms / 1000), 1)
    nach = np.maximum(t - halten_ms / 1000, 0)
    return a * np.exp(k * nach)


def kick(a):
    t = np.arange(int((a.abfall + 120) / 1000 * SR)) / SR
    f = a.f_end + (a.f_start - a.f_end) * np.exp(-t / (a.tau / 1000))
    koerper = np.sin(2 * np.pi * np.cumsum(f) / SR) * huelle(t, 0.5, a.halten, a.abfall, -20)
    rng = np.random.default_rng(1)
    klick = sosfilt(butter(2, 2500, 'highpass', fs=SR, output='sos'), rng.standard_normal(len(t))) * np.exp(-t / 0.0015)
    return saettigen(koerper + a.klick * klick / np.max(np.abs(klick)), a.drive)


def rumble(a):
    t = np.arange(int((a.laenge * 2.5 + 60) / 1000 * SR)) / SR
    f = a.hz * (1 + 0.04 * np.exp(-t / 0.008))  # kurzer Einschwing-Glide, sonst klickt der Ton nur
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * huelle(t, 4, 0, a.laenge, -12)
    if a.hall > 0:
        # Rumble-Charakter: tiefpassgefilterte Hallfahne aus Rauschen, nur unter 180 Hz
        rng = np.random.default_rng(2)
        ir = rng.standard_normal(int(0.6 * SR)) * np.exp(-np.arange(int(0.6 * SR)) / SR / 0.15)
        nass = np.convolve(x, ir)[:len(t)]
        nass = sosfilt(butter(4, 180, 'lowpass', fs=SR, output='sos'), nass)
        x = x + a.hall * nass / np.max(np.abs(nass))
    return saettigen(x, a.drive)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('art', choices=['kick', 'rumble'])
    ap.add_argument('--aus', required=True)
    ap.add_argument('--f-start', type=float, default=180)
    ap.add_argument('--f-end', type=float, default=55)
    ap.add_argument('--tau', type=float, default=25, help='Pitch-Zeitkonstante in ms')
    ap.add_argument('--halten', type=float, default=30, help='ms volle Lautstaerke vor dem Abfall')
    ap.add_argument('--abfall', type=float, default=300, help='ms bis -20 dB (Kick)')
    ap.add_argument('--klick', type=float, default=0.12)
    ap.add_argument('--hz', type=float, default=55)
    ap.add_argument('--laenge', type=float, default=110, help='ms bis -12 dB (Rumble)')
    ap.add_argument('--hall', type=float, default=0.3)
    ap.add_argument('--drive', type=float, default=2.0)
    a = ap.parse_args()
    schreiben(kick(a) if a.art == 'kick' else rumble(a), a.aus)


if __name__ == '__main__':
    main()
