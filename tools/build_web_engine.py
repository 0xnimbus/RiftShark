"""Bundle the engine for the browser (Pyodide): copy riftsim/core, the card database and the deck lists into
web/engine/ with a manifest.json listing every file, so web/engine_worker.js can load them without a server.

usage: python tools/build_web_engine.py        (run by .github/workflows/pages.yml before deploying web/)
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "engine")
SKIP = {"cli.py", "runner.py", "__main__.py"}  # need argparse / multiprocessing, not used in the browser


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    files, decks = [], []
    for base, _dirs, names in os.walk(os.path.join(ROOT, "riftsim", "core")):
        if "__pycache__" in base:
            continue
        for n in sorted(names):
            if n.endswith(".py") and n not in SKIP:
                rel = os.path.relpath(os.path.join(base, n), ROOT).replace(os.sep, "/")
                files.append(rel)
    files.append("riftsim/__init__.py")
    files.append("data/cards/riftbound.json")
    best = os.path.join(ROOT, "models", "best.json")
    if os.path.exists(best):        # the promoted learned generation: the play page's "Learned" difficulty
        files += ["models/best.json", "models/" + json.load(open(best))["model"]]
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
                files.append(d + "/" + f)
                decks.append({"path": d + "/" + f, "name": name})
    for rel in files:
        src = os.path.join(ROOT, rel)
        if rel == "riftsim/__init__.py" and not os.path.exists(src):
            os.makedirs(os.path.join(OUT, "riftsim"), exist_ok=True)
            open(os.path.join(OUT, rel), "w").close()
            continue
        dst = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"files": files, "decks": decks}, f, indent=1)
    print(f"web/engine: {len(files)} files, {len(decks)} decks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
