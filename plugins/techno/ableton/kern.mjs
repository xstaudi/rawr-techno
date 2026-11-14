import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);

// ableton/kern.mjs
import { execFile, execFileSync, spawn } from "node:child_process";
import { existsSync as existsSync2, mkdirSync, openSync, readFileSync as readFileSync2, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join as join2 } from "node:path";
import { fileURLToPath } from "node:url";

// ableton/umgebung.mjs
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
var VENV = join(homedir(), ".venvs", "stems", "Scripts", "python.exe");
var PYTHON = process.env.TECHNO_PYTHON || (existsSync(VENV) ? VENV : "python");
var PY_FLAGS = ["-E", "-P", "-W", "ignore"];
function pythonFehlt(err) {
  return err?.code === "ENOENT" || err?.status === 9009 || err?.code === 9009 ? new Error(`Python 3 fehlt (${PYTHON}). Installieren: winget install Python.Python.3.12, danach Claude Code neu starten; anderes Python per TECHNO_PYTHON.`) : err;
}

// ableton/kern.mjs
var HIER = dirname(fileURLToPath(import.meta.url));
var AUFTRAEGE = join2(tmpdir(), "rawr-techno");
var STILE = ["raw", "deep", "hypnotic"];
var ROLLEN = ["kick", "rumble", "hat", "openhat", "perc", "synth", "pad"];
var SPUREN = ["Kick", "Rumble", "Hat", "Hat 2", "Perc", "Synth", "Pad"];
var TOENE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
var UMSCHRIFT = {
  H: "B",
  CB: "B",
  DB: "C#",
  EB: "D#",
  FB: "E",
  GB: "F#",
  AB: "G#",
  BB: "A#",
  HB: "A#",
  CIS: "C#",
  DIS: "D#",
  FIS: "F#",
  GIS: "G#",
  AIS: "A#",
  DES: "C#",
  ES: "D#",
  GES: "F#",
  AS: "G#"
};
function tonName(t) {
  const k = t.trim().toUpperCase().replace("\u266F", "#").replace("\u266D", "B");
  if (/^\d+$/.test(k)) return k;
  return k === "B" ? void 0 : TOENE.includes(k) ? k : UMSCHRIFT[k];
}
var TON_FEHLER = 'Unbekannter Grundton (C, C#/Cis/Db \u2026 H; "B" ist mehrdeutig: H oder Bb schreiben)';
var ENDE = { 0: "fertig", 2: "fertig, Pr\xFCfung au\xDFerhalb des Stil-Bereichs", 4: "fertig, Pr\xFCfung nicht m\xF6glich (Demucs?)" };
function py(skript, args) {
  try {
    return execFileSync(PYTHON, [...PY_FLAGS, join2(HIER, skript), ...args], { encoding: "utf8", maxBuffer: 1 << 26 });
  } catch (e) {
    throw pythonFehlt(e);
  }
}
function pyAsync(skript, args) {
  return new Promise((ok, fehler) => {
    execFile(
      PYTHON,
      [...PY_FLAGS, join2(HIER, skript), ...args],
      { encoding: "utf8", maxBuffer: 1 << 26, windowsHide: true },
      (e, aus, err) => e ? fehler(Object.assign(pythonFehlt(e), { stderr: err })) : ok(aus)
    );
  });
}
function soundArgs({ stil, rolle, seed, ton, ordner }) {
  const a = [stil, rolle];
  if (seed !== void 0) a.push("--seed", String(seed));
  if (ton) {
    if (!tonName(ton)) throw new Error(`${TON_FEHLER}: "${ton}"`);
    a.push("--ton", tonName(ton));
  }
  if (ordner) a.push("--aus", ordner);
  return a;
}
var SPERRE = join2(AUFTRAEGE, "laeuft.json");
var laufend = /* @__PURE__ */ new Map();
function laufenderAuftrag() {
  try {
    const { id, pid } = JSON.parse(readFileSync2(SPERRE, "utf8"));
    if (/^ENDE -?\d+$/m.test(readFileSync2(join2(AUFTRAEGE, `${id}.log`), "utf8"))) {
      rmSync(SPERRE, { force: true });
      return null;
    }
    process.kill(pid, 0);
    return id;
  } catch {
    return null;
  }
}
function optionen(o) {
  const a = [o.stil];
  if (o.seed !== void 0) a.push("--seed", String(o.seed));
  if (o.bpm) a.push("--bpm", String(o.bpm));
  if (o.quelle) a.push("--quelle", o.quelle);
  if (o.minuten) a.push("--minuten", String(o.minuten));
  if (o.spuren) a.push("--nur", o.spuren.join(","), "--takte", String(o.takte ?? 32));
  return a;
}
function auftrag(args) {
  const aktiv = laufenderAuftrag();
  if (aktiv) throw new Error(`Auftrag ${aktiv} l\xE4uft noch; erst nach dessen Ende neu starten`);
  rmSync(SPERRE, { force: true });
  mkdirSync(AUFTRAEGE, { recursive: true });
  const id = `t${Date.now().toString(36)}`;
  const log = join2(AUFTRAEGE, `${id}.log`);
  try {
    writeFileSync(SPERRE, JSON.stringify({ id, pid: process.pid }), { flag: "wx" });
  } catch {
    throw new Error("Ein anderer Auftrag startet gerade; gleich noch einmal versuchen");
  }
  const fd = openSync(log, "w");
  const kind = spawn(process.execPath, [join2(HIER, "stil-track.mjs"), ...args], { stdio: ["ignore", fd, fd], windowsHide: true });
  laufend.set(id, { kind, log, ende: null });
  writeFileSync(SPERRE, JSON.stringify({ id, pid: kind.pid }));
  kind.on("error", () => {
    laufend.get(id).ende = 1;
    rmSync(SPERRE, { force: true });
  });
  kind.on("exit", (code) => {
    laufend.get(id).ende = code ?? 1;
    rmSync(SPERRE, { force: true });
  });
  return id;
}
function auftragStatus(id) {
  const a = laufend.get(id);
  const log = a?.log ?? join2(AUFTRAEGE, `${id}.log`);
  if (!existsSync2(log)) return null;
  const alle = readFileSync2(log, "utf8").trim().split(/\r?\n/);
  const code = a?.ende ?? /^ENDE (-?\d+)$/.exec(alle.at(-1) ?? "")?.[1] ?? null;
  const stand = code === null ? a || laufenderAuftrag() === id ? "l\xE4uft" : "unbekannt (Lauf ohne Ende im Log)" : ENDE[code] ?? `Fehler (Exit ${code})`;
  const wav = alle.map((z) => /^Fertig: (.+\.wav) \(/.exec(z)?.[1]).filter(Boolean).at(-1) ?? null;
  return { id, stand, code: code === null ? null : Number(code), wav, zeilen: alle.slice(-40) };
}
function profilKennzahlen(stil) {
  const code = "import importlib.util as u,sys;s=u.spec_from_file_location('kl',sys.argv[1]);m=u.module_from_spec(s);s.loader.exec_module(m);print(m.profil_ordner())";
  let ordner;
  try {
    ordner = execFileSync(PYTHON, [...PY_FLAGS, "-c", code, join2(HIER, "stil-klang.py")], { encoding: "utf8" }).trim();
  } catch (e) {
    throw pythonFehlt(e);
  }
  const p = JSON.parse(readFileSync2(join2(ordner, `_profil-${stil}.json`), "utf8"));
  return {
    n: p.n,
    bpm: p.bpm.quartile,
    lufs: p.lufs,
    dauer_min: p.dauer_min,
    kick: { f_end_hz: p.kick.f_end_hz, abfall_20db_ms: p.kick.abfall_20db_ms },
    tonart: p.tonart,
    swing: p.swing?.quartile,
    grundmuster_prozent: p.grundmuster_prozent?.alle
  };
}
export {
  AUFTRAEGE,
  ROLLEN,
  SPUREN,
  STILE,
  TON_FEHLER,
  auftrag,
  auftragStatus,
  laufenderAuftrag,
  optionen,
  profilKennzahlen,
  py,
  pyAsync,
  soundArgs,
  tonName
};
