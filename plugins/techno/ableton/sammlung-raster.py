"""Drum-Raster je Track der Sammlung: Takt-Start (Kick-Anschlag), Muster je 16tel und Band im Haupt-Groove, Swing.

Aufruf: python -I sammlung-raster.py <_Stems-Ordner> [--neu]
Schreibt je Track das Feld "raster" in messwerte.json. Haupt-Groove = die 32 Takte mit der meisten Kick-Energie.
Muster: Anschlagstaerke je 16tel (Median ueber die Takte, dB zum lautesten Schlag des Bands).
Swing: Lage der Hat-Anschlaege im kohaerenten Beat-Mittel, ms gegen das gerade Raster; 50 % = gerade.
"""
import argparse, importlib.util, json, sys
from pathlib import Path
import numpy as np

_spec = importlib.util.spec_from_file_location('vt', Path(__file__).parent / 'vorlage-transkript.py')
vt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vt)
_spec = importlib.util.spec_from_file_location('tt', Path(__file__).parent / 'tiefton-analyse.py')
tt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tt)
SR = vt.SR
# Kick bis 250 Hz: im 35-110-Band steigt die Huelle erst mit dem Pitch-Sweep, der Anschlag faellt sonst ins naechste 16tel
BAENDER = {'kick': (40, 250),'perc': (300, 900), 'clap': (1200, 3500), 'hat': (6000, 10900)}
TAKTE = 32
VERFAHREN = 2  # 2 = Takt-Start mit Kick-Anker (vorlage-transkript.raster_start), Bass im selben Raster


def groove_start(kick_env, t0, bpm, takte_ges):
    takt = int(4 * 60 / bpm * SR)
    e = [np.mean(kick_env[int(t0 * SR) + t * takt:int(t0 * SR) + (t + 1) * takt] ** 2) for t in range(takte_ges)]
    fenster = np.convolve(e, np.ones(TAKTE), 'valid')
    return int(np.argmax(fenster))


def lage_im_beat(env, t0, bpm, takte):
    """Je 16tel-Slot im Beat: Versatz des staerksten Anschlags (ms) zum geraden Raster und seine Staerke (dB zu Slot-Max)."""
    beat = SR * 60 / bpm
    s0 = int(t0 * SR)
    m = np.mean([env[s0 + int(b * beat):s0 + int(b * beat) + int(beat)] for t in takte for b in range(t * 4, t * 4 + 4)
                 if s0 + int((b + 1) * beat) < len(env)], 0)
    d = np.maximum(np.diff(m, prepend=m[0]), 0)
    d = np.convolve(d, np.ones(int(SR * .002)), 'same')
    sech = beat / 4
    aus = []
    for k in range(4):
        lo, hi = int(k * sech - SR * .02), int(k * sech + SR * .06)
        idx = np.arange(lo, hi) % len(d)
        i = int(np.argmax(d[idx]))
        aus.append((round((lo + i - k * sech) / SR * 1000, 1), float(d[idx][i])))
    top = max(v for _, v in aus) or 1
    return [(ms, round(float(vt.db(v / top)), 1)) for ms, v in aus]


def analysiere(drums, bpm):
    t0 = vt.raster_start(drums, bpm)
    takte_ges = int((len(drums) / SR - t0) / (4 * 60 / bpm)) - 1
    # 10 ms fuer die Kick: eine 2-ms-Huelle rippelt bei 50 Hz und erzeugt Schein-Anschlaege im Ausklang
    env = {b: vt.huelle(vt.band(drums, *r), 10 if b == 'kick' else 2) for b, r in BAENDER.items()}
    g0 = groove_start(env['kick'], t0, bpm, takte_ges)
    takte = range(g0, min(g0 + TAKTE, takte_ges))
    muster = {}
    for b, e in env.items():
        st = vt.treffer(e, t0 + g0 * 4 * 60 / bpm, bpm, len(takte) * 16).reshape(-1, 16)
        med = np.median(st, 0)
        muster[b] = [round(float(v), 1) for v in med - med.max()]
    hat = lage_im_beat(env['hat'], t0, bpm, takte)
    return {'start_s': round(t0, 4), 'groove_takt': g0 + 1, 'muster': muster, 'hat_lage_ms_db': hat, 'swing_prozent': swing_aus(hat, bpm)}


def raster(o, bpm):
    r = analysiere(vt.lade(str(o / 'drums.flac')), bpm)
    # Bass im selben Raster: Ausschnitt ab Groove-Takt, Start 0 = Kick-Anschlag (alter Wert lag an beliebiger Taktstelle)
    takt = 4 * 60 / bpm
    von = r['start_s'] + (r['groove_takt'] - 1) * takt
    r['bass'] = tt.bass_raster(tt.lesen(str(o / 'bass.flac'), von, von + TAKTE * takt), bpm, 0)
    r['verfahren'] = VERFAHREN
    return r


def swing_aus(hat, bpm):
    """Swing (%) aus den Hat-Lagen je Slot, nur mit Beleg: Offbeat-Hat (x.5) laut und hoechstens 12 ms neben dem Raster
    (sonst stimmt der Takt-Start nicht), x.25/x.75 laut und nicht am Fensterrand (-20/+60 ms = kein echter Schlag)."""
    ms2, db2 = hat[2]
    if db2 < -6 or abs(ms2) > 12:
        return None
    ungerade = [ms for k, (ms, dbv) in enumerate(hat) if k % 2 and dbv > -10 and -15 < ms < 55]
    return round(50 + np.mean(ungerade) / (2 * 60 / bpm / 4 * 1000) * 100, 1) if ungerade else None


def _selbsttest():
    bpm = 130
    beat = SR * 60 / bpm
    t = np.arange(int(SR * .4)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(50 + 170 * np.exp(-t / .03)) / SR) * np.exp(-t / .2)
    rng = np.random.default_rng(3)
    hat = vt.band(rng.normal(0, .3, int(SR * .03)), 5000, 10900) * np.exp(-np.arange(int(SR * .03)) / SR / .006)
    x = np.zeros(int(SR * 90))
    sech = beat / 4
    for b in range(int(len(x) / beat) - 2):
        a = int(SR * .05 + b * beat)
        x[a:a + len(kick)] += kick
        for k, vers in ((1, 0.62), (2, 0.0), (3, 0.62)):  # 62 % Swing auf x.25 und x.75
            h = a + int(k * sech + (vers - .5) * 2 * sech if k % 2 else k * sech)
            x[h:h + len(hat)] += hat
    r = analysiere(x, bpm)
    assert abs(r['start_s'] - .05) < .003, r['start_s']
    assert r['swing_prozent'] and abs(r['swing_prozent'] - 62) < 2, r['swing_prozent']
    assert r['muster']['kick'][0] == 0 and r['muster']['kick'][2] < -10, r['muster']['kick']


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')  # Tracknamen mit Sonderzeichen (U+29F8) brachen die cp1252-Konsole
    _selbsttest()
    ap = argparse.ArgumentParser()
    ap.add_argument('stems')
    ap.add_argument('--neu', action='store_true')
    ap.add_argument('--teil', default='1/1', help='i/n: jeden n-ten Track ab i, fuer parallele Laeufe')
    a = ap.parse_args()
    i0, n = map(int, a.teil.split('/'))
    ordner = sorted(p.parent for p in Path(a.stems).glob('*/messwerte.json'))[i0 - 1::n]
    for i, o in enumerate(ordner, 1):
        mw = json.loads((o / 'messwerte.json').read_text('utf8'))
        if mw.get('raster', {}).get('verfahren') == VERFAHREN and not a.neu:
            continue
        try:
            mw['raster'] = raster(o, mw['bpm'])
        except Exception as e:
            print(f'FEHLER {o.name}: {e}', flush=True)
            continue
        (o / 'messwerte.json').write_text(json.dumps(mw, ensure_ascii=False, indent=1), 'utf8')
        r = mw['raster']
        print(f"{i}/{len(ordner)} {o.name}: Start {r['start_s']} s, Swing {r['swing_prozent']}", flush=True)
