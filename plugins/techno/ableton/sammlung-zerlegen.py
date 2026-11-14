# Zerlegt eine Track-Sammlung in Stems (Demucs), vermisst jeden Track und legt One-Shots ab. Neustart-fest.
# Aufruf (venv mit demucs): python -I sammlung-zerlegen.py <quellordner> <samples-ordner> <arbeitsordner> [--name "Sammlung 2025"] [--max N]
# Ergebnis je Track: <samples>/_Stems/<Track>/{drums,bass,other,vocals}.flac + messwerte.json,
# One-Shots in <samples>/{Kicks,Bass,Claps,HiHats}/One-Shots/<name>/<Track>.wav
import argparse, importlib.util, json, os, re, shutil, subprocess, sys, time, traceback
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfiltfilt, find_peaks, hilbert

HIER = Path(__file__).parent
_spec = importlib.util.spec_from_file_location('tiefton', HIER / 'tiefton-analyse.py')
tt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tt)
SR = tt.SR
ENDUNGEN = {'.mp3', '.flac', '.wav', '.aif', '.aiff'}
DUR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]  # Krumhansl-Profile
MOLL = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def ordnername(p):
    return re.sub(r'[<>:"/\\|?*]', '_', p.stem).strip(' .')[:120]


def dauer(p):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(p)],
                                capture_output=True, text=True, encoding='utf-8', errors='replace', check=True).stdout)


def tempo(drums):
    lp = sosfiltfilt(butter(4, 120, 'lowpass', fs=SR, output='sos'), drums)
    env = np.convolve(np.abs(hilbert(lp)), np.ones(64) / 64, 'same')
    d = np.maximum(np.diff(env), 0)
    pk, _ = find_peaks(d, distance=int(0.3 * SR), height=np.percentile(d, 99.5) * 0.3)
    iv = np.diff(pk) / SR
    iv = iv[(iv > 60 / 165) & (iv < 60 / 115)]
    if len(iv) < 16:
        return None, pk
    grob = np.median(iv)
    # Feinwert: Regression der Onsets ueber ihre Schlagnummer
    idx = np.round((pk - pk[0]) / SR / grob)
    a = np.polyfit(idx, pk / SR, 1)[0]
    return round(float(60 / a), 2), pk


def tonart(other):
    spek = np.abs(np.fft.rfft(other[: SR * 60] * np.hanning(min(len(other), SR * 60))))
    fq = np.fft.rfftfreq(min(len(other), SR * 60), 1 / SR)
    sel = (fq > 55) & (fq < 2000)
    midi = np.round(69 + 12 * np.log2(fq[sel] / 440)).astype(int)
    chroma = np.bincount(midi % 12, weights=spek[sel] ** 2, minlength=12)
    best = max(((np.corrcoef(chroma, np.roll(prof, k))[0, 1], k, art) for k in range(12)
                for prof, art in ((DUR, 'Dur'), (MOLL, 'Moll'))))
    return f'{tt.NOTEN[best[1]]} {best[2]}', round(float(best[0]), 2)


def lufs(p):
    out = subprocess.run(['ffmpeg', '-hide_banner', '-threads', '4', '-i', str(p), '-af', 'ebur128', '-f', 'null', '-'],
                         capture_output=True, text=True, encoding='utf-8', errors='replace').stderr
    m = re.findall(r'I:\s+(-?[\d.]+) LUFS', out)
    return float(m[-1]) if m else None


def median_schlag(x, starts, n):
    hits = [x[s:s + n] for s in starts if s >= 0 and s + n < len(x)]
    return np.median(np.array(hits), axis=0) if len(hits) >= 8 else None


def wav_schreiben(x, pfad):
    if x is None or np.max(np.abs(x)) < 1e-4:
        return False
    pfad.parent.mkdir(parents=True, exist_ok=True)
    x = x / np.max(np.abs(x)) * 10 ** (-1 / 20)
    x[-220:] *= np.linspace(1, 0, 220)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', '-', str(pfad)],
                   input=(x * 32767).astype('<i2').tobytes(), check=True)
    return True


def oneshots(stems, bpm, pk, ziel, name):
    beat = 60 / bpm * SR
    vor = 64
    hp = lambda x, hz: sosfiltfilt(butter(4, hz, 'highpass', fs=SR, output='sos'), x)
    kick = median_schlag(stems['drums'], pk - vor, int(0.35 * SR))
    # Clap: die Haelfte der Kick-Schlaege mit mehr Energie ueber 300 Hz ist der Backbeat. Hochpass trennt Clap/Hat von der Kick.
    hoch = hp(stems['drums'], 300)
    e = np.array([np.sqrt(np.mean(hoch[p:p + int(0.1 * SR)] ** 2)) for p in pk])
    paritaet = int(np.mean(e[1::2]) > np.mean(e[0::2]))
    clap = median_schlag(hoch, pk[paritaet::2] - vor, int(0.3 * SR))
    hat = median_schlag(hp(stems['drums'], 6000), (pk + beat / 2).astype(int) - vor, int(0.12 * SR))
    b = stems['bass']
    s16 = beat / 4
    env = np.abs(hilbert(sosfiltfilt(butter(4, 250, 'lowpass', fs=SR, output='sos'), b)))
    slot = int(np.argmax([np.mean([env[int(p + i * s16):int(p + (i + 1) * s16)].max() for p in pk[:-1]]) for i in range(4)]))
    bass = median_schlag(b, (pk + slot * s16).astype(int) - vor, int(2 * s16))
    gelegt = {}
    for art, x in (('Kicks', kick), ('Claps', clap), ('HiHats', hat), ('Bass', bass)):
        pfad = ziel / art / 'One-Shots' / name
        if wav_schreiben(x, pfad):
            gelegt[art] = str(pfad)
    return gelegt


def energie_je_8_takte(drums, bpm):
    lp = sosfiltfilt(butter(4, 100, 'lowpass', fs=SR, output='sos'), drums)
    blk = int(8 * 4 * 60 / bpm * SR)
    rms = [float(np.sqrt(np.mean(lp[i:i + blk] ** 2))) for i in range(0, len(lp) - blk // 2, blk)]
    ref = max(rms) or 1
    return [round(tt.db(r / ref), 1) for r in rms]


def lesen_voll(p):
    return np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-threads', '4', '-i', str(p), '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-'],
                                        capture_output=True, check=True).stdout, dtype=np.float32).astype(float)


def track(quelle, demucs_dir, samples, name):
    tn = ordnername(quelle)
    ziel = samples / '_Stems' / tn
    stems = {s: lesen_voll(demucs_dir / f'{s}.wav') for s in ('drums', 'bass', 'other')}
    bpm, pk = tempo(stems['drums'])
    m = {'datei': quelle.name, 'dauer_s': round(dauer(quelle), 1), 'bpm': bpm, 'lufs': lufs(quelle)}
    m['tonart'], m['tonart_sicherheit'] = tonart(stems['other'] + stems['bass'])
    if bpm:
        mitte = len(stems['drums']) / SR * 0.3
        von, bis = mitte, mitte + 90
        a = SR * int(von)
        teil = {k: v[a:a + SR * 90] for k, v in stems.items()}
        pk_t = tt.kick_onsets(teil['drums'], bpm)
        if len(pk_t) >= 16:
            k, n = tt.kick_mittel(teil['drums'], pk_t)
            m['kick'] = tt.kick_werte(k)
            m['bass'] = tt.bass_raster(teil['bass'], bpm, int(pk_t[0]))
            m['oneshots'] = oneshots(teil, bpm, pk_t, samples, f'{name}/{tn}.wav')
        m['energie_8takte_db'] = energie_je_8_takte(stems['drums'], bpm)
        m['bass_anteil_im_bassstem_db'] = round(tt.db(np.sqrt(np.mean(stems['bass'] ** 2)) / max(np.sqrt(np.mean(stems['drums'] ** 2)), 1e-9)), 1)
    ziel.mkdir(parents=True, exist_ok=True)
    for s in ('drums', 'bass', 'other', 'vocals'):
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-threads', '4', '-i', str(demucs_dir / f'{s}.wav'), '-c:a', 'flac', str(ziel / f'{s}.flac')], check=True)
    (ziel / 'messwerte.json').write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding='utf-8')
    return m


def demucs(tmp, dateien):
    # Demucs druckt Dateinamen; ohne UTF-8 bricht es an Zeichen wie U+29F8 auf der cp1252-Pipe ab
    # ohne -d nimmt Demucs CUDA, wenn vorhanden, sonst CPU (Plugin-Nutzer ohne Nvidia)
    return subprocess.run([sys.executable, '-m', 'demucs', '-n', 'htdemucs', '-o', str(tmp / 'out'), *map(str, dateien)],
                          capture_output=True, text=True, encoding='utf-8', errors='replace',
                          env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('quelle')
    ap.add_argument('samples')
    ap.add_argument('arbeit')
    ap.add_argument('--name', default='Sammlung 2025')
    ap.add_argument('--max', type=int, default=0)
    ap.add_argument('--paket', type=int, default=8, help='Tracks je Demucs-Aufruf (Modell laedt einmal je Paket)')
    a = ap.parse_args()
    # Tracknamen mit Sonderzeichen (z. B. U+29F8) brachen die cp1252-Konsole und damit den Stapellauf ab
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    quelle, samples, arbeit = Path(a.quelle), Path(a.samples), Path(a.arbeit)
    # '._*' sind macOS-Metadaten ohne Audio
    offen = [p for p in sorted(quelle.iterdir()) if p.suffix.lower() in ENDUNGEN and not p.name.startswith('._')
             and not (samples / '_Stems' / ordnername(p) / 'messwerte.json').exists()]
    if a.max:
        offen = offen[:a.max]
    print(f'{len(offen)} Tracks offen', flush=True)
    fehler = []
    for i in range(0, len(offen), a.paket):
        paket = offen[i:i + a.paket]
        tmp = arbeit / 'paket'
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        # Kopien mit sauberen Namen: Demucs benennt Ausgabeordner nach dem Dateinamen.
        kopien = {}
        for p in paket:
            k = tmp / f'{ordnername(p)}{p.suffix.lower()}'
            shutil.copyfile(p, k)
            kopien[p] = k
        t0 = time.time()
        r = demucs(tmp, kopien.values())
        print(f'Demucs Paket {i // a.paket + 1}: {time.time() - t0:.0f} s, exit {r.returncode}', flush=True)
        # Demucs bricht das ganze Paket ab, wenn eine Datei nicht lesbar ist: Rest einzeln nachholen
        if r.returncode:
            for k in kopien.values():
                if not (tmp / 'out' / 'htdemucs' / k.stem / 'drums.wav').exists():
                    r = demucs(tmp, [k])
        for p, k in kopien.items():
            d = tmp / 'out' / 'htdemucs' / k.stem
            try:
                if not (d / 'drums.wav').exists():
                    raise RuntimeError('keine Stems: ' + r.stderr[-300:])
                m = track(p, d, samples, a.name)
                print(f'  ok {p.name}: {m.get("bpm")} BPM, {m.get("tonart")}, Kick {m.get("kick", {}).get("f_end_note")}', flush=True)
            except Exception:  # ein kaputter Track stoppt den Lauf nicht; Liste am Ende
                fehler.append((p.name, traceback.format_exc()[-600:]))
                print(f'  FEHLER {p.name}: {fehler[-1][1]}', flush=True)
        shutil.rmtree(tmp, ignore_errors=True)
    (arbeit / 'fehler.json').write_text(json.dumps(fehler, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'fertig, {len(fehler)} Fehler', flush=True)


if __name__ == '__main__':
    main()
