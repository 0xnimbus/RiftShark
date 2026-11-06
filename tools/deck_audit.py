"""Per-card audit of one deck across a round-robin: replays its games and counts how each card and rule was used,
and checks the uses against the printed text.

usage: python tools/deck_audit.py out/rr_1745/games.json riven [--policy expert] [--workers 4] [--out FILE]
The games are replayed from their seeds (the engine is deterministic), so the counts match the round-robin results.
"""
import argparse, collections, json, os, sys, time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audit_games import _db  # noqa: E402

RIVEN_MODES = ("[Buff] me", "Spend my buff to [Stun] an enemy unit", "Spend my buff to ready me")


def replay(args):
    r, policy, key = args
    from riftsim.core.deck import Deck
    from riftsim.core.policies import make_policy
    from riftsim.core.replay import play_game
    db = _db()
    decks = [Deck.load(p, db) for p in r["paths"]]
    pols = [make_policy(policy, seed=r["seed"] * 7 + i) for i in range(2)]
    g, _ = play_game(db, decks, r["seed"], pols, record=False, max_turns=60)
    me = next(i for i, p in enumerate(r["paths"]) if key in os.path.basename(p))
    return analyse(g, db, me, r)


def analyse(g, db, me, r):
    use = collections.Counter()
    bad = []
    name = {u: o.defn.name for u, o in g.objects.items()}
    printed = lambda n: (db.card(n).energy or 0, db.card(n).power or 0)
    turn = None
    heron_pending = 0
    modes_this_turn = collections.defaultdict(set)
    last_trigger = None
    held_units = set()
    plays_this_turn = 0
    for i, e in enumerate(g.events):
        k = e["kind"]
        p = e.get("player")
        if k == "turn":
            turn, heron_pending, plays_this_turn = e.get("turn"), 0, 0
            modes_this_turn.clear()
        if k == "trigger":
            last_trigger = e
            if e.get("controller") == me:
                use["trigger: " + name.get(e["source"], "?") + " | " + e["label"][:50]] += 1
        if k == "decision" and p == me:
            dk, ch = e.get("dkind"), str(e.get("choice"))
            if dk == "mode":
                use[f"mode: {ch}"] += 1
                if ch in RIVEN_MODES and last_trigger is not None:
                    src = last_trigger["source"]
                    if ch in modes_this_turn[src]:
                        bad.append(f"turn {turn}: Riven chose '{ch}' twice in one turn")
                    modes_this_turn[src].add(ch)
            if dk == "action" and ch.startswith("hide "):
                use["hide: " + ch.split(" ", 1)[1].split("#")[0]] += 1
            if dk == "additional_cost":
                use[f"additional cost: {ch}"] += 1
            if dk == "yesno":
                lbl = (last_trigger or {}).get("label", "")[:40]
                use[f"yes/no ({name.get((last_trigger or {}).get('source'), '?')}): {ch[:50]}"] += 1
        if k == "play" and p == me:
            n = e["name"]
            use[f"play from {e.get('from_zone')}: {n}"] += 1
            if e.get("state") != "neutral" or e.get("chain", 0):
                use[f"play at reaction speed: {n}"] += 1
        if k == "event:play" and p == me:
            n = name.get(e["uid"], "?")
            plays_this_turn += 1
            if heron_pending:
                pe, pp = printed(n)
                if e.get("from_zone") == "facedown":
                    pe, pp = 0, 0
                use["Heron discount used on: " + n] += 1
                heron_pending = 0
        if k == "trigger" and e.get("controller") == me and name.get(e["source"]) == "Astral Heron":
            heron_pending = 1
        if k == "event:pay" and p == me:
            pass
        if k == "replace":
            src = e.get("source")
            if src in g.objects and g.objects[src].controller == me:
                use[f"replacement: {name.get(src)} ({e.get('event')})"] += 1
        if k == "event:hold" and p == me:
            held_units = set(e.get("units") or ())
        if k == "event:to_hand" and p == me and e.get("from_zone") == "board":
            n = name.get(e["uid"], "?")
            use[f"returned to hand: {n}"] += 1
            if n == "Blitzcrank, Impassive" and e["uid"] not in held_units:
                use["Blitzcrank returned without holding (by an effect)"] += 1
        if k == "event:to_hand" and p != me and e.get("from_zone") == "board":
            use[f"enemy returned to hand: {name.get(e['uid'], '?')}"] += 1
        if k == "event:counter" and p != me:
            use["countered an enemy spell"] += 1
        if k == "activate" and p == me:
            use[f"activate: {e['name']} | {e.get('label')}"] += 1
        if k == "event:stun" and e.get("by") == me:
            use["stunned an enemy"] += 1
        if k == "enter" and p == me and e.get("loc", ("",))[0] == "bf":
            bf = g.battlefields[e["loc"][1]]
            use["unit entered at a battlefield " + ("ready" if e.get("ready") else "exhausted")] += 1
        if k == "event:recall" and p == me:
            use[f"recalled: {name.get(e['uid'], '?')}"] += 1
        if k == "token" and p == me:
            use[f"token: {e['name']}"] += 1
        if k == "hidden_lost":
            o = g.objects.get(e["uid"])
            if o is not None and o.owner == me:
                use["hidden card lost (battlefield lost)"] += 1
        if k == "event:conquer" and p == me:
            use["conquer"] += 1
        if k == "event:hold" and p == me:
            use["hold"] += 1
    return {"seed": r["seed"], "won": g.winner == me, "use": dict(use), "bad": bad}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("games")
    ap.add_argument("key")
    ap.add_argument("--policy", default="expert")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    R = [r for r in json.load(open(a.games)) if not r.get("crash") and any(a.key in os.path.basename(p) for p in r["paths"])]
    t = time.time()
    res = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for x in ex.map(replay, [(r, a.policy, a.key) for r in R]):
            res.append(x)
            if len(res) % 20 == 0:
                print(f"{len(res)}/{len(R)} ({time.time() - t:.0f}s)", file=sys.stderr)
    tot = collections.Counter()
    games_with = collections.Counter()
    for x in res:
        tot.update(x["use"])
        games_with.update(x["use"].keys())
    out = [f"# {a.key} per-card audit: {len(res)} games, won {sum(x['won'] for x in res)}", "",
           "| use | total | games with it |", "|---|---|---|"]
    for k in sorted(tot):
        out.append(f"| {k} | {tot[k]} | {games_with[k]} |")
    bads = [b for x in res for b in x["bad"]]
    out += ["", f"Rule problems: {len(bads)}"] + [f"- {b}" for b in bads[:50]]
    txt = "\n".join(out)
    print(txt)
    if a.out:
        open(a.out, "w").write(txt + "\n")
        json.dump(res, open(a.out.replace(".md", ".json"), "w"))


if __name__ == "__main__":
    main()
