#!/usr/bin/env node
import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);

// ableton/mix.mjs
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

// ableton/client.mjs
import net from "node:net";
var MIXER_PORT = 9878;
var PORT = Number(process.env.ABLETON_PORT || MIXER_PORT);
var TIMEOUT_MS = 3e4;
var mixer = (type, params = {}) => send(type, params, MIXER_PORT);
function send(type, params = {}, port = PORT) {
  return new Promise((resolve, reject) => {
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
      if (r.status === "success") resolve(r.result);
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

// ableton/umgebung.mjs
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
var VENV = join(homedir(), ".venvs", "stems", "Scripts", "python.exe");
var PYTHON = process.env.TECHNO_PYTHON || (existsSync(VENV) ? VENV : "python");
var ps;
function powershell() {
  ps ??= spawnSync("pwsh", ["-NoProfile", "-Command", "exit 0"]).status === 0 ? "pwsh" : "powershell.exe";
  return ps;
}

// ableton/mix.mjs
var PEGEL = fileURLToPath(new URL("../scripts/desktop/pegel.ps1", import.meta.url));
function dbfsAusPegel(text) {
  const m = text.split(/\r?\n/).find((l) => l.startsWith("Ableton"))?.match(/\((-?[\d.,]+|-inf) dBFS\)/);
  if (!m) return null;
  return m[1] === "-inf" ? -Infinity : Number(m[1].replace(",", "."));
}
function pegel(sekunden) {
  return dbfsAusPegel(execFileSync(powershell(), ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PEGEL, "-Sekunden", String(sekunden)], { encoding: "utf8" }));
}
async function abspielen(startBeat) {
  await send("start_playback");
  await send("set_current_song_time", { time: startBeat });
}
async function messen(startBeat = 0, sekunden = 4) {
  const spuren = (await mixer("meters")).filter((k) => typeof k.index === "number" && !/^[A-Z]-/.test(k.name));
  const aus = [];
  try {
    for (const s of spuren) {
      await mixer("solo", { track: s.index, on: true });
      await abspielen(startBeat);
      aus.push({ spur: s.name, fader_db: s.fader_db, spitze_dbfs: pegel(sekunden) });
      await mixer("solo", { track: s.index, on: false });
    }
    await abspielen(startBeat);
    aus.push({ spur: "Master", fader_db: null, spitze_dbfs: pegel(sekunden) });
  } finally {
    for (const s of spuren) await mixer("solo", { track: s.index, on: false }).catch(() => {
    });
    await send("stop_playback");
  }
  return aus;
}
if (process.argv[1]?.endsWith("mix.mjs")) {
  const [start = "0", sek = "4"] = process.argv.slice(2);
  messen(Number(start), Number(sek)).then((r) => console.table(r.filter((k) => k.spitze_dbfs > -Infinity || k.spur === "Master"))).catch((e) => {
    console.error(`Abbruch: ${e.message}`);
    process.exit(1);
  });
}
export {
  dbfsAusPegel,
  messen
};
