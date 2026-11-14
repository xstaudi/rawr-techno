# Fuellt einen Windows-Speichern-Dialog von Ableton per Tastatur (Alt+N = Dateiname), kein Klick.
param([string]$Pfad, [string]$Titel = 'Audio-Datei speichern*')
$sp = $PSScriptRoot
$pidA = (Get-Process 'Ableton Live*' | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1).Id
& "$sp\dialog-hoch.ps1" -ProzessId $pidA -Y 60 -Titel $Titel | Out-Null
Add-Type 'using System;using System.Runtime.InteropServices;public static class FG{[DllImport("user32.dll")]public static extern IntPtr GetForegroundWindow();[DllImport("user32.dll")]public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);}'
Start-Sleep -Milliseconds 500
$fp = 0; [FG]::GetWindowThreadProcessId([FG]::GetForegroundWindow(), [ref]$fp) | Out-Null
if ($fp -ne $pidA) { throw "Vordergrund gehoert PID $fp, nicht Ableton" }
$ws = New-Object -ComObject WScript.Shell
# SendKeys-Sonderzeichen im Pfad (+^%~(){}[]) waeren sonst Tastenbefehle
$text = [regex]::Replace($Pfad, '[+^%~(){}\[\]]', { "{$($args[0].Value)}" })
foreach ($t in @('%n', '^a', $text, '{ENTER}')) { $ws.SendKeys($t); Start-Sleep -Milliseconds 300 }
'getippt'
