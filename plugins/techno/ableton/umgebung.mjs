import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);

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
function pythonFehlt(err) {
  return err?.code === "ENOENT" || err?.status === 9009 || err?.code === 9009 ? new Error(`Python 3 fehlt (${PYTHON}). Installieren: winget install Python.Python.3.12, danach Claude Code neu starten; anderes Python per TECHNO_PYTHON.`) : err;
}
export {
  PYTHON,
  PY_FLAGS,
  powershell,
  pythonFehlt,
  userLibrary
};
