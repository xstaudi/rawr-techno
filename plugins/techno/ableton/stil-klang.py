"""Erzeugt One-Shots je Rolle aus den Stil-Werten, ohne fremde Samples (frei teilbar).

Aufruf: python -I -W ignore stil-klang.py <raw|deep|hypnotic> <kick|rumble|hat|openhat|perc|synth|pad> [--seed N] [--aus ordner] [--ton E]
Je Aufruf entstehen KANDIDATEN Varianten; gemessen wird wie bei Library-Samples (sample-merkmale.merkmale), behalten wird
die Variante mit dem kleinsten Abstand zum Stil-Ziel. Ausgabe: WAV plus Messwerte als JSON-Zeile.
"""
import argparse, importlib.util, json, os, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from scipy.signal import butter, sosfilt

HIER = Path(__file__).parent


def _modul(name, datei):
    s = importlib.util.spec_from_file_location(name, HIER / datei)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


tb = _modul('tb', 'tiefton-bauen.py')
sm = _modul('sm', 'sample-merkmale.py')
SR = tb.SR
NOTEN = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
ROLLEN = ('kick', 'rumble', 'hat', 'openhat', 'perc', 'synth', 'pad')
KANDIDATEN = 24
# 808-Metall: sechs Rechtecke mit unharmonischen Abstaenden ergeben den typischen Hat-Klang
METALL_HZ = np.array([205.3, 304.4, 369.6, 522.7, 540.0, 800.0])


def profil_ordner():
    # Reihenfolge: TECHNO_PROFILE, vermessene eigene Sammlung, mitgelieferte Profile (nur Zahlen, ohne Tracknamen)
    for o in (os.environ.get('TECHNO_PROFILE'), sm.EIG / '_Stems', HIER / 'profile'):
        if o and (Path(o) / '_profil-raw.json').exists():
            return Path(o)
    raise SystemExit('Kein Stil-Profil gefunden (TECHNO_PROFILE setzen)')


def profil(stil, ordner=None):
    return json.loads((Path(ordner or profil_ordner()) / f'_profil-{stil}.json').read_text('utf8'))


def hz(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def filt(x, art, f):
    return sosfilt(butter(2 if art != 'band' else 2, f, art, fs=SR, output='sos'), x)


def zeit(ms):
    return np.arange(int(ms / 1000 * SR)) / SR


def saege(f, t, rng, stimmen=3, verstimmt=0.12):
    # verstimmte Saegezaehne (in Halbtoenen), Phase zufaellig: breiter, lebendiger Ton
    x = np.zeros(len(t))
    for v in np.linspace(-verstimmt, verstimmt, stimmen):
        ph = rng.random() + np.cumsum(np.full(len(t), f * 2 ** (v / 12))) / SR
        x += 2 * (ph % 1) - 1
    return x / stimmen


def rumble_midi(pc):
    # 36-72 Hz wie in den Referenztracks; frueher 62-124 Hz fuer saubere Demucs-Trennung, das droehnte im Oberbass
    return pc + (36 if pc < 2 else 24)


def hat_hell(stil):
    # echte kurze Hats der Library: Schwerpunkt 9-10 kHz; tiefer (5-6 kHz) liegt die Energie bei 2-5 kHz und klingt schrill
    return {'raw': 8000, 'deep': 7500, 'hypnotic': 8000}[stil]


def ziele(stil, p):
    sm_ = p['stil_merkmale']
    rauh, hell = sm_['rauheit_db'][1], sm_['synth_hell_hz'][1]
    return {
        'kick': {'obertoene_db': sm_['kick_obertoene_db'][1], 'abfall_20db_ms': p['kick']['abfall_20db_ms'][1]},
        'hat': {'hell_hz': hat_hell(stil),'rauheit_db': rauh + (2 if stil == 'raw' else 0), 'dauer_ms': 90},
        'openhat': {'hell_hz': 8000, 'rauheit_db': rauh, 'dauer_ms': 350},
        'perc': {'hell_hz': 600, 'dauer_ms': 180},
        'synth': {'hell_hz': hell, 'dauer_ms': 900} if stil == 'deep' else {'hell_hz': hell, 'rauheit_db': rauh, 'dauer_ms': 250},
        'pad': {'hell_hz': hell, 'dauer_ms': 2500},
    }


def kick(p, stil, rng):
    k = p['kick']
    a = SimpleNamespace(f_start=k['f_start_hz'][1] * rng.uniform(.85, 1.15), f_end=k['f_end_hz'][1] * rng.uniform(.9, 1.1),
                        tau=k['pitch_tau_ms'][1] * rng.uniform(.7, 1.3), halten=rng.uniform(10, 30),
                        abfall=k['abfall_20db_ms'][1] * rng.uniform(.5, 1.05), klick=0.12,
                        drive=float(rng.choice([1.5, 2, 3, 4, 6])))
    x = tb.kick(a)
    t = np.arange(len(x)) / SR
    # Knack bei 1,5 kHz plus Rauschen 2-8 kHz: ohne ihn legt Demucs eine Sinus-Kick in den Bass-Stem (Probe 14.11.)
    # mehr Knack statt mehr Drive fuer helle Kicks: Drive ueber 6 verschiebt die gemessene Kick-Tonhoehe im Track auf einen Oberton
    knack = rng.uniform(.2, 1.6) * np.sin(2 * np.pi * 1500 * t) * np.exp(-t / .004)
    rausch = filt(rng.standard_normal(len(t)), 'band', [2000, 8000])
    x = x + knack + rng.uniform(.15, .7) * rausch / np.abs(rausch).max() * np.exp(-t / .003)
    return x, {'f_end_hz': round(a.f_end, 1), 'drive': a.drive}


def rumble(p, stil, rng, ton):
    a = SimpleNamespace(hz=hz(ton), laenge=p['bass']['abfall_12db_ms'][1] * 2 * rng.uniform(.8, 1.2),
                        hall=rng.uniform(.2, .4), drive={'raw': 3, 'deep': 1.5, 'hypnotic': 2}[stil])
    return tb.rumble(a), {'hz': round(a.hz, 1)}


def hat(p, stil, rng, offen=False):
    t = zeit(rng.uniform(300, 600) if offen else rng.uniform(60, 160))
    metall = sum(np.sign(np.sin(2 * np.pi * f * rng.uniform(.97, 1.03) * t + rng.random() * 6)) for f in METALL_HZ * rng.uniform(1.5, 3))
    rausch = rng.standard_normal(len(t))
    mix = rng.uniform(.3, 1)
    x = mix * rausch / rausch.std() + (1 - mix) * metall / metall.std()
    # Hochpass ab 4 kHz: darunter klingeln die Metall-Obertoene bei 2-3 kHz, wo das Ohr am empfindlichsten ist
    # Tiefpass bis 12 kHz: raw-Sammlung liegt ueber 12 kHz rund 8 dB unter offenen Synth-Hats (Zischen)
    x = filt(filt(x, 'highpass', rng.uniform(4000, 7500)), 'lowpass', min(rng.uniform(8000, 12000), SR / 2 - 100))
    abfall = len(t) / SR / 4
    return tb.saettigen(x * np.exp(-t / abfall), float(rng.choice([1, 2, 4, 8]))), {'mix': round(mix, 2)}


def perc(p, stil, rng):
    t = zeit(rng.uniform(150, 350))
    f0 = rng.uniform(250, 700)
    ton = np.sin(2 * np.pi * np.cumsum(f0 * (1 + .5 * np.exp(-t / .01))) / SR)
    x = ton * np.exp(-t / (len(t) / SR / 5)) + .3 * filt(rng.standard_normal(len(t)), 'band', [f0, f0 * 4]) * np.exp(-t / .01)
    return tb.saettigen(x, 1.5), {'hz': round(f0)}


def dub_echo(x, verz=.32, rueck=.45, n=4):
    # jedes Echo dunkler als das vorige, wie ein Band-Delay; nur fuer den Einzelsound, im Track macht das Live-Delay
    d = int(verz * SR)
    y = np.concatenate([x, np.zeros(d * n)])
    echo = x
    for k in range(1, n + 1):
        echo = filt(echo, 'lowpass', 1500) * rueck
        y[k * d:k * d + len(echo)] += echo
    return y


def synth(p, stil, rng, ton):
    # deep soll harmonisch sein, kein Krawall -> weich gefiltert, kaum Saettigung, kein Rauschen, Dub-Echo
    weich = stil == 'deep'
    t = zeit(rng.uniform(500, 900) if weich else rng.uniform(150, 400))
    x = saege(hz(ton), t, rng)
    # Filterhuelle: offen beim Anschlag, dann zu; Grenzfrequenz bestimmt die Helligkeit
    grenze = rng.uniform(300, 1200) if weich else rng.uniform(400, 8000)
    stuecke = np.array_split(np.arange(len(t)), 24)
    y = np.concatenate([filt(x, 'lowpass', min(grenze * (1 + 3 * np.exp(-t[s[0]] / .05)), SR / 2 - 100))[s] for s in stuecke])
    rausch = 0 if weich else rng.uniform(0, .3)
    y = (y + rausch * filt(rng.standard_normal(len(t)), 'highpass', 2000)) * np.exp(-t / (len(t) / SR / 3))
    drive = float(rng.choice([1, 1.5, 2] if weich else [1, 2, 4, 8, 16]))
    return tb.saettigen(y, drive), {'grenze_hz': round(grenze), 'drive': drive}


def pad(p, stil, rng, ton):
    t = zeit(3500)
    x = saege(hz(ton), t, rng, stimmen=5, verstimmt=.2)
    # Hochpass: Pad-Grundton um 130 Hz machte deep im Unterbau matschig (Referenz 26 dB weniger bei 120-250 Hz)
    x = filt(filt(x, 'lowpass', rng.uniform(400, 4000)), 'highpass', 200)
    hull = np.minimum(t / rng.uniform(.3, .8), 1) * np.minimum((t[-1] - t) / .8, 1)
    return x * hull, {}


def abstand(m, ziel):
    d = 0.0
    if 'hell_hz' in ziel:
        d += abs(np.log2(max(m['hell_hz'], 50) / ziel['hell_hz']))
    if 'rauheit_db' in ziel:
        d += abs(m['rauheit_db'] - ziel['rauheit_db']) / 3
    if 'dauer_ms' in ziel:
        d += abs(np.log2(max(m['dauer_ms'], 5) / ziel['dauer_ms'])) / 2
    if 'obertoene_db' in ziel:
        d += abs(m['obertoene_db'] - ziel['obertoene_db']) / 4
    if 'abfall_20db_ms' in ziel:
        d += abs(m['abfall_20db_ms'] - ziel['abfall_20db_ms']) / 60
    return d


def messen(x, rolle):
    m = sm.merkmale(np.interp(np.arange(0, len(x), SR / sm.SR), np.arange(len(x)), x))
    if rolle == 'kick':
        k = np.pad(x, (0, max(0, int(.35 * SR) - len(x))))[:int(.35 * SR)]
        m['obertoene_db'] = round(sm.kick_obertoene(k, SR), 1)
        m['abfall_20db_ms'] = sm._tt().huelle_abfall(k)['abfall_20db_ms'] or 350
    return m


def erzeugen(stil, rolle, seed=None, ton=None, p=None, ziel_anders=None):
    """Gibt (Signal, Messwerte, Parameter) der besten von KANDIDATEN Varianten zurueck; ton = MIDI-Note fuer tonale Rollen.
    ziel_anders ueberschreibt einzelne Zielwerte (z. B. fuer den Einsatz im Track)."""
    p = p or profil(stil)
    rng = np.random.default_rng(seed)
    if ton is None:
        gt = p['tonart']['grundton']
        pc = NOTEN.index(max(gt, key=gt.get))
        ton = rumble_midi(pc) if rolle == 'rumble' else pc + {'synth': 48, 'pad': 48}.get(rolle, 0)
    bauer = {'kick': lambda: kick(p, stil, rng), 'rumble': lambda: rumble(p, stil, rng, ton), 'hat': lambda: hat(p, stil, rng),
             'openhat': lambda: hat(p, stil, rng, offen=True), 'perc': lambda: perc(p, stil, rng),
             'synth': lambda: synth(p, stil, rng, ton), 'pad': lambda: pad(p, stil, rng, ton)}[rolle]
    ziel = {**ziele(stil, p).get(rolle, {}), **(ziel_anders or {})}
    beste = None
    for _ in range(KANDIDATEN if ziel else 1):
        x, par = bauer()
        x = x / np.max(np.abs(x))
        m = messen(x, rolle)
        d = abstand(m, ziel)
        if beste is None or d < beste[0]:
            beste = (d, x, m, par)
    _, x, m, par = beste
    if rolle in ('rumble', 'synth', 'pad'):
        m['grundton_midi'] = float(ton)  # gebaut auf diesem Ton; die Spektrum-Schaetzung irrt bei Saegezahn-Obertoenen
    return x, m, {**par, 'ton_midi': ton, 'ziel': ziel}


def _selbsttest():
    p = profil('raw')
    for rolle in ROLLEN:
        x, m, _ = erzeugen('raw', rolle, seed=1, p=p)
        assert len(x) > SR * .05 and np.isfinite(x).all() and np.abs(x).max() <= 1, rolle
    x, m, _ = erzeugen('raw', 'hat', seed=1, p=p)
    assert 3000 < m['hell_hz'] < 12000 and m['dauer_ms'] < 200, m
    assert all(36 <= hz(rumble_midi(pc)) < 72 for pc in range(12))


def aus_bibliothek(stil, rolle, seed, ton, anzahl, ordner):
    """anzahl verschiedene Samples aus den besten der Bibliothek nach Abstand zum Stil-Ziel; mit ton auf dessen Grundton gestimmt."""
    rz = _modul('rz', 'stil-rezept.py')  # erst hier: stil-rezept laedt selbst dieses Modul
    p = profil(stil)
    liste = rz.rangliste('hat' if rolle == 'openhat' else rolle, rz.klang_ziel(stil, p, rolle), stil)
    if not liste:
        raise SystemExit(f'Keine {rolle}-Samples in der Bibliothek ({sm.EIG}); Synthese mit --quelle synth')
    rng = np.random.default_rng(seed)
    beste = liste[:max(8, 3 * anzahl)]
    wahl = sorted(rng.choice(len(beste), size=min(anzahl, len(beste)), replace=False))
    for i, k in enumerate(wahl):
        s = beste[k]
        halb = rz.transponieren(s, ton % 12) if ton is not None and rolle in ('kick', 'synth', 'pad', 'perc') else 0
        datei = ordner / f'{stil.capitalize()} {rolle} s{seed}-{i + 1} {Path(s["pfad"]).stem}.wav'
        f = 2 ** (halb / 12)
        # wie Simpler ohne Warp: schneller abspielen hebt Ton und kuerzt das Sample
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', s['pfad'], '-af', f'aresample={SR},asetrate={SR * f:.3f},aresample={SR}',
                        str(datei)], check=True)
        m = {k_: v for k_, v in s.items() if k_ not in ('pfad', 'mtime')}
        yield {'datei': str(datei), 'stil': stil, 'rolle': rolle, 'quelle': 'library', 'seed': seed, 'original': s['pfad'],
               'halbtoene': halb, 'messwerte': m}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('stil', choices=['raw', 'deep', 'hypnotic'])
    ap.add_argument('rolle', choices=ROLLEN + ('selbsttest',))
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--ton', default=None, help='Grundton (z. B. E) oder MIDI-Note')
    ap.add_argument('--aus', default=str(Path.home() / 'Music' / 'RAWR Techno' / 'Sounds'))
    ap.add_argument('--anzahl', type=int, default=1, choices=range(1, 7), help='Vorschlaege zur Auswahl')
    ap.add_argument('--quelle', choices=['library', 'synth'], default=None, help='Standard: library, wenn vermessen; Rumble immer synth')
    a = ap.parse_args()
    if a.rolle == 'selbsttest':
        _selbsttest()
        print('selbsttest ok')
        sys.exit(0)
    seed = a.seed if a.seed is not None else int(np.random.default_rng().integers(1e6))
    if a.ton is None or a.ton.isdigit():
        ton = None if a.ton is None else int(a.ton)
    else:
        pc = NOTEN.index(a.ton.upper())
        ton = rumble_midi(pc) if a.rolle == 'rumble' else pc + 48
    ordner = Path(a.aus)
    ordner.mkdir(parents=True, exist_ok=True)
    quelle = a.quelle or ('library' if sm.CACHE.exists() and a.rolle != 'rumble' else 'synth')
    if quelle == 'library':
        for z in aus_bibliothek(a.stil, a.rolle, seed, ton, a.anzahl, ordner):
            print(json.dumps(z, ensure_ascii=False))
        sys.exit(0)
    for i in range(a.anzahl):
        x, m, par = erzeugen(a.stil, a.rolle, seed + i, ton)
        if a.stil == 'deep' and a.rolle == 'synth':
            x = dub_echo(x)
        datei = ordner / f'{a.stil.capitalize()} {a.rolle} s{seed + i}.wav'
        tb.schreiben(x, str(datei))
        print(json.dumps({'datei': str(datei), 'stil': a.stil, 'rolle': a.rolle, 'quelle': 'synth', 'seed': seed + i, 'messwerte': m,
                          'parameter': par}, ensure_ascii=False))
