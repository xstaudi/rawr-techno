import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);

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
export {
  mixer,
  send
};
