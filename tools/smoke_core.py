"""Play random games with engine v2 to shake out crashes. usage: python tools/smoke_core.py [n] [seed]"""
import sys, random, json, traceback, collections
sys.path.insert(0, ".")
from riftsim.core import CardDB, Deck, Game
from riftsim.core.scripts import script_all, coverage

db = script_all(CardDB.load())

def make_deck(legend_name, champ_name, seed):
    leg = db.card(legend_name)
    rng = random.Random(seed)
    pool = [c for c in db if c.type in ("unit", "spell", "gear") and not c.is_token and c.domains
            and set(c.domains) <= set(leg.domains) and not c.data_incomplete and c.set != "SFD" or False]
    pool = [c for c in pool if c.supertype != "champion"]
    rng.shuffle(pool)
    main, counts = [], collections.Counter()
    for c in pool:
        if len(main) >= 40: break
        if counts[c.name] < 3 and not c.keywords.get("unique"):
            main.append(c.id); counts[c.name] += 1
    runes = [leg.domains[0]] * 6 + [leg.domains[1]] * 6
    bfs = [b.id for b in db if b.type == "battlefield"][:3]
    return Deck(f"{legend_name} random", leg.id, db.card(champ_name).id, main, runes, bfs)

def play(seed, verbose=False):
    rng = random.Random(seed)
    d1 = make_deck("Blind Monk", "Lee Sin, Meditative" if False else "Lee Sin", seed)
    d2 = make_deck("Hand of Noxus", "Darius", seed + 1)
    g = Game(db, [d1, d2], seed=seed)
    n = 0
    while True:
        d = g.run()
        if d is None: break
        n += 1
        if n > 20000: raise RuntimeError("decision limit")
        opts = d.options
        # bias: avoid passing/ending turn when something else is possible 40% of the time
        if d.kind == "action" and len(opts) > 1 and rng.random() < 0.6:
            opts = [o for o in opts if o[0] not in ("pass", "end_turn")] or opts
        g.choose(rng.choice(opts))
    return g, n

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    s0 = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    cov, missing = coverage(db)
    print("coverage:", cov)
    res = collections.Counter()
    for s in range(s0, s0 + n):
        try:
            g, nd = play(s)
            res[g.winner] += 1
            print(f"seed {s}: winner P{g.winner} reason={g.reason} turns={g.turn} decisions={nd} points={[p.points for p in g.players]}")
        except Exception:
            print(f"seed {s}: CRASH"); traceback.print_exc(); break
    print(res)
