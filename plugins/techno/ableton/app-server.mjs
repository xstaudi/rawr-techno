#!/usr/bin/env node
import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);

// ableton/app-server.mjs
import { spawn as spawn2 } from "node:child_process";
import { createReadStream, readFileSync as readFileSync3, statSync as statSync2 } from "node:fs";
import { createServer } from "node:http";
import { pipeline } from "node:stream";
import { dirname as dirname2, join as join3, resolve } from "node:path";
import { fileURLToPath as fileURLToPath2 } from "node:url";

// ableton/client.mjs
import net from "node:net";
var MIXER_PORT = 9878;
var PORT = Number(process.env.ABLETON_PORT || MIXER_PORT);
var TIMEOUT_MS = 3e4;
function send(type, params = {}, port = PORT) {
  return new Promise((resolve2, reject) => {
    const s = net.connect(port, "127.0.0.1", () => s.write(JSON.stringify({ type, params })));
    let buf = "";
    const timer = setTimeout(() => {
      s.destroy();
      reject(new Error(`${type}: keine Antwort von Ableton (l\xE4uft Live mit Control Surface ClaudeMixer?)`));
    }, TIMEOUT_MS);
    s.on("data", (d) => {
      buf += d;
      let r;
      try {
        r = JSON.parse(buf);
      } catch {
        return;
      }
      clearTimeout(timer);
      s.end();
      if (r.status === "success") resolve2(r.result);
      else reject(new Error(`${type}: ${r.message ?? JSON.stringify(r)}`));
    });
    s.on("error", (e) => {
      clearTimeout(timer);
      reject(new Error(`${type}: ${e.message}`));
    });
  });
}
if (process.argv[1]?.endsWith("client.mjs") && process.argv[2]) {
  const args = process.argv.slice(2);
  const port = args[0] === "mixer" ? (args.shift(), MIXER_PORT) : PORT;
  send(args[0], JSON.parse(args[1] ?? "{}"), port).then((r) => console.log(JSON.stringify(r, null, 1))).catch((e) => {
    console.error(e.message);
    process.exit(1);
  });
}

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

// ableton/app-server.mjs
var HIER2 = dirname2(fileURLToPath2(import.meta.url));
var PORT2 = Number(process.env.TECHNO_APP_PORT || 4141);
var SEITE = join3(HIER2, "app", "index.html");
var MAX_BODY = 64 * 1024;
var eigeneDateien = /* @__PURE__ */ new Set();
var profile = /* @__PURE__ */ new Map();
var json = (res, code, daten) => {
  res.writeHead(code, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  res.end(JSON.stringify(daten));
};
function koerper(req) {
  return new Promise((ok, fehler) => {
    let s = "";
    req.setEncoding("utf8");
    req.on("data", (d) => {
      s += d;
      if (s.length > MAX_BODY) {
        fehler(new Error("Anfrage zu gro\xDF"));
        req.destroy();
      }
    });
    req.on("end", () => {
      try {
        ok(JSON.parse(s || "{}"));
      } catch {
        fehler(new Error("Kein g\xFCltiges JSON"));
      }
    });
  });
}
var ganz = (v, min, max) => v === void 0 || v === null || v === "" ? void 0 : Number.isInteger(Number(v)) && Number(v) >= min && Number(v) <= max ? Number(v) : (() => {
  throw new Error(`Wert ${v} au\xDFerhalb ${min}\u2013${max}`);
})();
var stilPruefen = (s) => {
  if (!STILE.includes(s)) throw new Error(`Unbekannter Stil "${s}"`);
  return s;
};
async function liveVerbunden() {
  try {
    await Promise.race([send("ping", {}, 9878), new Promise((_, n) => setTimeout(() => n(new Error("zeit")), 1500))]);
    return true;
  } catch {
    return false;
  }
}
var routen = {
  "GET /api/stand": async () => ({ live: await liveVerbunden(), auftrag: laufenderAuftrag(), stile: STILE, rollen: ROLLEN, spuren: SPUREN }),
  "GET /api/profil": async (_, url) => {
    const stil = stilPruefen(url.searchParams.get("stil"));
    if (!profile.has(stil)) profile.set(stil, profilKennzahlen(stil));
    return profile.get(stil);
  },
  "POST /api/sound": async (b) => {
    if (!ROLLEN.includes(b.rolle)) throw new Error(`Unbekannter Sound "${b.rolle}"`);
    const r = JSON.parse(await pyAsync("stil-klang.py", soundArgs({ stil: stilPruefen(b.stil), rolle: b.rolle, seed: ganz(b.seed, 0, 1e9), ton: b.ton || void 0 })));
    eigeneDateien.add(resolve(r.datei));
    return r;
  },
  "POST /api/spuren": async (b) => {
    const spuren = Array.isArray(b.spuren) ? b.spuren.filter((s) => SPUREN.includes(s)) : [];
    if (!spuren.length) throw new Error("Mindestens eine Spur w\xE4hlen");
    return { id: auftrag(optionen({ stil: stilPruefen(b.stil), spuren, takte: ganz(b.takte, 1, 256) ?? 32, bpm: ganz(b.bpm, 100, 170), seed: ganz(b.seed, 0, 1e9) })) };
  },
  "POST /api/track": async (b) => {
    const minuten = b.minuten === void 0 ? void 0 : Number(b.minuten);
    if (minuten !== void 0 && !(minuten >= 1 && minuten <= 20)) throw new Error("L\xE4nge 1\u201320 min");
    const a = optionen({ stil: stilPruefen(b.stil), minuten, bpm: ganz(b.bpm, 100, 170), seed: ganz(b.seed, 0, 1e9) });
    if (b.pruefen) a.push("--pruefen");
    return { id: auftrag([...a, "--stumm"]) };
  },
  "GET /api/status": async (_, url) => {
    const id = url.searchParams.get("id") ?? "";
    if (!/^t[0-9a-z]+$/.test(id)) throw new Error("Ung\xFCltige Auftrags-Id");
    const s = auftragStatus(id);
    if (!s) throw new Error(`Kein Auftrag ${id}`);
    if (s.wav) eigeneDateien.add(resolve(s.wav));
    return s;
  },
  "POST /api/zeigen": async (b) => {
    const pfad = resolve(String(b.datei ?? ""));
    if (!eigeneDateien.has(pfad)) throw new Error("Unbekannte Datei");
    spawn2("explorer.exe", ["/select,", pfad], { detached: true, stdio: "ignore" }).on("error", () => {
    }).unref();
    return { ok: true };
  }
};
function wavSenden(res, url) {
  const pfad = resolve(url.searchParams.get("datei") ?? "");
  let groesse = 0;
  try {
    groesse = eigeneDateien.has(pfad) ? statSync2(pfad).size : 0;
  } catch {
    groesse = 0;
  }
  if (!groesse) return json(res, 404, { fehler: "Unbekannte Datei" });
  res.writeHead(200, { "content-type": "audio/wav", "content-length": groesse, "cache-control": "no-store" });
  pipeline(createReadStream(pfad), res, () => {
  });
}
var kurzerFehler = (e) => e.stderr?.trim().split(/\r?\n/).at(-1) || e.message.split("\n")[0];
var erlaubterHost = (h) => h === `127.0.0.1:${PORT2}` || h === `localhost:${PORT2}`;
var server = createServer(async (req, res) => {
  if (!erlaubterHost(req.headers.host)) return json(res, 403, { fehler: "Nur lokal" });
  let url;
  try {
    url = new URL(req.url, "http://127.0.0.1");
  } catch {
    return json(res, 400, { fehler: "Ung\xFCltige Adresse" });
  }
  if (req.method === "GET" && url.pathname === "/") {
    res.writeHead(200, {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "content-security-policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; media-src 'self' blob:; frame-ancestors 'none'",
      "x-frame-options": "DENY"
    });
    return res.end(readFileSync3(SEITE));
  }
  if (req.method === "GET" && url.pathname === "/api/wav") return wavSenden(res, url);
  const route = routen[`${req.method} ${url.pathname}`];
  if (!route) return json(res, 404, { fehler: "Nicht gefunden" });
  if (req.method === "POST" && !String(req.headers["content-type"]).startsWith("application/json")) return json(res, 415, { fehler: "Nur JSON" });
  try {
    const b = req.method === "POST" ? await koerper(req) : {};
    json(res, 200, await route(b, url));
  } catch (e) {
    json(res, 400, { fehler: kurzerFehler(e) });
  }
});
server.on("error", (e) => {
  if (e.code === "EADDRINUSE") {
    oeffnen();
    setTimeout(() => process.exit(0), 500);
  } else throw e;
});
server.listen(PORT2, "127.0.0.1", () => {
  console.log(`RAWR Techno: http://127.0.0.1:${PORT2}`);
  oeffnen();
});
function oeffnen() {
  if (process.argv.includes("--oeffnen")) spawn2("cmd.exe", ["/c", "start", "", `http://127.0.0.1:${PORT2}`], { detached: true, stdio: "ignore", windowsHide: true }).unref();
}
