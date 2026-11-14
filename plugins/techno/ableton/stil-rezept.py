"""Stil-Profil (raw / deep / hypnotic) -> Song-Spec fuer build.mjs.

Aufruf: python -I -W ignore stil-rezept.py <raw|deep|hypnotic> [--seed N] [--bpm B] [--quelle library|synth] [--minuten M]
        [--nur Kick,Hat --takte 32] [--aus ordner]
Liest das Stil-Profil (stil-klang.profil_ordner), baut das Rumble selbst, nimmt die uebrigen Klaenge aus der Library nach
Messwerten (sample-merkmale.py) oder erzeugt sie (stil-klang.py), schreibt <aus>/<Name>/<Name>.json und Sounds/.
Danach: arrangement-check (nur ganze Tracks), build.mjs ins offene Set (Skill techno-track).
"""
import argparse, importlib.util, json, re, sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np

HIER = Path(__file__).parent


def _modul(name, datei):
    s = importlib.util.spec_from_file_location(name, HIER / datei)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


sm = _modul('sm', 'sample-merkmale.py')
tb = _modul('tb', 'tiefton-bauen.py')
kl = _modul('kl', 'stil-klang.py')
NOTEN = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
# Stufen je Stil (Halbtoene ueber dem Grundton); raw nutzt die kleine Sekunde fuer den duesteren Klang
STUFEN = {'raw': [0, 0, 1, 7, 12], 'deep': [0, 3, 7, 10], 'hypnotic': [0, 0, 3, 7, 10, 12]}
RUMBLE_DRIVE = {'raw': 3, 'deep': 1.5, 'hypnotic': 2}
KICK_DEMUCS_VERLUST_DB = 5
# Fills, Loops mit Tempo, Effekte und Gitarren liegen auch in One-Shot-Ordnern, taugen aber nicht als Motiv-Ton
UNPASSEND = re.compile(r'fill|guitar|impact|downlifter|uplifter|swell|riser|bpm|misc|vocal|loop|\bfx\b', re.I)


def median(qs):
    return qs[1]


def vel(db, ref=0.0):
    # dB unter dem lautesten Schlag -> Velocity; Simpler skaliert linear, 40er-Teiler haelt leise Schlaege hoerbar
    return int(np.clip(round(127 * 10 ** ((db - ref) / 40)), 30, 127))


def noten_aus_muster(zentrum_db, schwelle=-6, laenge=0.2, tonhoehe=None):
    z = np.array(zentrum_db, dtype=float)
    ref = z.max()
    return [[i * 0.25, laenge, vel(v, ref)] + ([tonhoehe] if tonhoehe is not None else []) for i, v in enumerate(z) if v - ref >= schwelle]


def kick_ziel(p):
    # Eine synthetische Sinus-Kick ordnet Demucs der Bass-Spur zu (Probe 14.11.); Library-Kicks bleiben in den Drums
    k = p['kick']
    return {'f_end_hz': median(k['f_end_hz']), 'abfall_20db_ms': median(k['abfall_20db_ms']),
            'obertoene_db': median(p['stil_merkmale']['kick_obertoene_db'])}


def rumble_bauen(p, grundton_pc, aus, drive):
    hz = 440 * 2 ** ((kl.rumble_midi(grundton_pc) - 69) / 12)
    a = SimpleNamespace(hz=hz, laenge=median(p['bass']['abfall_12db_ms']) * 2, hall=0.3, drive=drive)
    tb.schreiben(tb.rumble(a), str(aus))
    return a


def klang_ziel(stil, p, rolle):
    """Zielmerkmale je Rolle fuer die Sample-Wahl (Bibliothek) und die Synthese im Track."""
    sm_ = p['stil_merkmale']
    rauh, hell = median(sm_['rauheit_db']), median(sm_['synth_hell_hz'])
    return {'kick': kick_ziel(p),
            'hat': {'rauheit_db': rauh + (2 if stil == 'raw' else 0), 'hell_hz': kl.hat_hell(stil), 'dauer_max': 150},
            'openhat': {'rauheit_db': rauh, 'hell_hz': 6000, 'dauer_min': 250},
            'perc': {'hell_hz': 600, 'dauer_max': 300},
            'synth': {'hell_hz': hell, 'dauer_min': 400} if stil == 'deep' else {'hell_hz': hell, 'rauheit_db': rauh, 'dauer_max': 450},
            'pad': {'hell_hz': hell, 'dauer_min': 1500}}[rolle]


def waehle(rolle, ziel, rng, top=5, stil=None):
    """Zufall unter den top besten Samples der Rangliste."""
    beste = rangliste(rolle, ziel, stil)[:top]
    return beste[int(rng.integers(len(beste)))]


# deep soll harmonisch bleiben (Buch: Dub/Melodic statt Warehouse/Industrial): harte Genre-Ordner und verzerrte Samples meiden
MEIDEN = {'deep': re.compile(r'[\\/](Hard Techno|Industrial Techno|Rave Techno|Acid Techno|Synthwave)[\\/]|distort|crunch|dirty|noise|saturat', re.I)}


def rangliste(rolle, ziel, stil=None):
    """Samples nach gewichtetem Abstand zum Ziel (nur angegebene Merkmale), bestes zuerst."""
    v = [s for s in sm.vorrat(rolle) if not UNPASSEND.search(Path(s['pfad']).stem)]
    if stil in MEIDEN:
        v = [s for s in v if not MEIDEN[stil].search(s['pfad'])] or v
    if 'dauer_max' in ziel:
        v = [s for s in v if s['dauer_ms'] <= ziel['dauer_max']] or v
    if 'dauer_min' in ziel:
        v = [s for s in v if s['dauer_ms'] >= ziel['dauer_min']] or v
    if 'f_end_hz' in ziel:
        v = [s for s in v if s.get('f_end_hz') and s.get('abfall_20db_ms')]
    def abstand(s):
        d = 0.0
        if 'f_end_hz' in ziel:
            d += abs(np.log2(s['f_end_hz'] / ziel['f_end_hz'])) * 2 + abs(s['abfall_20db_ms'] - ziel['abfall_20db_ms']) / 60
        if 'obertoene_db' in ziel:
            d += abs(s['obertoene_db'] - ziel['obertoene_db']) / 4
        if 'hell_hz' in ziel:
            d += abs(np.log2(max(s['hell_hz'], 50) / ziel['hell_hz']))
        if 'rauheit_db' in ziel:
            d += abs(s['rauheit_db'] - ziel['rauheit_db']) / 3
        return d
    return sorted(v, key=abstand)


def transponieren(s, pc):
    # Simpler-Note 60 = Originaltonhoehe; Versatz so, dass der Sample-Grundton auf die Tonart faellt (hoechstens +-6)
    return ((pc - round(s['grundton_midi']) % 12 + 6) % 12) - 6


def motiv(stil, rng, basis, akkord=None):
    st = STUFEN[stil]
    if stil == 'hypnotic':
        # 1 Takt, 5-7 Schlaege bevorzugt auf x.25/x.75: ein Loop, der ueber den ganzen Track traegt
        lagen = sorted(rng.choice(16, size=int(rng.integers(5, 8)), replace=False, p=np.where(np.arange(16) % 2, 2, 1) / 24))
        return [[i * 0.25, 0.2, int(rng.integers(85, 115)), basis + int(rng.choice(st))] for i in lagen]
    if stil == 'raw':
        lagen = sorted(rng.choice(32, size=int(rng.integers(3, 6)), replace=False))
        return [[i * 0.25, 0.15, int(rng.integers(95, 127)), basis + int(rng.choice(st))] for i in lagen]
    # deep: Dub-Akkord auf x.75 von Beat 1 und 3, dazu ein leiser Nachschlag, knapp hinter dem Raster wie von Hand gespielt
    return [[pos + 0.02, 0.4, v, basis + s] for pos, v in ((0.75, 110), (2.75, 100), (3.75, 70)) for s in akkord or st]


# Dub-Akkorde: Moll7, Moll7 mit der Septime im Bass, iv7, Moll7 hoch gelegt; alle halten Grundton oder Moll-Terz des Pads
DEEP_AKKORDE = {'A': [0, 3, 7, 10], 'B': [-2, 3, 7, 10], 'C': [-7, -4, 0, 3], 'D': [3, 7, 10, 12]}
# Dub-Kette nach Buch, in Live-Intro-Geraeten: Mulm raus, Hoehen zu, punktierte Achtel mit dunklen Echos, wenig Hall
DEEP_AKKORD_FX = [{'name': 'EQ Three', 'werte': {'GainLo': -15, 'GainMid': -4}},
                  {'name': 'Auto Filter', 'werte': {'Frequency': 3000, 'Resonance': 10}},
                  {'name': 'Delay', 'werte': {'L 16th': 3, 'Feedback': 35, 'Filter Freq': 1200, 'Dry/Wet': 30}},
                  {'name': 'Reverb', 'werte': {'Decay Time': 3, 'Dry/Wet': 18}}]
DEEP_PAD_FX = [{'name': 'EQ Three', 'werte': {'GainLo': -15}},
               {'name': 'Auto Filter', 'werte': {'Frequency': 700, 'Resonance': 20, 'LFO Amount': 3, 'LFO Frequency': 0.2}},
               {'name': 'Reverb', 'werte': {'Decay Time': 4.4, 'Dry/Wet': 19}}]


def variante(noten, rng, basis, stil):
    n = [list(x) for x in noten]
    i = int(rng.integers(len(n)))
    n[i][3] = basis + int(rng.choice(STUFEN[stil]))
    return n


def abschnitte(p, stil, rng, bpm, minuten=None):
    """Abschnittsfolge aus dem Profil: Laenge = Median der Bloecke (oder minuten), Breaks nach haeufigster Anzahl (mind. 1)."""
    ziel = int(round(minuten * bpm / 4 / 8)) * 8 if minuten else int(median(p['arrangement']['bloecke'])) * 8
    while not minuten and ziel * 4 / bpm < 5.2:
        ziel += 8
    br = p['arrangement']['breaks_je_track']
    n_breaks = max(1, int(max(br, key=lambda k: br[k])))
    folge = [('Intro', 16, 'intro'), ('Aufbau', 16, 'aufbau'), ('Groove A1', 16, 'a1'), ('Groove A2', 16, 'a2'),
             ('Break 1', 8, 'break'), ('Groove B1', 16, 'b1'), ('Groove B2', 16, 'b2')]
    if n_breaks >= 2:
        folge.append(('Break 2', 8, 'break2'))
    folge += [('Peak', 16, 'peak'), ('Groove C', 8, 'c'), ('Outro', 16, 'outro')]
    for weg in ('Groove C', 'Break 2', 'Groove B2', 'Groove A2', 'Aufbau'):
        if sum(b for _, b, _ in folge) <= ziel:
            break
        folge = [x for x in folge if x[0] != weg]
    dehnbar = ['Groove A2', 'Peak', 'Groove B1', 'Groove C', 'Groove A1', 'Groove B2']
    dehnbar = [n for n in dehnbar if any(a == n for a, _, _ in folge)]
    for i in range(200):
        rest = ziel - sum(b for _, b, _ in folge)
        if rest <= 0:
            break
        if all(b >= 32 for a, b, _ in folge if a in dehnbar):
            # lange Tracks: weitere Groove-Abschnitte vor dem Peak (arrangement-check erlaubt hoechstens 32 Takte am Stueck)
            k = sum(a.startswith('Groove D') for a, _, _ in folge)
            folge.insert([a for a, _, _ in folge].index('Peak'), (f'Groove D{k + 1}', min(16, rest), 'b1' if k % 2 else 'b2'))
            continue
        n = dehnbar[i % len(dehnbar)]
        folge = [(a, b + 8 if a == n and b + 8 <= 32 else b, r) for a, b, r in folge]
    return folge


# Besetzung je Abschnittsrolle: Spur -> Pattern (None = Spur pausiert)
BESETZUNG = {
    'intro':  {'Kick': 'A', 'Hat': 'A'},
    'aufbau': {'Kick': 'A', 'Hat': 'A', 'Rumble': 'A'},
    'a1':     {'Kick': 'A', 'Hat': 'A', 'Rumble': 'A', 'Perc': 'A', 'Synth': 'A'},
    'a2':     {'Kick': 'A', 'Hat': 'A', 'Hat 2': 'A', 'Rumble': 'A', 'Perc': 'A', 'Synth': 'A', 'Pad': 'A'},
    'break':  {'Hat': 'A', 'Synth': 'A', 'Pad': 'A'},
    'b1':     {'Kick': 'A', 'Hat': 'B', 'Hat 2': 'A', 'Rumble': 'A', 'Perc': 'A', 'Synth': 'B', 'Pad': 'A'},
    'b2':     {'Kick': 'A', 'Hat': 'B', 'Rumble': 'A', 'Perc': 'A', 'Synth': 'B'},
    'break2': {'Synth': 'B', 'Pad': 'A'},
    'peak':   {'Kick': 'A', 'Hat': 'A', 'Hat 2': 'A', 'Rumble': 'A', 'Perc': 'A', 'Synth': 'A', 'Pad': 'A'},
    'c':      {'Kick': 'A', 'Hat': 'B', 'Hat 2': 'A', 'Rumble': 'A', 'Synth': 'B'},
    'outro':  {'Kick': 'A', 'Hat': 'A', 'Rumble': 'A'},
}
# raw ohne Synth und Pad: Wechsel je Abschnitt tragen Rumble, Open Hat, Perc und das Hat-Muster
RAW_BESETZUNG = {
    'intro':  {'Kick': 'A', 'Hat': 'A'},
    'aufbau': {'Kick': 'A', 'Hat': 'A', 'Rumble': 'A'},
    'a1':     {'Kick': 'A', 'Hat': 'A', 'Rumble': 'A', 'Perc': 'A'},
    'a2':     {'Kick': 'A', 'Hat': 'B', 'Hat 2': 'A', 'Rumble': 'A', 'Perc': 'A'},
    'break':  {'Hat': 'A', 'Hat 2': 'A'},
    'b1':     {'Kick': 'A', 'Hat': 'B', 'Hat 2': 'A', 'Rumble': 'A', 'Perc': 'A'},
    'b2':     {'Kick': 'A', 'Hat': 'A', 'Rumble': 'A'},
    'break2': {'Hat 2': 'A', 'Perc': 'A'},
    'peak':   {'Kick': 'A', 'Hat': 'B', 'Hat 2': 'A', 'Rumble': 'A', 'Perc': 'A'},
    'c':      {'Kick': 'A', 'Hat': 'A', 'Hat 2': 'A', 'Rumble': 'A'},
    'outro':  {'Kick': 'A', 'Hat': 'A', 'Rumble': 'A'},
}
RAMPE = {'intro': [0.8, 1], 'aufbau': [0.5, 1], 'break': [0.6, 1], 'break2': [0.6, 1], 'outro': [1, 0.7]}
SPUREN = ('Kick', 'Rumble', 'Hat', 'Hat 2', 'Perc', 'Synth', 'Pad')
SYNTH_WECHSEL = ['A', 'C', 'B', 'D']
QUELLEN = ('library', 'synth')


def rezept(stil, seed, bpm=None, quelle='library', minuten=None, nur=None, takte=None, aus=None):
    """Song-Spec fuer build.mjs. nur + takte = Komponente: nur diese Spuren, ein Abschnitt 'Loop' mit takte Takten."""
    rng = np.random.default_rng(seed)
    p = kl.profil(stil)
    lo, mitte, hi = p['bpm']['quartile']
    # deep/hypnotic-Referenzen laufen 144-148 BPM: obere Haelfte statt Q1-Q3
    bpm = bpm or int(round(rng.uniform(lo, hi) if stil == 'raw' else rng.uniform(mitte, hi + 2)))
    gt = p['tonart']['grundton']
    pc = NOTEN.index(rng.choice(list(gt), p=np.array(list(gt.values())) / sum(gt.values())))
    # deep immer Moll: Dub-Akkorde in Dur klangen zu wenig deep
    moll = stil == 'deep' or rng.random() < p['tonart']['moll_anteil']
    name = f'{stil.capitalize()} {bpm} s{seed}' + (f" {'+'.join(nur)} {takte}T" if nur else '')
    ordner = Path(aus or Path.home() / 'Music') / name
    (ordner / 'Sounds').mkdir(parents=True, exist_ok=True)
    # raw = roh, weniger ist mehr; Synth erst ab deep (auf Wunsch per --nur auch in raw)
    gewollt = set(nur or [s for s in SPUREN if not (stil == 'raw' and s == 'Synth')])

    def klang(rolle, ziel, synth_rolle, ton=None):
        # deep-Akkorde und Flaeche immer aus der Synthese: Bibliotheks-Stabs sind oft selbst Akkorde, gestapelt wird das Krawall
        if quelle == 'library' and not (stil == 'deep' and synth_rolle in ('synth', 'pad')):
            return waehle(rolle, ziel, rng, stil=stil)
        # Im Track misst die Pruefung die Synth-Kick nach Demucs 4-7 dB dumpfer als einzeln (raw s2, raw s125, deep s2 v4)
        anders = {'obertoene_db': ziel['obertoene_db'] + KICK_DEMUCS_VERLUST_DB} if synth_rolle == 'kick' else None
        x, m, par = kl.erzeugen(stil, synth_rolle, seed=int(rng.integers(1_000_000)), ton=ton, p=p, ziel_anders=anders)
        datei = ordner / 'Sounds' / f'{name} {synth_rolle}.wav'
        tb.schreiben(x, str(datei))
        return {'pfad': str(datei), **m, **({'f_end_hz': par['f_end_hz']} if 'f_end_hz' in par else {})}

    k = klang('kick', klang_ziel(stil, p, 'kick'), 'kick')
    rumble_datei = ordner / 'Sounds' / f'{name} Rumble.wav'
    r = rumble_bauen(p, pc, rumble_datei, RUMBLE_DRIVE[stil])
    tracks = {}

    def spur(n, sample, volume, patterns, effekte=(), simpler=None):
        if n in gewollt:
            tracks[n] = {'name': n, 'sample': str(sample), 'volume': volume, 'patterns': patterns, 'effekte': list(effekte),
                         'simpler': simpler or {}}

    # Kick auf die Tonart stimmen (Buch); mehr als 3 Halbtoene verbiegt Abfall und Druck einer Sample-Kick
    kick_ton = 60 + (transponieren(k, pc) if quelle == 'library' and abs(transponieren(k, pc)) <= 3 else 0)
    spur('Kick', k['pfad'], -11, {'A': {'bars': 1, 'notes': [[b, 0.5, 120 if b % 2 == 0 else 116, kick_ton] for b in range(4)]}})
    bass = p['bass']['cluster'][0]
    if bass['muster'].count('x') == 0:
        bass = next((c for c in p['bass']['cluster'] if 'x' in c['muster']), bass)
    rumble_noten = [n for n in noten_aus_muster(bass['zentrum_db'], laenge=0.22) if n[0] % 1 != 0]  # nie auf der Kick
    # Referenzen: Rumble im Bass-Stem rund 10 dB unter dem Kick-Sub; lauter frisst es die Dynamik im Limiter
    spur('Rumble', rumble_datei, -24, {'A': {'bars': 1, 'notes': rumble_noten}})
    hats = p['drums']['hat']['cluster']
    hat_a = next((c for c in hats if 'x' in c['muster']), hats[0])
    hat_b = next((c for c in hats if 'x' in c['muster'] and c is not hat_a), hat_a)
    if stil == 'deep':
        # Deep-Tracks haben kaum feste Hats: leise 16tel-Textur, Offbeat etwas lauter
        weich = [[i * 0.25, 0.1, 70 if i % 4 == 2 else 45] for i in range(16)]
        hat_noten, hat_b_noten = weich, [x for x in weich if x[0] % 0.5 == 0]
    else:
        hat_noten = noten_aus_muster(hat_a['zentrum_db'], laenge=0.1)
        hat_b_noten = noten_aus_muster(hat_b['zentrum_db'], laenge=0.1)
        if hat_b_noten == hat_noten:
            hat_b_noten = hat_noten + [[3.75, 0.1, 70]]
    if 'Hat' in gewollt:
        hat = klang('hat', klang_ziel(stil, p, 'hat'), 'hat')
        # deep/hypnotic-Referenzen: Hochton 5 dB leiser als bisher
        spur('Hat', hat['pfad'], -22 if stil == 'raw' else -26,{'A': {'bars': 1, 'notes': hat_noten}, 'B': {'bars': 1, 'notes': hat_b_noten}})
    if 'Hat 2' in gewollt:
        hat2 = klang('hat', klang_ziel(stil, p, 'openhat'), 'openhat')
        spur('Hat 2', hat2['pfad'], -18 if stil == 'raw' else -22,{'A': {'bars': 2, 'notes': [[3.5, 0.3, 90], [7.5, 0.3, 100]]}})
    off = [c for c in p['drums']['perc']['cluster'] if any(ch == 'x' and i % 4 for i, ch in enumerate(c['muster']))]
    if (off or nur or stil == 'raw') and 'Perc' in gewollt:
        perc_noten = [n for n in noten_aus_muster(off[0]['zentrum_db'], laenge=0.15) if n[0] % 1 != 0] if off else \
            [[b + 0.75, 0.15, 100] for b in range(4)]
        perc = klang('perc', klang_ziel(stil, p, 'perc'), 'perc')
        spur('Perc', perc['pfad'], -22, {'A': {'bars': 1, 'notes': perc_noten}})
    if 'Synth' in gewollt:
        synth = klang('synth', klang_ziel(stil, p, 'synth'), 'synth', pc + 48)
        basis = 60 + transponieren(synth, pc)
        bars = 2 if stil == 'raw' else 1
        if stil == 'deep':
            muster = {k: {'bars': 1, 'notes': motiv(stil, rng, basis, akk)} for k, akk in DEEP_AKKORDE.items()}
        else:
            a = motiv(stil, rng, basis)
            muster = {'A': {'bars': bars, 'notes': a}, 'B': {'bars': bars, 'notes': variante(a, rng, basis, stil)}}
            if stil == 'raw':  # raw wechselt das Motiv je Abschnitt, sonst gleichen sich alle 8-Takt-Bloecke (Wiederholung > Q3)
                muster |= {k: {'bars': bars, 'notes': motiv(stil, rng, basis)} for k in ('C', 'D')}
        deep = stil == 'deep'
        spur('Synth', synth['pfad'], {'raw': -24, 'deep': -17, 'hypnotic': -20}[stil], muster,
             DEEP_AKKORD_FX if deep else (), {'Ve Release': 200} if deep else None)
    if (stil == 'deep' or nur) and 'Pad' in gewollt:
        pad = klang('pad', klang_ziel(stil, p, 'pad'), 'pad', pc + 48)
        # eine Oktave hoeher als der Grundton: um 130 Hz zaehlt Demucs das Pad zum Bass, dann fehlt die Flaeche im other-Stem
        pb = 60 + transponieren(pad, pc)
        terz = 3 if moll else 4
        # Grundton und Terz als Halteflaeche; die Akkordwechsel traegt der Synth (DEEP_AKKORDE), sonst reiben sich beide
        pad_muster = {'bars': 4, 'notes': [[0, 7.9, 90, pb], [8, 7.9, 85, pb + terz]]}
        spur('Pad', pad['pfad'], -20, {'A': pad_muster}, DEEP_PAD_FX if stil == 'deep' else ())

    if nur:
        folge = [('Loop', takte, 'peak')]
    else:
        folge = abschnitte(p, stil, rng, bpm, minuten)
    for t in tracks.values():
        t['play'] = {}
    synth_folge = iter(SYNTH_WECHSEL * len(folge))
    for sec, _, rolle in folge:
        besetzung = (RAW_BESETZUNG if stil == 'raw' else BESETZUNG)[rolle]
        # deep-Tracks der Sammlung haben die Flaeche durchgehend unter dem Synth (synth_flaeche_db Median -9 dB)
        if stil == 'deep' and 'Synth' in besetzung:
            besetzung = {**besetzung, 'Pad': 'A'}
        for n, pat in besetzung.items():
            if n == 'Synth' and 'C' in tracks.get('Synth', {}).get('patterns', {}):
                pat = next(synth_folge)
            if n in tracks:
                tracks[n]['play'][sec] = {'pattern': pat, 'vel': RAMPE[rolle]} if rolle in RAMPE else pat
    spec = {'name': name, 'bpm': bpm, 'sections': [{'name': a, 'bars': b} for a, b, _ in folge],
            'tracks': [t for t in tracks.values() if t['play']]}
    info = {'stil': stil, 'seed': seed, 'quelle': quelle, 'tonart': f"{NOTEN[pc]} {'Moll' if moll else 'Dur'}",
            'kick': {x: k.get(x) for x in ('f_end_hz', 'abfall_20db_ms', 'obertoene_db')}, 'rumble': vars(r),
            'samples': {t['name']: Path(t['sample']).name for t in spec['tracks']}}
    pfad = ordner / f'{name}.json'
    pfad.write_text(json.dumps(spec, ensure_ascii=False, indent=1), 'utf8')
    (ordner / 'rezept-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=1), 'utf8')
    return pfad, spec, info


def _selbsttest():
    assert noten_aus_muster([-20, 0, -3, -9]) == [[0.25, 0.2, 127], [0.5, 0.2, 107]]
    assert transponieren({'grundton_midi': 45.1}, 9) == 0 and transponieren({'grundton_midi': 45}, 3) == -6
    p = kl.profil('raw')
    rng = np.random.default_rng(1)
    for minuten in (3, 5.4, 9):
        takte = sum(b for _, b, _ in abschnitte(p, 'raw', rng, 142, minuten))
        assert abs(takte * 4 / 142 - minuten) < 0.5, (minuten, takte)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    _selbsttest()
    ap = argparse.ArgumentParser()
    ap.add_argument('stil', choices=['raw', 'deep', 'hypnotic'])
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--bpm', type=int, default=None)
    ap.add_argument('--quelle', choices=QUELLEN, default=None, help='Standard: library, wenn vermessen, sonst synth')
    ap.add_argument('--minuten', type=float, default=None, help='Tracklaenge statt Median der Sammlung')
    ap.add_argument('--nur', default=None, help=f"Komponente: Spuren mit Komma, aus {', '.join(SPUREN)}")
    ap.add_argument('--takte', type=int, default=32, help='Laenge der Komponente')
    ap.add_argument('--aus', default=None, help='Basisordner (Standard: ~/Music)')
    a = ap.parse_args()
    nur = [n.strip() for n in a.nur.split(',')] if a.nur else None
    if nur and not set(nur) <= set(SPUREN):
        ap.error(f'unbekannte Spur: {set(nur) - set(SPUREN)}')
    quelle = a.quelle or ('library' if sm.CACHE.exists() else 'synth')
    seed = a.seed if a.seed is not None else int(np.random.default_rng().integers(1000))
    pfad, spec, info = rezept(a.stil, seed, a.bpm, quelle, a.minuten, nur, a.takte if nur else None, a.aus)
    takte = sum(s['bars'] for s in spec['sections'])
    print(f"{pfad}\n{spec['bpm']} BPM, {info['tonart']}, {takte} Takte = {takte * 4 / spec['bpm']:.1f} min, Quelle {quelle}, Kick {info['kick']}")
    for n, s in info['samples'].items():
        print(f'  {n}: {s}')
