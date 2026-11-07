"""List cards whose text in data/cards/riftbound.json differs from the [NEW TEXT] in docs/rules/*errata*.txt.

usage: python tools/errata_check.py [--decks]     --decks: only cards in data/decks/tournament/
The gallery data still carries some pre-errata wording; every card listed here needs its script checked against the
new text (reminder text in parentheses and line breaks are ignored)."""
import glob, json, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def norm(s):
    s = re.sub(r"\([^)]*\)", "", s or "").lower().replace("’", "'")
    return re.sub(r"\s+|\[add\]", "", s)


def errata():
    for f in sorted(glob.glob(os.path.join(ROOT, "docs/rules/*errata*.txt"))):
        lines = open(f, encoding="utf-8").read().split("\n")
        for i, line in enumerate(lines):
            if line.strip() == "[NEW TEXT]":
                j, new = i + 1, []
                while j < len(lines) and lines[j].strip() not in ("▲", "[OLD TEXT]"):
                    new.append(lines[j])
                    j += 1
                yield lines[i - 1].strip().replace("’", "'"), " ".join(new), os.path.basename(f)


def main():
    data = json.load(open(os.path.join(ROOT, "data/cards/riftbound.json"), encoding="utf-8"))
    cards = data if isinstance(data, list) else data["cards"]
    by = {}
    for c in cards:
        by.setdefault(c["name"].replace("’", "'"), c)
    only = None
    if "--decks" in sys.argv:
        ids = {c["id"]: c["name"] for c in cards}
        only = set()
        for f in glob.glob(os.path.join(ROOT, "data/decks/tournament/*.json")):
            d = json.load(open(f, encoding="utf-8"))
            only |= {e["name"] for e in d["main"]} | {ids.get(b) for b in d.get("battlefields", [])}
            only |= {ids.get(d.get("legend")), ids.get(d.get("champion"))}
    n = 0
    for name, new, src in errata():
        if only is not None and name not in only:
            continue
        c = by.get(name)
        if c is None:
            print(f"not in card data: {name} ({src})")
            continue
        if norm(new) != norm(c.get("text")):
            n += 1
            print(f"{name} ({src})\n  errata: {new}\n  data:   {(c.get('text') or '').replace(chr(10), ' / ')}")
    print(f"{n} cards differ")


if __name__ == "__main__":
    main()
