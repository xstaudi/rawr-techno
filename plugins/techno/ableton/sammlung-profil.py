"""Muster ueber alle zerlegten Tracks: Tempo, Tonart, Lautheit, Kick, Bass- und Drum-Raster, Swing, Arrangement.

Aufruf: python -I sammlung-profil.py <_Stems-Ordner>
Liest je Track messwerte.json (sammlung-zerlegen.py, sammlung-raster.py), schreibt _profil.json und _profil.md in den Ordner.
"""
import importlib.util, json, sys
from collections import Counter
from pathlib import Path
import numpy as np
from scipy.cluster.vq import kmeans2
from scipy.stats import spearmanr

_spec = importlib.util.spec_from_file_location('sr', Path(__file__).parent / 'sammlung-raster.py')
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)
NOTEN = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
BAND_NAME = {'kick': 'Tief 40–250 Hz (Kick, Rumble im Drum-Stem)', 'perc': 'Perc 300–900 Hz', 'clap': 'Clap 1,2–3,5 kHz', 'hat': 'Hat 6–11 kHz'}
GM_NAME = {'kick_4_4': 'Kick auf jedem Beat', 'clap_2_4': 'Clap/Snare auf 2 und 4 (≥ 3 dB über 1 und 3)', 'offbeat_hat': 'Offbeat-Hat (x.5 ≥ 6 dB über x.25/x.75)', 'hats_16tel': 'durchlaufende 16tel-Hats', 'bass_zwischen_kicks': 'Bass am lautesten zwischen den Kicks'}
TREFFER_DB = -6  # Schlag zaehlt im Muster, wenn er hoechstens so weit unter dem lautesten des Bands liegt


def pc(note):
    """Tonklasse aus 'G#1 (-0.13)' oder 'A# Moll'."""
    if not note:
        return None
    n = note.split()[0].rstrip('0123456789-')
    return NOTEN.index(n) if n in NOTEN else None


def q(xs, p=(25, 50, 75), nk=1):
    xs = [x for x in xs if x is not None and not np.isnan(x)]
    return [round(float(v), nk) for v in np.percentile(xs, p)] if xs else None


TEMPO_GRUPPEN = {'unter 132': (0, 132), '132–139': (132, 139), '139–146': (139, 146), '146–152': (146, 152), 'ab 152': (152, 999)}


def geruest(vektoren, schwelle=TREFFER_DB, je_beat=False):
    """Anteil der Tracks (%) mit Schlag je 16tel; je_beat: die 4 Beats eines Takts zusammengefasst (Slot 0 = auf der Kick)."""
    X = np.array([v for v in vektoren if v], dtype=float) >= schwelle
    if not len(X):
        return None
    if je_beat:
        X = X.reshape(len(X), 4, 4).mean(1) >= 0.5  # Slot zaehlt, wenn er in mindestens 2 von 4 Beats sitzt
    return [int(round(v * 100)) for v in X.mean(0)]


def kennzahlen(r):
    """Grundmuster eines Tracks als Ja/Nein; Kick-Klick im Clap/Perc-Band faellt heraus, weil nur Beat gegen Beat verglichen wird."""
    m = {b: np.array(v, dtype=float) for b, v in r['muster'].items()}
    je_beat = lambda v: v.reshape(4, 4).mean(0)
    hat, tief = je_beat(m['hat']), je_beat(m['tief'] if 'tief' in m else m['kick'])
    k = {'kick_4_4': bool(tief[0] >= max(tief[1:]) - 1),
         'clap_2_4': bool((m['clap'][[4, 12]].mean() - m['clap'][[0, 8]].mean()) >= 3),
         'offbeat_hat': bool(hat[2] - max(hat[1], hat[3]) >= 6),
         'hats_16tel': bool(min(hat[1], hat[3]) >= hat[2] - 6)}
    if r.get('bass'):
        b = je_beat(np.array(r['bass']['pegel_je_16tel_db'], dtype=float))
        k['bass_zwischen_kicks'] = bool(int(np.argmax(b)) != 0)
        k['bass_slot'] = int(np.argmax(b))
    return k


def anteile(ks):
    return {f: round(100 * np.mean([k[f] for k in ks if f in k])) for f in ('kick_4_4', 'clap_2_4', 'offbeat_hat', 'hats_16tel', 'bass_zwischen_kicks')
            if any(f in k for k in ks)}


def schritte(v, schwelle=TREFFER_DB):
    return ''.join('x' if x >= schwelle else '.' for x in v)


def cluster(vektoren, namen, k_max=6, seed=7):
    """k-means auf 16-Schritt-Vektoren, k nach Ellbogen (Gewinn < 15 %); Rueckgabe Zentren und Zuordnung."""
    X = np.array(vektoren, dtype=float)
    rng = np.random.default_rng(seed)
    best, fehler_vor = None, None
    for k in range(1, min(k_max, len(X)) + 1):
        zen, lab = min((kmeans2(X, k, minit='points', seed=int(rng.integers(1e9))) for _ in range(5)),
                       key=lambda zl: ((X - zl[0][zl[1]]) ** 2).sum())
        fehler = ((X - zen[lab]) ** 2).sum()
        if fehler_vor is not None and fehler > fehler_vor * 0.85:
            break
        best, fehler_vor = (zen, lab), fehler
    zen, lab = best
    aus = []
    for c in range(len(zen)):
        mitglieder = [namen[i] for i in np.where(lab == c)[0]]
        if mitglieder:
            aus.append({'anteil': round(len(mitglieder) / len(X), 2), 'n': len(mitglieder),
                        'zentrum_db': [round(float(v), 1) for v in zen[c]], 'muster': schritte(zen[c]), 'beispiele': mitglieder[:4]})
    return sorted(aus, key=lambda a: -a['n'])


def arrangement(e):
    """Bloecke je 8 Takte (dB zur lautesten Kick-Energie): Intro bis zum ersten vollen Block, Breaks = Einbrueche unter -6 dB."""
    e = np.array(e)
    voll = np.where(e >= -3)[0]
    if not len(voll):
        return None
    intro = int(voll[0])
    breaks, i = [], intro
    while i < voll[-1]:
        if e[i] < -6:
            j = i
            while j < len(e) and e[j] < -6:
                j += 1
            breaks.append({'start_rel': round(i / len(e), 2), 'bloecke': j - i})
            i = j
        else:
            i += 1
    return {'bloecke': len(e), 'intro_bloecke': intro, 'outro_bloecke': len(e) - 1 - int(voll[-1]), 'breaks': breaks}


STILE = ('raw', 'deep', 'hypnotic')
KERN_GENRES = ('Techno (Raw / Deep / Hypnotic)', 'Techno', 'Techno (Peak Time / Driving)', '–')
STIL_FELDER = ('kick_obertoene_db', 'rauheit_db', 'synth_hell_hz', 'synth_flaeche_db', 'synth_wiederholung', 'synth_zu_drums_db')


def break_zahl(energie):
    x = np.array(energie)
    return int(np.sum((x[1:] < np.median(x) - 6) & (x[:-1] >= np.median(x) - 6)))


def geteilte_matrix(tracks):
    """Nur was stil_zuordnung braucht, ohne Namen, Energiekurve und Beatport-Untergenre, sortiert statt in Sammlungsreihenfolge."""
    felder = ('kick_obertoene_db', 'rauheit_db', 'synth_flaeche_db', 'synth_zu_drums_db', 'synth_hell_hz', 'synth_wiederholung')
    kern = [t for t in tracks if t.get('stil') and t.get('tags', {}).get('genre', '–') in KERN_GENRES and 130 <= t['bpm'] <= 150]
    zeilen = [{'bpm': 140, 'tags': {'genre': 'Techno'}, 'stil': {k: t['stil'].get(k) for k in felder},
               'bass_anteil_im_bassstem_db': t.get('bass_anteil_im_bassstem_db'), 'breaks': break_zahl(t['energie_8takte_db'])} for t in kern]
    return sorted(zeilen, key=lambda z: json.dumps(z, sort_keys=True, default=float))


def stil_zuordnung(tracks):
    """raw / deep / hypnotic je Kern-Track (Techno-Genres, 130-150 BPM) aus robusten z-Werten der Stil-Merkmale.
    Gewichte aus der Recherche (raw: verzerrte Kick, Rauschen, Rumble; deep: Flaechen, dunkel, Synth vorn;
    hypnotic: Wiederholung, wenig Breaks), am 14.11.2026 an Beispielen abgenommen."""
    kern = [t for t in tracks if t.get('stil') and t.get('tags', {}).get('genre', '–') in KERN_GENRES and 130 <= t['bpm'] <= 150]
    if len(kern) < 10:
        return {}
    def z(v):
        v = np.array(v, dtype=float)
        return (v - np.nanmedian(v)) / (np.nanpercentile(v, 75) - np.nanpercentile(v, 25) + 1e-9)
    col = lambda k: [np.nan if t['stil'][k] is None else t['stil'][k] for t in kern]
    # die geteilte Matrix traegt nur die Break-Zahl, nicht die Energiekurve (die koennte einen Track wiedererkennbar machen)
    breaks = [t['breaks'] if 'breaks' in t else break_zahl(t['energie_8takte_db']) for t in kern]
    werte = np.vstack([z(col('kick_obertoene_db')) + z(col('rauheit_db')) + z([t.get('bass_anteil_im_bassstem_db', np.nan) for t in kern]),
                       z(col('synth_flaeche_db')) + z(col('synth_zu_drums_db')) - z(col('synth_hell_hz')),
                       2 * np.nan_to_num(z(col('synth_wiederholung'))) - z(breaks)]).T / 3
    werte = np.nan_to_num(werte, nan=-9)
    for t, w in zip(kern, werte):
        t['_stil'] = STILE[int(np.argmax(w))]
        t['_stil_wert'] = [round(float(x), 2) for x in w]
    return {s: [t for t in kern if t['_stil'] == s] for s in STILE}


def stil_merkmale(tracks):
    return {k: q([t['stil'][k] for t in tracks if t['stil'][k] is not None]) for k in STIL_FELDER}


def typisch(tracks, s, n=5):
    i = STILE.index(s)
    return [t['_name'] for t in sorted(tracks, key=lambda t: -(t['_stil_wert'][i] - max(w for j, w in enumerate(t['_stil_wert']) if j != i)))[:n]]


def profil(tracks):
    p = {'n': len(tracks)}
    bpm = [t['bpm'] for t in tracks if t.get('bpm')]
    p['bpm'] = {'quartile': q(bpm), 'verteilung': dict(sorted(Counter(int(b // 2 * 2) for b in bpm).items()))}
    p['dauer_min'] = q([t['dauer_s'] / 60 for t in tracks])
    p['lufs'] = q([t.get('lufs') for t in tracks])
    sicher = [t for t in tracks if (t.get('tonart_sicherheit') or 0) >= 0.5]
    p['tonart'] = {'n_sicher': len(sicher), 'moll_anteil': round(np.mean(['Moll' in t['tonart'] for t in sicher]), 2) if sicher else None,
                   'grundton': dict(Counter(t['tonart'].split()[0] for t in sicher).most_common())}

    kick = [t for t in tracks if t.get('kick', {}).get('f_end_hz')]
    kw = lambda f: np.array([t['kick'].get(f) for t in kick], dtype=float)
    p['kick'] = {'n': len(kick), 'f_start_hz': q(kw('f_start_hz')), 'f_end_hz': q(kw('f_end_hz')), 'pitch_tau_ms': q(kw('pitch_tau_ms')),
                 'abfall_6db_ms': q(kw('abfall_6db_ms')), 'abfall_20db_ms': q(kw('abfall_20db_ms')),
                 'end_ton': dict(Counter(NOTEN[pc(t['kick']['f_end_note'])] for t in kick).most_common())}
    # Kick-Grundton gegen Tonart: Intervall in Halbtoenen ueber dem Grundton der Tonart
    iv = [(pc(t['kick']['f_end_note']) - pc(t['tonart'])) % 12 for t in kick if (t.get('tonart_sicherheit') or 0) >= 0.5]
    p['kick']['intervall_zur_tonart'] = dict(Counter(iv).most_common())
    p['kick']['spearman_bpm'] = {f: round(float(spearmanr([t['bpm'] for t in kick], kw(f), nan_policy='omit')[0]), 2)
                                 for f in ('f_end_hz', 'abfall_20db_ms', 'pitch_tau_ms')}

    ras = [t for t in tracks if t.get('raster')]
    namen = [t['_name'] for t in ras]
    p['raster_n'] = len(ras)
    if ras:
        # Swing neu aus den gespeicherten Hat-Lagen: aeltere Laeufe nahmen auch Randwerte ohne echten Schlag
        for t in ras:
            t['raster']['swing_prozent'] = sr.swing_aus(t['raster']['hat_lage_ms_db'], t['bpm'])
        sw = [t['raster']['swing_prozent'] for t in ras]
        mit = [s for s in sw if s is not None]
        ok = [abs(t['raster']['hat_lage_ms_db'][2][0]) <= 12 for t in ras if t['raster']['hat_lage_ms_db'][2][1] >= -6]
        p['swing'] = {'ohne_beleg': sw.count(None), 'raster_belegt': f'{sum(ok)}/{len(ok)} Tracks mit Offbeat-Hat liegen ±12 ms im Raster', 'quartile': q(mit), 'ueber_54': sum(s > 54 for s in mit),
                      'verteilung': dict(sorted(Counter(int(round(s / 2) * 2) for s in mit).items()))}
        p['start_s'] = q([t['raster']['start_s'] for t in ras], nk=3)
        # belegt: Offbeat-Hat laut und hoechstens 12 ms neben dem Raster, der Takt-Start ist damit gesichert
        belegt = [t for t in ras if t['raster']['hat_lage_ms_db'][2][1] >= -6 and abs(t['raster']['hat_lage_ms_db'][2][0]) <= 12]
        p['belegt_n'] = len(belegt)
        for t in ras:
            t['_k'] = kennzahlen(t['raster'])
        p['grundmuster_prozent'] = {'alle': anteile([t['_k'] for t in ras]), 'belegt': anteile([t['_k'] for t in belegt])}
        p['bass_slot'] = dict(Counter(t['_k'].get('bass_slot') for t in ras if 'bass_slot' in t['_k']).most_common())
        p['drums'] = {}
        for b in ('kick', 'perc', 'clap', 'hat'):
            v = [t['raster']['muster'][b] for t in ras]
            p['drums'][b] = {'geruest_prozent': geruest(v), 'geruest_belegt': geruest([t['raster']['muster'][b] for t in belegt]), 'haeufigste': Counter(schritte(x) for x in v).most_common(6), 'cluster': cluster(v, namen)}
        p['tempo_gruppen'] = {}
        for g, (lo, hi) in TEMPO_GRUPPEN.items():
            tg = [t for t in ras if lo <= t['bpm'] < hi]
            if len(tg) >= 5:
                sw = [t['raster']['swing_prozent'] for t in tg if t['raster']['swing_prozent'] is not None]
                p['tempo_gruppen'][g] = {'n': len(tg), 'swing_ueber_54': sum(s > 54 for s in sw), 'grundmuster': anteile([t['_k'] for t in tg]),
                                         **{b: geruest([t['raster']['muster'][b] for t in tg], je_beat=True) for b in ('kick', 'clap', 'hat')},
                                         'bass': geruest([t['raster']['bass']['pegel_je_16tel_db'] for t in tg if t['raster'].get('bass')], -3, True)}
        bass = [t for t in ras if t['raster'].get('bass')]
        if bass:
            v = [t['raster']['bass']['pegel_je_16tel_db'] for t in bass]
            p['bass'] = {'n': len(bass), 'geruest_prozent': geruest(v, -3), 'geruest_belegt': geruest([t['raster']['bass']['pegel_je_16tel_db'] for t in belegt if t['raster'].get('bass')], -3), 'cluster': cluster(v, [t['_name'] for t in bass]),
                         'lautestes_16tel': dict(Counter(t['raster']['bass']['lautestes_16tel'] % 4 for t in bass).most_common()),
                         'abfall_12db_ms': q([t['raster']['bass']['abfall_12db_ms'] for t in bass])}
            iv = Counter()
            for t in bass:
                if (t.get('tonart_sicherheit') or 0) >= 0.5:
                    iv.update((pc(n) - pc(t['tonart'])) % 12 for n in t['raster']['bass']['ton_je_16tel'] if pc(n) is not None)
            ges = sum(iv.values()) or 1
            p['bass']['ton_intervall_anteil'] = {k: round(v / ges, 2) for k, v in iv.most_common()}

    arr = [a for a in (arrangement(t['energie_8takte_db']) for t in tracks if t.get('energie_8takte_db')) if a]
    p['arrangement'] = {'n': len(arr), 'bloecke': q([a['bloecke'] for a in arr]), 'intro_bloecke': q([a['intro_bloecke'] for a in arr]),
                        'outro_bloecke': q([a['outro_bloecke'] for a in arr]),
                        'breaks_je_track': dict(sorted(Counter(len(a['breaks']) for a in arr).items())),
                        'break_bloecke': dict(sorted(Counter(b['bloecke'] for a in arr for b in a['breaks']).items())),
                        'break_lage': dict(sorted(Counter(round(b['start_rel'] * 10) / 10 for a in arr for b in a['breaks']).items()))}
    return p


def _selbsttest():
    a = arrangement([-20, -8, -1, 0, -0.5, -12, -15, -1, 0, -9])
    assert a['intro_bloecke'] == 2 and a['breaks'] == [{'start_rel': 0.5, 'bloecke': 2}] and a['outro_bloecke'] == 1, a
    assert pc('G#1 (-0.13)') == 8 and pc('A# Moll') == 10
    c = cluster([[0, -20] * 8] * 5 + [[-20, 0] * 8] * 5, list('abcdefghij'))
    assert len(c) == 2 and {x['muster'] for x in c} == {'x.' * 8, '.x' * 8}, c


def md(p):
    z = [f"# Profil der Sammlung{' – Stil ' + p['stil'] if p.get('stil') else ''} ({p['n']} Tracks)", '',
         'Erzeugt von `maschine-mcp/ableton/sammlung-profil.py`. Quartile = 25/50/75 %. Muster: `x` = Schlag höchstens 6 dB unter dem lautesten des Bands, 16 Schritte = 1 Takt, Schritt 1 = Kick-Anschlag.', '',
         '## Tempo, Länge, Lautheit', '',
         f"- BPM {p['bpm']['quartile']}, Verteilung (2er-Schritte): {p['bpm']['verteilung']}",
         f"- Dauer {p['dauer_min']} min, Lautheit {p['lufs']} LUFS",
         f"- Tonart (Sicherheit ≥ 0,5, n={p['tonart']['n_sicher']}): Moll-Anteil {p['tonart']['moll_anteil']}, Grundton {p['tonart']['grundton']}", '',
         '## Kick', '']
    k = p['kick']
    z += [f"- Pitch-Sweep {k['f_start_hz']} → {k['f_end_hz']} Hz, Zeitkonstante {k['pitch_tau_ms']} ms",
          f"- Abfall −6 dB nach {k['abfall_6db_ms']} ms, −20 dB nach {k['abfall_20db_ms']} ms",
          f"- End-Ton: {k['end_ton']}", f"- Intervall Kick-Ton über Grundton der Tonart (Halbtöne): {k['intervall_zur_tonart']}",
          f"- Rangkorrelation mit BPM: {k['spearman_bpm']}", '']
    if p.get('raster_n'):
        zeile = lambda w: ' | '.join(f'{v:3}' for v in w) if w else '–'
        gm = p['grundmuster_prozent']
        z += ['## Grundmuster (% der Tracks)', '', '| Merkmal | alle ' + str(p['raster_n']) + ' | nur ' + str(p['belegt_n']) + ' belegte |', '|---|---|---|']
        z += [f'| {GM_NAME[f]} | {v} | {gm["belegt"].get(f, "–")} |' for f, v in gm['alle'].items()]
        z += ['', f"Lautestes Bass-16tel im Beat (0 = auf der Kick, 1 = x.25, 2 = x.5, 3 = x.75): {p['bass_slot']}", '']
        z += ['## Grundgerüst: Anteil der Tracks mit Schlag je 16tel (%)', '',
              '| Band | ' + ' | '.join(f'{i + 1}' for i in range(16)) + ' |', '|---' * 17 + '|']
        z += [f"| {BAND_NAME[b].split(' ')[0]} | {zeile(d['geruest_prozent'])} |" for b, d in p['drums'].items()]
        z += [f"| {BAND_NAME[b].split(' ')[0]} (nur {p['belegt_n']} belegte) | {zeile(d['geruest_belegt'])} |" for b, d in p['drums'].items() if b != 'hat']
        if p.get('bass'):
            z.append(f"| Bass (≤ 3 dB unter Max) | {zeile(p['bass']['geruest_prozent'])} |")
            z.append(f"| Bass (nur belegte) | {zeile(p['bass']['geruest_belegt'])} |")
        z += ['', '## Gerüst je Tempo-Gruppe (Slot im Beat: auf der Kick, x.25, x.5, x.75; % der Tracks)', '',
              '| Tempo | n | Swing > 54 % | Grundmuster % | Tief | Clap | Hat | Bass |', '|---|---|---|---|---|---|---|---|']
        z += [f"| {g} | {d['n']} | {d['swing_ueber_54']} | {d['grundmuster']} | {d['kick']} | {d['clap']} | {d['hat']} | {d['bass']} |" for g, d in p['tempo_gruppen'].items()]
        z.append('')
        s = p['swing']
        z += ['## Swing und Takt-Start', '', f"- Takt-Start (Kick-Anschlag) {p['start_s']} s nach Dateibeginn",
              f"- Swing der Hats auf x.25/x.75: {s['quartile']} %, über 54 %: {s['ueber_54']} Tracks, ohne Beleg: {s['ohne_beleg']}",
              f"- Raster-Kontrolle: {s['raster_belegt']}",
              f"- Verteilung: {s['verteilung']}", '', '## Drum-Muster im Haupt-Groove', '']
        for b, d in p['drums'].items():
            z.append('### ' + BAND_NAME[b])
            z += [f"- `{m}` {n}×" for m, n in d['haeufigste']]
            z += [f"- Gruppe {i + 1} ({c['n']} Tracks): `{c['muster']}` dB {c['zentrum_db']}" for i, c in enumerate(d['cluster'])]
            z.append('')
        if p.get('bass'):
            b = p['bass']
            z += ['## Bass je 16tel', '', f"- lautestes 16tel im Beat (0 = auf der Kick): {b['lautestes_16tel']}, Abfall −12 dB {b['abfall_12db_ms']} ms",
                  f"- Töne relativ zum Grundton (Halbtöne, Anteil): {b['ton_intervall_anteil']}"]
            z += [f"- Gruppe {i + 1} ({c['n']} Tracks): `{c['muster']}` dB {c['zentrum_db']}, z. B. {', '.join(c['beispiele'][:2])}" for i, c in enumerate(b['cluster'])]
            z.append('')
    if p.get('stil_merkmale'):
        z += ['## Stil-Merkmale (Quartile)', ''] + [f'- {k}: {v}' for k, v in p['stil_merkmale'].items()] + ['', 'Typische Tracks: ' + ', '.join(p['typisch']), '']
    a = p['arrangement']
    z += ['## Arrangement (Blöcke à 8 Takte)', '', f"- Länge {a['bloecke']}, Intro {a['intro_bloecke']}, Outro {a['outro_bloecke']} Blöcke",
          f"- Breaks je Track: {a['breaks_je_track']}", f"- Break-Länge (Blöcke): {a['break_bloecke']}", f"- Break-Beginn (Anteil der Tracklänge): {a['break_lage']}"]
    return '\n'.join(z) + '\n'


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')  # -I ignoriert PYTHONIOENCODING, cp1252 kennt keine Sonderzeichen
    _selbsttest()
    ordner = Path(sys.argv[1])
    tracks, gesehen = [], set()
    for f in sorted(ordner.glob('*/messwerte.json')):
        t = json.loads(f.read_text('utf8'))
        # Doppelkauf ("... Lies" und "... Lies_1") nur einmal zaehlen; ohne LUFS kollidieren fremde Tracks gleicher Laenge
        schluessel = (round(t.get('bpm') or 0, 1), round(t['dauer_s']), t.get('lufs'))
        if schluessel in gesehen:
            print(f'doppelt, übersprungen: {f.parent.name}')
            continue
        gesehen.add(schluessel)
        t['_name'] = f.parent.name
        tracks.append(t)
    p = profil(tracks)
    for stil, tr in stil_zuordnung(tracks).items():
        ps = {**profil(tr), 'stil': stil, 'stil_merkmale': stil_merkmale(tr), 'typisch': typisch(tr, stil)}
        (ordner / f'_profil-{stil}.json').write_text(json.dumps(ps, ensure_ascii=False, indent=1, default=lambda o: o.item()), 'utf8')
        (ordner / f'_profil-{stil}.md').write_text(md(ps), 'utf8')
        print(f"Stil {stil}: {ps['n']} Tracks, BPM {ps['bpm']['quartile']}, typisch {ps['typisch'][:3]}")
    # Nur Zahlen je Track, ohne Namen: damit ordnet stil-pruefen auch ohne Sammlung (Plugin-Paket) einen Export zu
    (ordner / '_stil-matrix.json').write_text(json.dumps(geteilte_matrix(tracks), default=lambda o: o.item()), 'utf8')
    (ordner / '_profil.json').write_text(json.dumps(p, ensure_ascii=False, indent=1, default=lambda o: o.item()), 'utf8')
    (ordner / '_profil.md').write_text(md(p), 'utf8')
    print(md(p))
