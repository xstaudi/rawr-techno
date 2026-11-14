# Holt das Hauptfenster eines Programms nach vorne. Windows blockt SetForegroundWindow aus Hintergrundprozessen;
# ein kurzer Alt-Tastendruck vorher hebt die Sperre auf.
param([string]$Prozess)
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class V {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, IntPtr extra);
}
'@
$p = Get-Process | Where-Object { $_.ProcessName -like $Prozess -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { throw "Kein Fenster für $Prozess" }
[V]::keybd_event(0x12, 0, 0, [IntPtr]::Zero); [V]::keybd_event(0x12, 0, 2, [IntPtr]::Zero)
[V]::ShowWindow($p.MainWindowHandle, 5) | Out-Null  # SW_SHOW: Groesse und Lage bleiben
[V]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 400
if ([V]::GetForegroundWindow() -ne $p.MainWindowHandle) { throw "$($p.ProcessName) kam nicht nach vorne" }
"vorne: $($p.MainWindowTitle)"
