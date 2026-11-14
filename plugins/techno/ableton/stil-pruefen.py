"""Vermisst einen Export wie die Sammlung (Demucs, Raster, Stil-Merkmale) und vergleicht mit _profil-<stil>.json.

Aufruf: python -I -W ignore stil-pruefen.py <raw|deep|hypnotic> <export.wav>
Arbeitsordner: <export-ordner>/pruefung/. Ausgabe: Tabelle Merkmal | Export | Sammlung (Quartile) | ok, dazu die
Stil-Zuordnung, die der Export in der Sammlung bekaeme. Exit 1, wenn ein Pflicht-Merkmal ausserhalb liegt.
"""
import importlib.util, json, shutil, sys
from pathlib import Path
import numpy as np

HIER = Path(__file__).parent


def _modul(name, datei):
    s = importlib.util.spec_from_file_location(name, HIER / datei)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


sz = _modul('sz', 'sammlung-zerlegen.py')
sr = _modul('sr', 'sammlung-raster.py')
ss = _modul('ss', 'sammlung-stil.py')
sp = _modul('sp', 'sammlung-profil.py')
STEMS = _modul('kl', 'stil-klang.py').profil_ordner()
# Pflicht = Abnahme-Satz (Tempo, Kick, Drum-Geruest, Bass, Arrangement, Lautheit); Rest nur zur Info
PFLICHT = {'bpm', 'lufs', 'dauer_min', 'kick_f_end_hz', 'kick_abfall_20db_ms', 'kick_obertoene_db', 'bloecke'}


def im_bereich(wert, qs):
    # Kernbereich der Sammlung: Quartile, um eine halbe Quartilsbreite erweitert
    lo, _, hi = qs
    rand = (hi - lo) / 2
    return lo - rand <= wert <= hi + rand


def vermessen(export, arbeit):
    if arbeit.exists():
        shutil.rmtree(arbeit)
    (arbeit / 'paket').mkdir(parents=True)
    kopie = arbeit / 'paket' / 'export.wav'
    shutil.copy(export, kopie)
    r = sz.demucs(arbeit / 'paket', [kopie])
    if r.returncode:
        print(f'Demucs-Fehler: {r.stderr[-500:]}', file=sys.stderr)
        sys.exit(3)
    m = sz.track(kopie, arbeit / 'paket' / 'out' / 'htdemucs' / 'export', arbeit, 'Pruefung')
    o = arbeit / '_Stems' / 'export'
    m['raster'] = sr.raster(o, m['bpm'])
    m['stil'] = ss.merkmale(o, m)
    m['tags'] = {'genre': 'Techno (Raw / Deep / Hypnotic)'}
    shutil.rmtree(arbeit / 'paket')
    (o / 'messwerte.json').write_text(json.dumps(m, ensure_ascii=False, indent=1, default=lambda x: x.item()), 'utf8')
    return m


def zuordnung(m):
    # Matrix = entdoppelte Tracks des Profils, nur Zahlen; liegt auch im Plugin ohne Sammlung
    matrix = STEMS / '_stil-matrix.json'
    tracks = json.loads(matrix.read_text('utf8')) if matrix.exists() else [json.loads(f.read_text('utf8')) for f in sorted(STEMS.glob('*/messwerte.json'))]
    m = {**m, '_name': 'EXPORT'}
    for s, tr in sp.stil_zuordnung(tracks + [m]).items():
        for t in tr:
            if t.get('_name') == 'EXPORT':
                return s, t['_stil_wert']
    return None, None


def vergleich(stil, m):
    p = json.loads((STEMS / f'_profil-{stil}.json').read_text('utf8'))
    e = np.array(m['energie_8takte_db'])
    zeilen = [('bpm', m['bpm'], p['bpm']['quartile']), ('lufs', m['lufs'], p['lufs']),
              ('dauer_min', round(m['dauer_s'] / 60, 1), p['dauer_min']), ('bloecke', len(e), p['arrangement']['bloecke'])]
    for k in ('f_end_hz', 'pitch_tau_ms', 'abfall_20db_ms'):
        if m.get('kick', {}).get(k) is not None:
            zeilen.append((f'kick_{k}', m['kick'][k], p['kick'][k]))
    zeilen += [(k, m['stil'][k], p['stil_merkmale'][k]) for k in p['stil_merkmale'] if m['stil'].get(k) is not None]
    k = sp.kennzahlen(m['raster'])
    gm = p['grundmuster_prozent']['alle']
    info = {f: (k.get(f), gm.get(f)) for f in ('kick_4_4', 'clap_2_4', 'offbeat_hat', 'bass_zwischen_kicks')}
    info['bass_slot'] = (k.get('bass_slot'), p.get('bass_slot'))
    return [(n, w, qs, im_bereich(w, qs)) for n, w, qs in zeilen], info


def _selbsttest():
    assert im_bereich(143, [140, 143, 144.5]) and not im_bereich(150, [140, 143, 144.5]) and im_bereich(146.5, [140, 143, 144.5])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    _selbsttest()
    stil, export = sys.argv[1], Path(sys.argv[2])
    m = vermessen(export, export.parent / 'pruefung')
    zeilen, info = vergleich(stil, m)
    print(f'| Merkmal | Export | Sammlung {stil} (Q1/Median/Q3) | ok |\n|---|---|---|---|')
    for n, w, qs, ok in zeilen:
        print(f"| {n}{' *' if n in PFLICHT else ''} | {w} | {' / '.join(map(str, qs))} | {'ja' if ok else 'NEIN'} |")
    for f, (w, anteil) in info.items():
        print(f'| {f} | {w} | {anteil} {"% der Sammlung" if f != "bass_slot" else "(Slot: Tracks)"} | – |')
    s, werte = zuordnung(m)
    print(f'\nStil-Zuordnung des Exports: {s} (raw/deep/hypnotic = {werte})')
    fehlt = [n for n, _, _, ok in zeilen if n in PFLICHT and not ok]
    print('Pflicht ausserhalb: ' + (', '.join(fehlt) if fehlt else 'keins'))
    sys.exit(1 if fehlt or s != stil else 0)
