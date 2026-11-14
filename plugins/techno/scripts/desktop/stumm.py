# Schaltet ein Programm im Windows-Lautstaerkemischer stumm/laut, damit waehrend des Bauens nichts zu hoeren ist.
# Aufruf: python stumm.py an|aus|status [Prozessname-Anfang, Default "Ableton"]
import sys
from pycaw.pycaw import AudioUtilities

modus = sys.argv[1] if len(sys.argv) > 1 else 'status'
name = sys.argv[2] if len(sys.argv) > 2 else 'Ableton'
treffer = [s for s in AudioUtilities.GetAllSessions() if s.Process and s.Process.name().startswith(name)]
if not treffer:
    sys.exit(f'{name}: keine Ton-Sitzung (Programm spielt noch nie Ton ab oder laeuft nicht)')
for s in treffer:
    if modus in ('an', 'aus'):
        s.SimpleAudioVolume.SetMute(1 if modus == 'an' else 0, None)
    print(f'{s.Process.name()} stumm={bool(s.SimpleAudioVolume.GetMute())}')
