# RAWR Techno

Claude-Code-Plugin für Ableton Live, ein Ideengeber für Producer und DJs: „Gib mir eine raw-Kick“, und du bekommst drei Vorschläge zur Auswahl. Dazu Spuren und ganze Track-Skizzen im Stil **raw**, **deep** oder **hypnotic** als Startpunkt für deine eigene Arbeit. Die Stile sind Kennzahlen aus einer vermessenen Sammlung von rund 230 Techno-Tracks (Tempo, Kick-Tonhöhe und -Abfall, Drum-Gerüst, Bass-Platz, Arrangement, Lautheit). Das Paket enthält nur diese Zahlen, keine Tracks, Samples oder Titel.

Die Stile bauen aufeinander auf: **raw** ist roh und dunkel, nur Kick, Rumble, Hats und Perc. **deep** legt weiche Moll-Akkorde mit Dub-Echo und eine Fläche darüber. **hypnotic** zieht mit einem kurzen Synth-Loop, der vom ersten bis zum letzten Groove unverändert durchläuft.

*Claude Code plugin for Ableton Live, an idea generator for producers and DJs: ask for a raw kick and pick from three suggestions; parts and full track sketches (raw / deep / hypnotic) from measured style profiles.*

![RAWR Techno: Track gebaut, als deep eingeordnet, Export gegen die Sammlung](bilder/app-track.png)

## Hörprobe

raw, deep und hypnotic nacheinander, je ein Ausschnitt aus einem ganzen Track, den das Plugin gebaut hat, vom letzten Takt vor dem Peak an, ohne Nachmischen. *Listen: raw, deep and hypnotic, each an excerpt of a full track built by the plugin, no mixing afterwards.*

https://github.com/user-attachments/assets/85930b5f-d099-4741-87b3-8f2cd8b7f05b

## Was es kann

| Sag zu Claude | Ergebnis |
|---|---|
| „raw kick“, „deep pad in F“, „hypnotic hihat“ | drei WAV-Vorschläge zur Auswahl (bis zu sechs auf Wunsch): aus deiner eigenen Sample-Library die Klänge, die dem Stil-Profil am nächsten liegen, auf den Grundton gestimmt; ohne Library synthetisiert |
| „hypnotic Kick und Rumble, 16 Takte“ | Spuren als Loop im offenen Live-Set |
| „raw track“, „deep track mit 7 Minuten“ | neues Set mit Arrangement, Pegeln, Limiter auf das LUFS-Ziel des Stils und WAV-Export |
| „raw track und prüf ihn“ | dazu die Demucs-Messung des Exports gegen das Profil; liegen Tempo, Kick, Lautheit, Länge oder Aufbau außerhalb, baut das Plugin bis zu zweimal mit neuem Zufallswert neu (je etwa 20 Minuten), Fehlversuche bleiben in ihrem Ordner |
| „öffne techno“ | die Oberfläche im Browser, alles per Klick |

## Oberfläche

„öffne techno“ in Claude Code startet die App unter `http://127.0.0.1:4141` (ohne Claude: `node <Plugin-Ordner>/ableton/app-server.mjs --oeffnen`). Stil wählen, Sound, Spuren oder Track, Länge und Tempo einstellen, starten. Die App zeigt Wellenform und Messwerte, spielt das Ergebnis ab und öffnet den Ordner. Beim Track sieht man jeden Schritt (Rezept, Spuren, Arrangement, Export, Prüfung) und am Ende den Export gegen die Sammlung: graues Band = mittlere Hälfte der Sammlung, Strich = Median, Quadrat = dein Track.

Die App läuft nur auf diesem Rechner und nimmt keine Anfragen anderer Webseiten an.

![RAWR Techno: Einzelsound](bilder/app-sound.png)

## Installieren (etwa 10 Minuten)

Du brauchst Windows 10 oder 11, Ableton Live 11 oder 12 mit **deutscher Oberfläche** und [Claude Code](https://claude.com/claude-code) mit Anmeldung. Live muss über den Windows-Ausgang spielen (Einstellungen → Audio → Treiber „MME/DirectX“ oder „WASAPI“), mit ASIO kann das Plugin die Pegel nicht messen.

**1. Node.js und Python, falls noch nicht da** (PowerShell):

```
winget install OpenJS.NodeJS.LTS
winget install Python.Python.3.12
```

Danach ein neues Terminal öffnen. `python --version` muss 3.11 oder neuer zeigen. Öffnet sich stattdessen der Microsoft Store: Einstellungen → Apps → Erweiterte App-Einstellungen → App-Ausführungsaliase → „python.exe“ ausschalten.

**2. Plugin holen:**

```
claude plugin marketplace add xstaudi/rawr-techno
claude plugin install techno@rawr-techno
```

**3. In Claude Code sagen:** „richte techno ein“

Claude kopiert das Remote Script `ClaudeMixer` in deine Ableton User Library, installiert numpy, scipy, pycaw und ffmpeg, wenn sie fehlen, und meldet jede Zeile. Wurde ffmpeg neu installiert: Claude Code einmal schließen und neu öffnen.

**4. In Live einmal:** Live neu starten (erst dann kennt es ClaudeMixer), dann Einstellungen → Link/Tempo/MIDI → Control Surface → `ClaudeMixer` (Eingang und Ausgang leer lassen). Noch einmal „richte techno ein“, bis „bereit“ dasteht.

Optional für die Stil-Prüfung: `python -m pip install --user demucs` (mit Nvidia-Karte schneller).

Optional für Vorschläge aus deinen eigenen Samples: `TECHNO_LIBRARY` auf deinen Sample-Ordner setzen (Unterordner `Kicks/One-Shots`, `HiHats/One-Shots`, `Percussion/One-Shots`, `Synths/One-Shots`, `Atmo-Pads/One-Shots`), dann zu Claude „vermiss meine Samples“ sagen. Das misst jedes Sample einmal (Helligkeit, Rauheit, Länge, Grundton) und dauert je nach Größe einige Minuten. Die Samples bleiben auf deinem Rechner.

## Aktualisieren und entfernen

```
claude plugin marketplace update rawr-techno
claude plugin update techno@rawr-techno
claude plugin uninstall techno@rawr-techno
```

Das Remote Script liegt danach noch unter `Dokumente/Ableton/User Library/Remote Scripts/ClaudeMixer` und kann dort gelöscht werden.

## Wenn etwas hakt

| Meldung | Abhilfe |
|---|---|
| „keine Antwort von Ableton“ | Live läuft nicht oder ClaudeMixer ist nicht als Control Surface gewählt (Schritt 4) |
| „Offenes Set hat ungespeicherte Änderungen“ | Set in Live speichern, dann den Track neu anfordern |
| „Python 3 fehlt“ | Schritt 1, danach Terminal und Claude Code neu starten; anderes Python per `TECHNO_PYTHON` |
| „Keine Pegel messbar“ | Live spielt über ASIO: Treiber auf MME/DirectX oder WASAPI stellen |
| „Auftrag … läuft noch“ | Es läuft immer nur ein Bau; warten, bis `status` „fertig“ meldet |
| Export hängt | während des Laufs nicht in Live klicken; Live-Oberfläche muss deutsch sein |
| Live bleibt stumm | „richte techno ein“ hebt die Stummschaltung nach einem abgebrochenen Lauf auf |

## Einstellungen (Umgebungsvariablen)

| Variable | Zweck |
|---|---|
| `TECHNO_PYTHON` | Python mit numpy/scipy, Standard `python` |
| `TECHNO_LIBRARY` | eigene Sample-Library für die Quelle `library` (Ordner `Kicks/One-Shots`, `HiHats/One-Shots`, `Percussion/One-Shots`, `Synths/One-Shots`, `Atmo-Pads/One-Shots`) |
| `TECHNO_PROFILE` | eigener Profil-Ordner (`_profil-raw.json` …) statt der mitgelieferten |
| `ABLETON_USER_LIBRARY` | nur nötig, wenn das Plugin die User Library nicht selbst findet (es liest sie aus den Live-Einstellungen) |

Setzen in PowerShell, z. B. `setx TECHNO_PYTHON "C:\Python312\python.exe"`, danach Claude Code neu starten.

## Grenzen

- Export und Speichern laufen über Tastatur und Fenstertitel von Live. Während eines Laufs nicht in Live klicken. Getestet nur mit deutscher Live-Oberfläche.
- Das Remote Script nimmt Befehle von jedem Programm auf diesem Rechner an (nur 127.0.0.1, nicht aus dem Netz).
- Ohne eigene Sample-Library sind die Klänge einfache Synthese. deep-Akkorde und Fläche sind immer synthetisiert.
- Live Intro erlaubt 16 Spuren; ein Track braucht bis zu 7.

## In English

Windows 10/11, Ableton Live 11 or 12 (tested: Live 11 Intro with **German UI**; English dialog titles are untested), Claude Code, Node.js, Python ≥ 3.11. Live must use MME/DirectX or WASAPI, not ASIO.

```
claude plugin marketplace add xstaudi/rawr-techno
claude plugin install techno@rawr-techno
```

The styles stack: **raw** is kick, rumble, hats and percussion only; **deep** adds soft minor chords with dub echo and a pad; **hypnotic** adds a short synth loop that runs unchanged through every groove section.

Optional: point `TECHNO_LIBRARY` at your sample folder and say „measure my samples“; suggestions then come from your own samples, tuned to the key.

Then tell Claude „set up techno“, select the control surface `ClaudeMixer` in Live, and say „raw kick“, „hypnotic kick and rumble, 16 bars“, „deep track“ or „open techno“ for the browser app. „raw track and check it“ measures the export with Demucs; if tempo, kick, loudness, length or structure land outside the profile, the plugin rebuilds up to twice with a new random seed.

## Lizenz

MIT, siehe `LICENSE`. Klänge und Tracks, die du mit dem Plugin erzeugst, gehören dir.
