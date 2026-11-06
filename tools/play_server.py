"""Play a deck against the AI in the browser with chess-style move grading (local server).

usage: python tools/play_server.py [--port 8765] [--ai mcts:100] [--analysis 150]
then open http://localhost:8765/play.html

The same page also works without this server (GitHub Pages / any static host): it then runs the engine in the
browser with Pyodide, which is slower. Single local game session, no auth: local use only.
"""
import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from riftsim.core.cards import CardDB  # noqa: E402
from riftsim.core.playsession import PlaySession  # noqa: E402
from riftsim.core.scripts import script_all  # noqa: E402

DB = script_all(CardDB.load(os.path.join(ROOT, "data", "cards", "riftbound.json")))
LOCK = threading.Lock()
SESSION = PlaySession(DB)
DEFAULTS = {"ai": "mcts:100", "analysis": 150}


def list_decks():
    out = []
    for d in ("data/decks/tournament", "data/decks"):
        p = os.path.join(ROOT, d)
        if not os.path.isdir(p):
            continue
        for f in sorted(os.listdir(p)):
            if f.endswith(".json"):
                try:
                    name = json.load(open(os.path.join(p, f), encoding="utf-8"))["name"]
                except Exception:
                    continue
                out.append({"path": d + "/" + f, "name": name})
    return out


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(ROOT, "web"), **k)

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/decks"):
            return self._json({"ok": True, "decks": list_decks(), "server": True})
        if self.path.startswith("/api/state"):
            with LOCK:
                return self._json(SESSION.payload())
        if self.path.startswith("/api/hint"):
            with LOCK:
                return self._json(SESSION.hint())
        return super().do_GET()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        try:
            if self.path.startswith("/api/new"):
                with LOCK:
                    d0 = json.load(open(os.path.join(ROOT, body.get("deck0", "data/decks/tournament/kaisa_void.json")), encoding="utf-8"))
                    d1 = json.load(open(os.path.join(ROOT, body.get("deck1", "data/decks/tournament/riven_exile.json")), encoding="utf-8"))
                    return self._json(SESSION.new(d0, d1, human=body.get("human", 0), seed=body.get("seed", 0),
                                                  ai=body.get("ai", DEFAULTS["ai"]), analysis=body.get("analysis", DEFAULTS["analysis"])))
            if self.path.startswith("/api/choose"):
                with LOCK:
                    return self._json(SESSION.choose(body.get("index")))
        except Exception as e:  # report engine errors to the page instead of dropping the connection
            return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)
        return self._json({"ok": False, "error": "unknown endpoint"}, 404)


def main():
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    if "--ai" in sys.argv:
        DEFAULTS["ai"] = sys.argv[sys.argv.index("--ai") + 1]
    if "--analysis" in sys.argv:
        DEFAULTS["analysis"] = int(sys.argv[sys.argv.index("--analysis") + 1])
    print(f"RiftShark play server: http://localhost:{port}/play.html  (AI {DEFAULTS['ai']}, analysis {DEFAULTS['analysis']} iterations/move)")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main()
