"""Build data/decks/tournament/*.json from a deck spec captured from riftdecks.com (tools/deckspecs/*.json).

Usage: python tools/build_decks.py tools/deckspecs/radiance_2026-11.json
Each spec entry holds the riftdecks sections (LEGEND, CHAMPION, UNIT, GEAR, SPELL, BATTLEFIELDS, RUNES) plus source
metadata. Card names map to the latest printing in data/cards/riftbound.json (CR 132: same name = same card).
The script reports every card the engine does not fully script, so the deck stays out of play until it is."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from riftsim.core.cards import CardDB          # noqa: E402
from riftsim.core.deck import Deck             # noqa: E402
from riftsim.core.scripts import script_all    # noqa: E402


def legend_card(db, name):
    """riftdecks names legends 'Akali, Rogue Assassin'; the gallery data names some only 'Rogue Assassin'."""
    try:
        return db.card(name)
    except KeyError:
        c = db.card(name.split(", ", 1)[1])
        assert c.type == "legend", name
        return c


def build(key, spec, db):
    L = spec["list"]
    legend = legend_card(db, L["LEGEND"][0][1])
    champion = db.card(L["CHAMPION"][0][1])
    main = []
    for sec in ("UNIT", "GEAR", "SPELL"):
        for n, name in L.get(sec, []):
            main.append({"id": db.card(name).id, "name": db.card(name).name, "count": n})
    runes = {}
    for n, name in L["RUNES"]:
        runes[name.split()[0].lower()] = n
    bfs = [db.card(name).id for _, name in L["BATTLEFIELDS"]]
    meta = {k: spec[k] for k in ("url", "player", "placement", "tournament", "players", "date")}
    meta["set"] = "Radiance"
    meta["sideboard"] = [[name, n] for n, name in spec.get("sideboard", [])]
    place = spec["placement"]
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(place if place < 20 else place % 10, "th")
    return {"name": f"{legend.name} ({spec['player']}, {place}{suffix} {spec['tournament']})",
            "legend": legend.id, "champion": champion.id, "main": main, "runes": runes,
            "battlefields": bfs, "source": meta}


def main(path):
    db = script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))
    specs = json.loads(pathlib.Path(path).read_text())
    missing = {}
    for key, spec in specs.items():
        d = build(key, spec, db)
        out = ROOT / "data/decks/tournament" / f"{key}.json"
        out.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
        deck = Deck.from_dict(d, db) if hasattr(Deck, "from_dict") else Deck.load(str(out), db)
        errs = list(dict.fromkeys(deck.validate(db) or []))
        print(f"{key}: {sum(c['count'] for c in d['main'])} main, {len(errs)} problems")
        for e in errs:
            print("   ", e)
            if "not fully scripted" in e:
                missing.setdefault(e.split(" is not fully")[0], []).append(key)
    print(f"\n{len(missing)} cards not fully scripted:")
    for name, keys in sorted(missing.items()):
        c = db.card(name)
        print(f"  {c.id} {name} [{c.script_status}] ({', '.join(keys)}): {c.text}")


if __name__ == "__main__":
    main(sys.argv[1])
