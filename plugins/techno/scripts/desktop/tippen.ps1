param([int]$X = -1, [int]$Y = -1, [string]$Prozess, [string[]]$Tasten)
# Klickt (X,Y), prueft, dass das Vordergrundfenster dem Prozess gehoert, und sendet erst dann Tasten.
# Ohne X/Y: Mitte der Titelleiste des Hauptfensters (passt auf jeden Bildschirm).
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class F {
  [StructLayout(LayoutKind.Sequential)] public struct R { public int L, T, Rr, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out R r);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
}
'@
$ziel = @(Get-Process | Where-Object { $_.ProcessName -like $Prozess } | ForEach-Object Id)
if ($X -lt 0 -or $Y -lt 0) {
  $h = (Get-Process | Where-Object { $_.ProcessName -like $Prozess -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowHandle
  if (-not $h) { throw "Kein Fenster von $Prozess" }
  $r = New-Object F+R; [F]::GetWindowRect($h, [ref]$r) | Out-Null
  $X = [int](($r.L + $r.Rr) / 2); $Y = $r.T + 12
}
[F]::SetCursorPos($X, $Y) | Out-Null; Start-Sleep -Milliseconds 150
[F]::mouse_event(2, 0, 0, 0, [IntPtr]::Zero); [F]::mouse_event(4, 0, 0, 0, [IntPtr]::Zero)
Start-Sleep -Milliseconds 400
$ws = New-Object -ComObject WScript.Shell
foreach ($t in $Tasten) {
  $fpid = 0; [F]::GetWindowThreadProcessId([F]::GetForegroundWindow(), [ref]$fpid) | Out-Null
  if ($ziel -notcontains [int]$fpid) { throw "Vordergrund gehört PID $fpid, nicht $Prozess ($ziel): abgebrochen" }
  $ws.SendKeys($t); Start-Sleep -Milliseconds 300
}
"ok"
