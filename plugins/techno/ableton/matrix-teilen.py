"""Stil-Matrix fuers Teilen kuerzen: python matrix-teilen.py <ein.json> <aus.json>
Bricht ab, wenn die gekuerzte Matrix einen Track anders einordnet als die volle."""
import importlib.util, json, sys
from collections import Counter
from pathlib import Path

s = importlib.util.spec_from_file_location('sp', Path(__file__).with_name('sammlung-profil.py'))
sp = importlib.util.module_from_spec(s)
s.loader.exec_module(sp)


def einordnung(tracks):
    return Counter((stil, tuple(t['_stil_wert'])) for stil, tr in sp.stil_zuordnung([dict(t) for t in tracks]).items() for t in tr)


voll = json.loads(Path(sys.argv[1]).read_text('utf8'))
geteilt = sp.geteilte_matrix(voll)
if einordnung(voll) != einordnung(geteilt):
    sys.exit('Gekuerzte Matrix ordnet anders ein als die volle')
Path(sys.argv[2]).write_text(json.dumps(geteilt, default=lambda o: o.item()), 'utf8')
print(f'Matrix: {len(voll)} -> {len(geteilt)} Zeilen, Einordnung gleich')
