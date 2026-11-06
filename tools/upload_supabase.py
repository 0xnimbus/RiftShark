"""Upload a batch (results.json + replays) to Supabase.

usage: SUPABASE_URL=https://<ref>.supabase.co SUPABASE_SERVICE_KEY=<service role key> \
       python tools/upload_supabase.py out/kr/results.json [out/kr/replays] [--label "..."] [--max-replays 10]

Uses the PostgREST API with urllib only (no third-party deps). The service-role key must never be committed;
the frontend uses the anon key (read-only through row level security).
"""
import glob, gzip, json, os, subprocess, sys, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tools.export_web import strip  # noqa: E402


def post(url, key, table, rows, prefer="return=representation"):
    req = urllib.request.Request(f"{url}/rest/v1/{table}", data=json.dumps(rows).encode(), method="POST",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "Prefer": prefer})
    with urllib.request.urlopen(req) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def main(results_path, replay_dir=None, label=None, max_replays=10):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("set SUPABASE_URL and SUPABASE_SERVICE_KEY")
    res = json.load(open(results_path))
    s, results = res["summary"], res.get("games") or res.get("results")
    decks = list(s["decks"])
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        commit = None
    pols = res.get("policies") or ["?", "?"]
    batch = post(url, key, "batches", [{
        "label": label, "deck_a": decks[0], "deck_b": decks[1] if len(decks) > 1 else decks[0],
        "policy_a": str(pols[0]), "policy_b": str(pols[1] if len(pols) > 1 else pols[0]),
        "games": s["games"], "draws": s["draws"], "avg_turns": s["avg_turns"], "avg_secs": s["avg_secs"],
        "engine_commit": commit, "summary": {k: v for k, v in s.items() if k != "cards"}}])[0]
    bid = batch["id"]
    post(url, key, "games", [{
        "batch_id": bid, "seed": r["seed"], "deck0": r["decks"][0], "deck1": r["decks"][1], "winner": r["winner"],
        "reason": r["reason"], "turns": r["turns"], "points0": r["points"][0], "points1": r["points"][1], "first": r["first"],
        "decisions": r["decisions"], "secs": r["secs"], "played0": r["played"][0], "played1": r["played"][1]} for r in results],
        prefer="return=minimal")
    post(url, key, "deck_stats", [{"batch_id": bid, "deck": n, **{k: d[k] for k in ("games", "wins", "win_rate", "first_games", "first_wins", "first_win_rate", "avg_points")}}
                                  for n, d in s["decks"].items()], prefer="return=minimal")
    cards = [{"batch_id": bid, "deck": c["deck"], "card": c["card"], "games": c["games"], "played": c["played"],
              "win_rate_when_played": c["win_rate_when_played"]} for c in s["cards"]]
    for i in range(0, len(cards), 500):
        post(url, key, "card_stats", cards[i:i + 500], prefer="return=minimal")
    n = 0
    if replay_dir:
        for f in sorted(glob.glob(os.path.join(replay_dir, "*.json.gz")))[:max_replays]:
            rep = json.loads(gzip.open(f).read().decode())
            slim = {k: rep[k] for k in ("version", "seed", "decks", "policies", "result", "events") if k in rep}
            slim["frames"] = strip(rep.get("frames", []))
            post(url, key, "replays", [{"batch_id": bid, "seed": rep["seed"], "decks": [d["name"] for d in rep["decks"]],
                                        "winner": rep["result"]["winner"], "turns": rep["result"]["turns"],
                                        "frames": len(slim["frames"]), "data": slim}], prefer="return=minimal")
            n += 1
    print(f"uploaded batch {bid}: {len(results)} games, {len(cards)} card rows, {n} replays")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    label = sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv else None
    mx = int(sys.argv[sys.argv.index("--max-replays") + 1]) if "--max-replays" in sys.argv else 10
    main(args[0], args[1] if len(args) > 1 else None, label, mx)
