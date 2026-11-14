# Exportiert das offene Live-Set mit den Einstellungen des Export-Dialogs als Audio nach $Pfad und wartet aufs Ende.
# Alles per Fenster-Handle und Tastatur: Strg+Umschalt+R, Enter im Export-Dialog, Pfad im Speichern-Dialog.
param([Parameter(Mandatory)][string]$Pfad, [switch]$StummErlaubt)
$hier = $PSScriptRoot
if (Test-Path $Pfad) { throw "$Pfad existiert schon: erst umbenennen oder loeschen (Ueberschreiben-Rueckfrage ist nicht automatisiert)" }
# Eine versehentlich stumme Spur (Rumble 13.11.) fiel erst beim Anhoeren auf: vor jedem Export pruefen
$stumm = (node "$hier\..\..\ableton\client.mjs" mixer meters | ConvertFrom-Json) | Where-Object { $_.mute -or $_.solo }
if ($stumm -and -not $StummErlaubt) { throw "Stumm/Solo: $(($stumm | ForEach-Object name) -join ', '). Absicht? Dann -StummErlaubt" }
$pidA = (Get-Process 'Ableton Live*' | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1).Id  # jede Live-Edition
# vorne.ps1 holt Live vor andere Programme; danach Titelleisten-Klick, weil ein offenes Plugin-Fenster (Ozone) sonst die Tasten abfaengt.
try { & "$hier\vorne.ps1" -Prozess 'Ableton Live*' | Out-Null } catch { }
& "$hier\tippen.ps1" -Prozess 'Ableton*' -Tasten @('^+r') | Out-Null
$ws = New-Object -ComObject WScript.Shell
Start-Sleep -Seconds 2
& "$hier\dialog-hoch.ps1" -ProzessId $pidA -Y 60 -Titel 'Audio/Video*' | Out-Null
Start-Sleep -Milliseconds 500
$ws.SendKeys('{ENTER}'); Start-Sleep -Seconds 2
& "$hier\speichern-unter.ps1" -Pfad $Pfad | Out-Null
# Ende ohne Fenstertitel erkennen: Datei waechst nicht mehr und Live hat sie freigegeben (exklusiv oeffenbar)
$groesse = -1
for ($i = 0; $i -lt 300; $i++) {
  Start-Sleep -Seconds 2
  if (-not (Test-Path $Pfad)) { continue }
  $jetzt = (Get-Item $Pfad).Length
  if ($jetzt -gt 0 -and $jetzt -eq $groesse) {
    try { [IO.File]::Open($Pfad, 'Open', 'Read', 'None').Close(); "exportiert: $Pfad"; return } catch { }
  }
  $groesse = $jetzt
}
throw 'Export nach 10 min nicht fertig: Bildschirmfoto pruefen'
