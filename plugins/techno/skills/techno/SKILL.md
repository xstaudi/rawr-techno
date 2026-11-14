---
name: techno
description: Baut Techno-Sounds, Spuren und ganze Tracks im Stil raw, deep oder hypnotic in Ableton Live, nach Messwerten einer Track-Sammlung (Tempo, Kick, Drum-Gerüst, Bass, Arrangement, Lautheit). Use when "raw track", "deep track", "hypnotic track", "erstell mir eine Kick/Hihat/Rumble/Perc/Synth/Pad", "make me a raw kick", "Komponente für einen Track", "Loop mit 32 Takten", "Track mit 7 Minuten", Techno-Sound erzeugen, Stil-Profil zeigen. Nicht für andere Genres oder für Mixing/Mastering fremder Projekte.
---

# Techno raw / deep / hypnotic

Werkzeuge des MCP-Servers `techno` (Plugin): `sound`, `komponente`, `track`, `status`, `profil`, `app`.

## Erststart (einmal je Rechner)

1. Werkzeug `einrichten` aufrufen. Es kopiert das Remote Script `ClaudeMixer` in die Ableton User Library, prüft Python (numpy, scipy), ffmpeg und optional Demucs und meldet, ob Live das Script geladen hat.
2. Fehlt etwas, die Zeilen aus der Antwort dem Nutzer nennen (z. B. `pip install numpy scipy`). Ist das Script noch nicht aktiv: Live → Einstellungen → Link/Tempo/MIDI → Control Surface `ClaudeMixer` wählen (Ein- und Ausgang leer lassen), Live neu starten, `einrichten` erneut aufrufen.

## Welcher Befehl

| Wunsch | Werkzeug | Beispiel |
|---|---|---|
| Einzelsound als WAV | `sound` | „raw kick“ → `{stil:"raw", rolle:"kick"}`; „deep pad in F“ → `{stil:"deep", rolle:"pad", ton:"F"}` |
| Spuren als Loop ins offene Set | `komponente` | „hypnotic Kick und Rumble, 16 Takte“ → `{stil:"hypnotic", spuren:["Kick","Rumble"], takte:16}` |
| Ganzer Track mit Export | `track` | „raw track“ → `{stil:"raw"}`; „deep track 7 Minuten“ → `{stil:"deep", minuten:7}` |
| Kennzahlen eines Stils | `profil` | „was macht hypnotic aus?“ |
| Oberfläche im Browser | `app` | „öffne techno“, „zeig mir die App“ |

Rollen für `sound`: kick, rumble, hat, openhat, perc, synth, pad. Spuren für `komponente`: Kick, Rumble, Hat, Hat 2, Perc, Synth, Pad.

## Ablauf `track`

1. Vorher fragen, ob das offene Set gespeichert ist: `track` öffnet ein neues Set und bricht bei ungespeicherten Änderungen ab.
2. `track` starten, die Antwort nennt eine Auftrags-ID.
3. Alle 2 min `status` mit der ID abfragen, bis „fertig“ oder „Fehler“ dasteht. Während des Laufs nicht in Live klicken: Export und Speichern laufen über Tastatur und Fenster.
4. Ergebnis nennen: WAV-Pfad, LUFS, True Peak, Pegeltabelle; mit `pruefen:true` die Tabelle Merkmal → Export → Sammlung und die Stil-Zuordnung.
5. Set speichern lassen (Strg+S in Live), der Track liegt unter `~/Music/<Stil> <BPM> s<Seed>/`.

## Grenzen

- Windows, Ableton Live 11 oder 12 mit deutscher oder englischer Oberfläche. Getestet: Live 11 Intro, deutsch. Englische Dialogtitel sind ungetestet.
- Intro erlaubt 16 Spuren; ein Track braucht bis zu 7.
- Die Klänge sind synthetisch (Quelle `synth`). `library` braucht eine eigene, vermessene Sample-Library (`TECHNO_LIBRARY`, Ordner `Kicks/One-Shots`, `HiHats/One-Shots`, …).
- `pruefen` braucht Demucs (`pip install demucs`); ohne Nvidia-Karte dauert die Prüfung 5–10 min. Liegt der Export außerhalb des Stils, baut `track` ohne festen `seed` bis zu zweimal neu; `status` zeigt die Zeilen „Neuversuch“. Mit festem `seed` gibt es keinen Neuversuch.
- Die Stil-Profile sind Kennzahlen einer privaten Sammlung (nur Zahlen, keine Tracks oder Namen).
