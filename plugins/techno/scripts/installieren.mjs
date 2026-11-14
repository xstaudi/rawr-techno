#!/usr/bin/env node
import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);

// scripts/installieren.mjs
import { spawnSync as spawnSync2 } from "node:child_process";
import { cpSync, existsSync as existsSync2 } from "node:fs";
import { dirname, join as join2 } from "node:path";
import { fileURLToPath } from "node:url";

// ableton/umgebung.mjs
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
var VENV = join(homedir(), ".venvs", "stems", "Scripts", "python.exe");
var PYTHON = process.env.TECHNO_PYTHON || (existsSync(VENV) ? VENV : "python");
var PY_FLAGS = ["-E", "-P", "-W", "ignore"];
var ps;
function powershell() {
  ps ??= spawnSync("pwsh", ["-NoProfile", "-Command", "exit 0"]).status === 0 ? "pwsh" : "powershell.exe";
  return ps;
}
function userLibrary() {
  if (process.env.ABLETON_USER_LIBRARY) return process.env.ABLETON_USER_LIBRARY;
  const basis = join(process.env.APPDATA ?? join(homedir(), "AppData", "Roaming"), "Ableton");
  const cfgs = existsSync(basis) ? readdirSync(basis).filter((n) => n.startsWith("Live ")).map((n) => join(basis, n, "Preferences", "Library.cfg")).filter(existsSync) : [];
  cfgs.sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
  for (const f of cfgs) {
    const m = /<UserLibrary>[\s\S]*?<ProjectPath Value="([^"]+)"/.exec(readFileSync(f, "utf8"));
    const pfad = m && join(m[1].replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&"), "User Library");
    if (pfad && existsSync(pfad)) return pfad;
  }
  return join(homedir(), "Documents", "Ableton", "User Library");
}

// scripts/installieren.mjs
var HIER = dirname(fileURLToPath(import.meta.url));
var USER_LIB = userLibrary();
var ALLES = process.argv.includes("--alles");
var ok = true;
var zeile = (z) => console.log(z);
var melde = (gut, text) => {
  zeile(`${gut ? "ok   " : "FEHLT"} ${text}`);
  if (!gut) ok = false;
};
var lauf = (cmd, args) => spawnSync2(cmd, args, { encoding: "utf8" });
var py = (code) => lauf(PYTHON, [...PY_FLAGS, "-c", code]);
if (existsSync2(USER_LIB)) {
  cpSync(join2(HIER, "..", "ableton", "ClaudeMixer"), join2(USER_LIB, "Remote Scripts", "ClaudeMixer"), { recursive: true, filter: (p) => !p.includes("__pycache__") });
  melde(true, `Remote Script ClaudeMixer nach ${join2(USER_LIB, "Remote Scripts")}`);
} else {
  melde(false, `Ableton User Library nicht gefunden (${USER_LIB}); Live einmal starten oder Pfad per ABLETON_USER_LIBRARY setzen`);
}
var version = lauf(PYTHON, ["-c", "import sys; print(sys.version_info >= (3, 11))"]);
if (version.status !== 0) {
  melde(false, `Python 3 fehlt (${PYTHON}): winget install Python.Python.3.12, danach Claude Code neu starten`);
  process.exit(1);
}
if (version.stdout.trim() !== "True") melde(false, `Python ab 3.11 n\xF6tig (${PYTHON}): winget install Python.Python.3.12`);
var pip = (pakete) => lauf(PYTHON, ["-m", "pip", "install", "--user", "--quiet", ...pakete]).status;
if (ALLES && py("import numpy, scipy").status !== 0) zeile(`neu   pip install numpy scipy: Exit ${pip(["numpy", "scipy"])}`);
if (ALLES && py("import pycaw").status !== 0) zeile(`neu   pip install pycaw: Exit ${pip(["pycaw"])}`);
if (ALLES && lauf("ffmpeg", ["-version"]).status !== 0) {
  const w = lauf("winget", ["install", "--id", "Gyan.FFmpeg", "-e", "--silent", "--accept-package-agreements", "--accept-source-agreements"]);
  zeile(`neu   winget install Gyan.FFmpeg: Exit ${w.status} (danach Claude Code neu starten, damit ffmpeg im PATH steht)`);
}
var np = py("import numpy, scipy; print(numpy.__version__, scipy.__version__)");
melde(np.status === 0, np.status === 0 ? `Python mit numpy/scipy ${np.stdout.trim()}` : `numpy und scipy: ${PYTHON} -m pip install --user numpy scipy`);
melde(lauf("ffmpeg", ["-version"]).status === 0, "ffmpeg (sonst: winget install Gyan.FFmpeg, Claude Code neu starten)");
zeile(`ok    PowerShell: ${powershell()}`);
zeile(py("import demucs").status === 0 ? "ok    Demucs (f\xFCr die Stil-Pr\xFCfung)" : "opt.  Demucs fehlt: nur n\xF6tig f\xFCr pruefen (pip install --user demucs)");
var pycaw = py("import pycaw").status === 0;
zeile(pycaw ? "ok    pycaw (Live beim Bauen stumm)" : "opt.  pycaw fehlt: Live bleibt beim Bauen h\xF6rbar (pip install --user pycaw)");
var ping = lauf(process.execPath, [join2(HIER, "..", "ableton", "client.mjs"), "mixer", "ping"]);
melde(ping.status === 0, ping.status === 0 ? "Live antwortet \xFCber ClaudeMixer" : "Live antwortet nicht: Live neu starten, dann Einstellungen \u2192 Link/Tempo/MIDI \u2192 Control Surface \u201EClaudeMixer\u201C w\xE4hlen");
if (pycaw) lauf(PYTHON, [...PY_FLAGS, join2(HIER, "desktop", "stumm.py"), "aus"]);
process.exit(ok ? 0 : 1);
