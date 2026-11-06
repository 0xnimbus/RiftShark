/* Web worker: runs the RiftShark engine in the browser with Pyodide (used by play.js when no local server answers).
   Messages in: {id, cmd, args}; out: {id, result} | {id, error} | {progress}. */
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
importScripts(PYODIDE + "pyodide.js");

const BOOT = `
import json, sys
sys.path.insert(0, "/app")
from riftsim.core.cards import CardDB
from riftsim.core.scripts import script_all
from riftsim.core.playsession import PlaySession
DB = script_all(CardDB.load("/app/data/cards/riftbound.json"))
S = PlaySession(DB)
def call(cmd, args_json):
    a = json.loads(args_json or "{}")
    if cmd == "new":
        d0 = json.load(open("/app/" + a["deck0"], encoding="utf-8"))
        d1 = json.load(open("/app/" + a["deck1"], encoding="utf-8"))
        r = S.new(d0, d1, human=a.get("human", 0), seed=a.get("seed"), ai=a.get("ai", "mcts:60"), analysis=a.get("analysis", 60))
    elif cmd == "state": r = S.payload()
    elif cmd == "choose": r = S.choose(a["index"])
    elif cmd == "hint": r = S.hint()
    elif cmd == "decks":
        ds = [dict(d, data=json.load(open("/app/" + d["path"], encoding="utf-8"))) for d in a["decks"]]
        r = {"ok": True, "decks": S.playable(ds), "server": False}
    else: r = {"ok": False, "error": "unknown command " + cmd}
    return json.dumps(r)
`;

let ready = null, manifest = null;
function progress(msg) { postMessage({ progress: msg }); }

async function boot() {
  progress("loading Python runtime…");
  const py = await loadPyodide({ indexURL: PYODIDE });
  progress("fetching engine…");
  manifest = await (await fetch("engine/manifest.json", { cache: "no-cache" })).json();
  py.FS.mkdirTree("/app");
  let n = 0;
  await Promise.all(manifest.files.map(async rel => {
    const txt = await (await fetch("engine/" + rel, { cache: "no-cache" })).text();
    const dir = "/app/" + rel.split("/").slice(0, -1).join("/");
    py.FS.mkdirTree(dir);
    py.FS.writeFile("/app/" + rel, txt);
    n++;
    if (n % 10 === 0) progress(`fetching engine… ${n}/${manifest.files.length}`);
  }));
  progress("scripting 1180 cards…");
  await py.runPythonAsync(BOOT);
  progress("");
  return py.globals.get("call");
}

onmessage = async e => {
  const { id, cmd, args } = e.data;
  try {
    if (!ready) ready = boot();
    const call = await ready;
    const a = cmd === "decks" ? { decks: manifest.decks } : (args || {});
    const out = call(cmd, JSON.stringify(a));
    postMessage({ id, result: JSON.parse(out) });
  } catch (err) {
    postMessage({ id, error: String(err && err.message || err) });
  }
};
