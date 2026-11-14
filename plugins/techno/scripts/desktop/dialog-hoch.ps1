# Ableton-Dialoge liegen auf breiten Bildschirmen teils unter dem Bildschirmrand und Klicks landen daneben:
# Dialog per Fenster-Handle (Titel-Muster) hochschieben und nach vorne holen, ohne Mausklick.
param([int]$ProzessId, [int]$Y = 600, [string]$Titel = '*')
Add-Type @'
using System; using System.Text; using System.Collections.Generic; using System.Runtime.InteropServices;
public static class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  public struct RECT { public int L, T, R, B; }
  public static List<IntPtr> Von(uint pid) {
    var l = new List<IntPtr>();
    EnumWindows((h, x) => { uint p; GetWindowThreadProcessId(h, out p); if (p == pid && IsWindowVisible(h)) l.Add(h); return true; }, IntPtr.Zero);
    return l;
  }
}
'@
foreach ($h in [W]::Von($ProzessId)) {
  $sb = New-Object System.Text.StringBuilder 256; [W]::GetWindowText($h, $sb, 256) | Out-Null
  $r = New-Object W+RECT; [W]::GetWindowRect($h, [ref]$r) | Out-Null
  "$h '$($sb)' $($r.L),$($r.T),$($r.R),$($r.B)"
  if ($sb.ToString() -notlike '*Ableton Live*' -and $sb.ToString() -like $Titel) {
    [W]::SetWindowPos($h, [IntPtr]::Zero, $r.L, $Y, 0, 0, 0x0001 -bor 0x0004) | Out-Null
    [W]::SetForegroundWindow($h) | Out-Null
    $r2 = New-Object W+RECT; [W]::GetWindowRect($h, [ref]$r2) | Out-Null
    "  verschoben nach $($r2.L),$($r2.T),$($r2.R),$($r2.B)"
  }
}
