"""Export batch results and replays for the static frontend in web/data.

usage: python tools/export_web.py out/results.json out/replays web/data [--max-replays 20]
Writes web/data/results.json, web/data/replays/<name>.json and web/data/replays/index.json.
Replays must have been recorded with --snapshots for the visual viewer.
"""
import glob, gzip, json, os, sys


def strip(x, drop=("image", "keywords", "owner")):
    if isinstance(x, dict):
        return {k: strip(v, drop) for k, v in x.items() if k not in drop}
    if isinstance(x, list):
        return [strip(v, drop) for v in x]
    return x


def card_index(out_dir):
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "cards", "riftbound.json")
    cards = json.load(open(src))["cards"]
    idx = {c["id"]: {"name": c["name"], "image": c["image"], "type": c["type"], "might": c["might"], "energy": c["energy"],
                     "power": c["power"], "domains": c["domains"], "text": c["text"]} for c in cards}
    for t in ("Recruit", "Sprite", "Sand Soldier", "Mech", "Gold", "Reflection", "Bird", "Brush", "Baron Pit", "Tentacle", "Shadow Clone", "Bomb"):
        idx["TOKEN-" + t.upper().replace(" ", "")] = {"name": t, "image": "", "type": "token", "might": None, "energy": 0, "power": 0, "domains": [], "text": ""}
    json.dump(idx, open(os.path.join(out_dir, "cards.json"), "w"))


def main(results_path, replay_dir, out_dir, max_replays=20):
    os.makedirs(os.path.join(out_dir, "replays"), exist_ok=True)
    card_index(out_dir)
    res = json.load(open(results_path))
    json.dump(res, open(os.path.join(out_dir, "results.json"), "w"))
    index = []
    files = sorted(glob.glob(os.path.join(replay_dir, "*.json.gz")))[:max_replays]
    for f in files:
        rep = json.loads(gzip.open(f).read().decode())
        name = os.path.basename(f).replace(".json.gz", "")
        slim = {k: rep[k] for k in ("version", "seed", "decks", "policies", "result", "events") if k in rep}
        slim["frames"] = strip(rep.get("frames", []))
        json.dump(slim, open(os.path.join(out_dir, "replays", name + ".json"), "w"))
        index.append({"name": name, "seed": rep["seed"], "decks": [d["name"] for d in rep["decks"]], "result": rep["result"],
                      "frames": len(rep.get("frames", []))})
    json.dump({"replays": index, "generated": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()},
              open(os.path.join(out_dir, "replays", "index.json"), "w"))
    print(f"exported {len(index)} replays and results to {out_dir}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mx = 20
    if "--max-replays" in sys.argv:
        mx = int(sys.argv[sys.argv.index("--max-replays") + 1])
    main(args[0], args[1], args[2], mx)
