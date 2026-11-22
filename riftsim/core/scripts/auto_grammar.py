"""Grammar-based auto-scripter for Riftbound rules text.

Each line of rules text is one ability. A line is classified as activated ("COST: EFFECT"),
triggered ("When ..., EFFECT"), static ("While ..., EFFECT" / "Friendly units here have +1 [M]"),
or (for spells) the spell effect. Effect sentences are matched against templates that build
instruction trees from ops.py. Anything that does not parse makes the ability (and card) 'partial';
such cards are reported by coverage() and are scripted by hand in cards_manual.py.
"""
from __future__ import annotations

import re

from ..abilities import Static, Triggered, Activated, PlayPermission, Replacement, _by_me, _first_in_batch
from ..selectors import Sel
from .. import ops as O
from ..vm import Ref

DOMAIN_WORDS = {"fury": "fury", "calm": "calm", "mind": "mind", "body": "body", "chaos": "chaos", "order": "order"}
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "a": 1, "an": 1}
KW_NAMES = ["assault", "shield", "tank", "ganking", "deflect", "temporary", "backline", "hidden", "ambush", "accelerate",
            "vision", "deathknell", "hunt", "disarm", "reaction", "action", "legion", "deploy", "weaponmaster", "quick-draw"]


class ParseError(Exception):
    pass


def clean_text(t):
    t = re.sub(r"\s*\(([^()]*)\)", "", t)              # reminder text
    t = re.sub(r"\.(\[(?!M\]|A\]|C\]|T\]))", ".\n\\1", t)   # "effect.[1], [T]: ..." lost line breaks
    t = re.sub(r"\[(Predict|Burn) (\d+)\]", r"\1 \2", t)
    t = re.sub(r"([a-z\]])\.(?=[A-Z][a-z])", r"\1. ", t)                 # lost space after a sentence end
    t = t.replace("’", "'").replace("–", "-").replace("—", "-").replace(" ", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


# ---------------------------------------------------------------------------- object phrases
UNIT_WORDS = r"(?:unit|units)"


def _num(s):
    s = s.lower()
    if s.isdigit():
        return int(s)
    return NUM_WORDS.get(s)


def parse_sel(phrase, allow_self=True):
    """Turn an object phrase into (Sel or Ref, n, up_to, plural). Raises ParseError."""
    p = phrase.strip().rstrip(".").strip()
    pl = p.lower()
    if pl in ("me", "this", "this unit", "this gear", "myself"):
        return Ref("self"), 1, False, False
    if pl in ("it", "that unit", "them", "those units", "that gear", "that card", "the chosen unit", "it or them"):
        return Ref("t"), 1, False, False
    n, up_to, plural = 1, False, False
    m = re.match(r"up to (\w+) ", pl)
    if m and _num(m.group(1)):
        n, up_to = _num(m.group(1)), True
        pl = pl[m.end():]
        plural = True
    m = re.match(r"(?:each of )?(?:any number of|all|each|every) ", pl)
    if m:
        pl = pl[m.end():]
        plural = True
        n = None
    m = re.match(r"(?:an?|another|other|one) ", pl)
    other = False
    if m:
        other = m.group(0).strip() in ("another", "other")
        pl = pl[m.end():]
    m = re.match(r"(two|three|four|\d+) ", pl)
    if m:
        n = _num(m.group(1))
        pl = pl[m.end():]
        plural = True
    kw = {}
    side = None
    where = None
    zone = "board"
    kind = None
    # modifiers before the noun
    words = pl.split(" ")
    i = 0
    tags = []
    while i < len(words):
        w = words[i]
        if w == "your":
            side = "friendly"
        elif w in ("friendly",):
            side = "friendly"
        elif w in ("enemy",):
            side = "enemy"
        elif w in ("other", "another"):
            other = True
        elif w in ("exhausted",):
            kw["exhausted"] = True
        elif w in ("ready",):
            kw["ready"] = True
        elif w in ("buffed",):
            kw["buffed"] = True
        elif w in ("stunned",):
            kw["stunned"] = True
        elif w in ("empowered",):
            kw["empowered"] = True
        elif w in ("damaged",):
            kw["damaged"] = True
        elif w in ("attacking",):
            kw["pred"] = lambda g, c, u: g.objects[u].designation == "attacker"
        elif w in ("defending",):
            kw["pred"] = lambda g, c, u: g.objects[u].designation == "defender"
        elif w in ("[mighty]", "mighty"):
            kw["mighty"] = True
        elif w in ("facedown", "face-down", "hidden"):
            zone = "facedown"
        elif w in ("token",):
            kw["token"] = True
        elif w in ("non-token",):
            kw["token"] = False
        elif w in ("champion",):
            kw["supertype"] = "champion"
        elif w in ("non-champion",):
            kw["pred"] = lambda g, c, u: g.chars(u).supertype != "champion"
        elif w in DOMAIN_WORDS:
            dom = DOMAIN_WORDS[w]
            kw["pred"] = (lambda d: lambda g, c, u: d in g.chars(u).domains)(dom)
        elif w in ("unit", "units"):
            kind = "unit"
            i += 1
            break
        elif w in ("gear", "gears"):
            kind = "gear"
            i += 1
            break
        elif w in ("permanent", "permanents"):
            kind = "permanent"
            i += 1
            break
        elif w in ("equipment",):
            kind = "equipment"
            i += 1
            break
        elif w in ("spell",):
            kind = "spell"
            i += 1
            break
        elif w in ("rune", "runes"):
            kind = "rune"
            i += 1
            break
        elif w in ("legend",):
            kind = "legend"
            i += 1
            break
        elif w in ("battlefield",):
            kind = "battlefield"
            i += 1
            break
        elif w in ("card", "cards"):
            kind = "card"
            i += 1
            break
        elif re.match(r"^[a-z'\-]+$", w) and w[0].isalpha() and w not in ("the",):
            tags.append(w)       # tribe tag such as "yordle", "noxian"
        else:
            raise ParseError(f"object modifier {w!r} in {phrase!r}")
        i += 1
    if kind is None and tags:
        kind = "unit"
        tags = [t[:-1] if t.endswith("s") and not t.endswith("ss") else t for t in tags]
        if side is None and ("your" in pl.split(" ")[:1] or pl.startswith("your ")):
            side = "friendly"
    if kind is None:
        raise ParseError(f"no noun in {phrase!r}")
    rest = " ".join(words[i:])
    # "unit or gear"
    if rest.startswith("or gear"):
        kind = "permanent"
        rest = rest[len("or gear"):].strip()
    if rest.startswith("or a gear"):
        kind = "permanent"
        rest = rest[len("or a gear"):].strip()
    # trailing qualifiers
    if rest:
        m = re.match(r"(?:here|at this battlefield)\b(.*)", rest)
        if m:
            where = "here"
            rest = m.group(1).strip()
    if rest.startswith("you control"):
        side = "friendly"
        rest = rest[len("you control"):].strip()
    if rest.startswith("an opponent controls"):
        side = "enemy"
        rest = rest[len("an opponent controls"):].strip()
    if rest.startswith("at a battlefield"):
        where = "battlefield"
        rest = rest[len("at a battlefield"):].strip()
    if rest.startswith("at a different battlefield") or rest.startswith("at another battlefield"):
        where = "battlefield"
        kw["pred"] = lambda g, c, u: g.objects[u].location != c.here
        rest = re.sub(r"^at (a different|another) battlefield", "", rest).strip()
    if rest.startswith("in your base") or rest.startswith("at your base"):
        where = "own_base"
        rest = rest[len("in your base"):].strip()
    if rest.startswith("in a base") or rest.startswith("at a base"):
        where = "base"
        rest = rest[len("in a base"):].strip()
    if rest.startswith("in combat"):
        where = "in_combat"
        rest = rest[len("in combat"):].strip()
    if rest.startswith("at its location") or rest.startswith("at the same location") or rest.startswith("there"):
        where = "loc:__tloc"
        rest = re.sub(r"^(at its location|at the same location|there)", "", rest).strip()
    if rest.startswith("here"):
        where = "here"
        rest = rest[4:].strip()
    m = re.match(r"with (\d+) \[m\] or (less|more)\b(.*)", rest)
    if m:
        if m.group(2) == "less":
            kw["max_might"] = int(m.group(1))
        else:
            kw["min_might"] = int(m.group(1))
        rest = m.group(3).strip()
    m = re.match(r"with \[?(\w[\w\- ]*?)\]?(?: (\d+))?(?:\s+(.*))?$", rest)
    if m and m.group(1).lower().replace(" ", "_").replace("-", "_") in KEYWORD_NAMES:
        kw["keyword"] = m.group(1).lower().replace(" ", "_").replace("-", "_")
        rest = (m.group(3) or "").strip()
    m = re.match(r"with less might than (me|it)$", rest)
    if m:
        ref = "self" if m.group(1) == "me" else "t"
        kw["pred"] = (lambda r: lambda g, c, u: (g.chars(u).might or 0) < (g.chars(c.source if r == "self" else c.vars.get("t")).might or 0))(ref)
        rest = ""
    m = re.match(r"with energy cost (?:no more than \[(\d+)\]|\[(\d+)\] or less)(?: and (?:with )?power cost no more than \[a\])?$", rest)
    if m:
        n = int(m.group(1) or m.group(2))
        kw["pred"] = (lambda n: lambda g, c, u: (g.objects[u].base_defn().energy or 0) <= n)(n)
        rest = ""
    if rest.startswith("at battlefields"):
        where = "battlefield"
        rest = rest[len("at battlefields"):].strip()
    if rest.startswith("in bases"):
        where = "base"
        rest = rest[len("in bases"):].strip()
    m = re.match(r"without \[?(\w[\w\- ]*?)\]?(?: (\d+))?(?:\s+(.*))?$", rest)
    if m:
        k2 = m.group(1).lower().replace(" ", "_").replace("-", "_")
        kw["pred"] = (lambda k: lambda g, c, u: not g.chars(u).keywords.get(k))(k2)
        rest = (m.group(3) or "").strip()
    m = re.match(r"from your trash\b(.*)", rest)
    if m:
        zone = "trash"
        side = None
        kw["owner"] = lambda g, c: c.controller
        rest = m.group(1).strip()
    m = re.match(r"in your trash\b(.*)", rest)
    if m:
        zone = "trash"
        kw["owner"] = lambda g, c: c.controller
        rest = m.group(1).strip()
    m = re.match(r"(?:in|from) your hand\b(.*)", rest)
    if m:
        zone = "hand"
        kw["owner"] = lambda g, c: c.controller
        rest = m.group(1).strip()
    if rest.startswith("you control"):
        side = "friendly"
        rest = rest[len("you control"):].strip()
    if rest.startswith("that isn't me") or rest.startswith("other than me"):
        other = True
        rest = re.sub(r"^(that isn't me|other than me)", "", rest).strip()
    if rest.startswith("that is attacking") or rest.startswith("that's attacking"):
        kw["pred"] = lambda g, c, u: g.objects[u].designation == "attacker"
        rest = re.sub(r"^(that is|that's) attacking", "", rest).strip()
    if rest.startswith("with a buff") or rest.startswith("that is buffed"):
        kw["buffed"] = True
        rest = re.sub(r"^(with a buff|that is buffed)", "", rest).strip()
    if rest:
        raise ParseError(f"unparsed object qualifier {rest!r} in {phrase!r}")
    if tags:
        kw["tags"] = [t.capitalize() if t != "void" else "Void" for t in tags]
    if kind == "card" and zone == "board":
        raise ParseError(f"card without zone in {phrase!r}")
    sel = Sel(kind, side=side, where=where, zone=zone, other=other, **kw)
    return sel, n, up_to, plural


def choose(phrase, out="t", targeted=True, player=None):
    """Build a chooser instruction for an object phrase. Returns (instrs, ref, is_all)."""
    sel, n, up_to, plural = parse_sel(phrase)
    if isinstance(sel, Ref):
        return [], sel, False
    if n is None:
        return [], sel, True
    if n == 1 and not up_to:
        return [O.Choose(sel, out=out, targeted=targeted, player=player)], Ref(out), False
    return [O.Choose(sel, out=out, n=n, up_to=up_to, targeted=targeted, player=player)], Ref(out), True


# ---------------------------------------------------------------------------- amounts
def parse_amount(s, ctx_hint=None):
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    if s in NUM_WORDS:
        return NUM_WORDS[s]
    if s == "x":
        return Ref("x")
    m = re.match(r"(?:equal to )?(?:its|their) might$", s)
    if m:
        return O.might_of(Ref("t"))
    m = re.match(r"(?:equal to )?my might$", s)
    if m:
        return O.might_of(Ref("self"))
    m = re.match(r"(?:equal to )?the number of (.+)$", s)
    if m:
        return count_phrase(m.group(1))
    m = re.match(r"(?:equal to )?(?:your|the number of your) (.+)$", s)
    if m:
        return count_phrase("your " + m.group(1))
    raise ParseError(f"amount {s!r}")


def count_phrase(p):
    p = p.strip().rstrip(".")
    p = re.sub(r"^of ", "", p)
    p = BRACKET_WORDS.sub(lambda m: m.group(1), p)
    m = re.match(r"other (exhausted |buffed )?units? you control( here)?$", p)
    if m:
        kw = {"exhausted": True} if m.group(1) == "exhausted " else ({"buffed": True} if m.group(1) else {})
        return O.count(Sel("unit", side="friendly", other=True, where="here" if m.group(2) else None, **kw))
    m = re.match(r"token units? you control$", p)
    if m:
        return O.count(Sel("unit", side="friendly", token=True))
    m = re.match(r"equipment you control$", p)
    if m:
        return O.count(Sel("gear", side="friendly", tags=["Equipment"]))
    m = re.match(r"(?:your )?\[?mighty\]? units(?: you control)?$", p)
    if m:
        return O.count(Sel("unit", side="friendly", mighty=True))
    m = re.match(r"(?:friendly )?units (?:you control )?(here|at this battlefield)$", p)
    if m:
        return O.count(Sel("unit", side="friendly", where="here"))
    m = re.match(r"units here$", p)
    if m:
        return O.count(Sel("unit", where="here"))
    m = re.match(r"enemy units here$", p)
    if m:
        return O.count(Sel("unit", side="enemy", where="here"))
    m = re.match(r"(?:your |friendly )?units(?: you control)?$", p)
    if m:
        return O.count(Sel("unit", side="friendly"))
    m = re.match(r"(?:your |friendly )?(\w+) units(?: you control)?$", p)
    if m and m.group(1) not in ("enemy", "other"):
        return O.count(Sel("unit", side="friendly", tags=[m.group(1).capitalize()]))
    m = re.match(r"other friendly (\w+) units$", p)
    if m:
        return O.count(Sel("unit", side="friendly", tags=[m.group(1).capitalize()], other=True))
    m = re.match(r"other friendly units(?: here)?$", p)
    if m:
        return O.count(Sel("unit", side="friendly", other=True, where="here" if "here" in p else None))
    m = re.match(r"cards in your hand$", p)
    if m:
        return O.hand_size()
    m = re.match(r"exhausted units you control$", p)
    if m:
        return O.count(Sel("unit", side="friendly", exhausted=True))
    m = re.match(r"(?:friendly )?gear(?: you control)?$", p)
    if m:
        return O.count(Sel("gear", side="friendly"))
    m = re.match(r"battlefields you(?: or allies)? control$", p)
    if m:
        return lambda g, c: sum(1 for b in g.battlefields if b.controller == c.controller)
    m = re.match(r"runes you control$", p)
    if m:
        return lambda g, c: len(g.players[c.controller].runes)
    m = re.match(r"cards in your trash$", p)
    if m:
        return lambda g, c: len(g.players[c.controller].trash)
    m = re.match(r"(?:your )?xp$", p)
    if m:
        return lambda g, c: g.players[c.controller].xp
    m = re.match(r"buffed units you control$", p)
    if m:
        return O.count(Sel("unit", side="friendly", buffed=True))
    raise ParseError(f"count {p!r}")


# ---------------------------------------------------------------------------- effect sentences
KEYWORD_NAMES = {"accelerate", "assault", "deathknell", "deflect", "ganking", "hidden", "legion", "shield", "tank", "temporary",
                 "vision", "equip", "quick_draw", "repeat", "weaponmaster", "ambush", "hunt", "level", "unique", "backline",
                 "empower", "empowered", "flow", "deploy", "disarm", "mighty", "reaction", "action"}


def _loc_phrase(p):
    p = p.strip().rstrip(".").lower()
    if p in ("here", "to here", "this battlefield", "to this battlefield", "to my battlefield", "to my location"):
        return "here"
    if p in ("to that battlefield", "to the chosen battlefield"):
        return Ref("__bl")
    if p in ("to your base", "your base", "to base", "to its base", "to their base", "to its controller's base", "to base.", "base"):
        return "base"
    if p in ("to a battlefield", "a battlefield"):
        return ("choose_bf", None)
    if p in ("to another battlefield", "to a different battlefield"):
        return ("choose_bf", "other")
    if p in ("to its location", "to the same location", "to my location", "there"):
        return Ref("__tloc")
    if p in ("to an open battlefield", "to an empty battlefield"):
        return ("choose_bf", "open")
    if p in ("to a battlefield you control", "to a battlefield you or an ally controls"):
        return ("choose_bf", "controlled")
    raise ParseError(f"location {p!r}")


def _move_dest(dest, out="__dest"):
    """Instructions + ref for a destination phrase."""
    d = _loc_phrase(dest)
    if d == "here":
        return [], lambda g, c: c.here
    if d == "base":
        return [], "base"
    if isinstance(d, Ref):
        return [], d
    if isinstance(d, tuple):
        mode = d[1]
        pred = None
        if mode == "other":
            pred = lambda g, c, l: l != c.here
        elif mode == "open":
            pred = lambda g, c, l: not g.units_at(l)
        elif mode == "controlled":
            pred = lambda g, c, l: g.battlefields[l[1]].controller == c.controller
        return [O.ChooseLocation(out=out, pred=pred)], Ref(out)
    raise ParseError(dest)


def parse_effect(text, state=None):
    """Parse one or more sentences into an instruction list."""
    state = state if state is not None else {"tcount": 0}
    text = text.strip()
    if not text:
        return []
    m = re.match(r"choose one( that hasn't been chosen this turn)?\s*[-—:]\s*(.+)$", text, re.I | re.S)
    if m:
        modes = []
        for sent in [x.strip() for x in re.split(r"(?<=[.!])\s*(?=[A-Z\[])", m.group(2)) if x.strip()]:
            modes.append((sent.rstrip(".")[:40], parse_sentence(sent, state)))
        return [O.ChooseMode(modes, exclude_used=bool(m.group(1)))]
    # split into sentences; keep "If you do," attached to the next sentence
    sents = [s.strip() for s in re.split(r"(?<=[.!])\s+(?=[A-Z\[])", text) if s.strip()]
    out = []
    for s in sents:
        out.extend(parse_sentence(s, state))
    return out


def _next_out(state):
    state["tcount"] += 1
    return "t" if state["tcount"] == 1 else f"t{state['tcount']}"


BRACKET_WORDS = re.compile(r"\[(buff|stun|predict|burn|add|mighty|empowered|hidden|equip|temporary)\]", re.I)


def _each_player_kills(kind):
    """"Each player kills one of their units/gear": not a target (CR 355.10.e). Each player, the spell's controller
    first, picks as the spell resolves, then the picked objects die at the same time."""
    a = O.Choose(Sel(kind, side="friendly"), out="__k1", targeted=False)
    b = O.Choose(Sel(kind, side="enemy"), out="__k2", targeted=False, player="opponent")
    a.at_resolution = b.at_resolution = True
    return [a, b, O.Kill(lambda g, c: [u for u in (c.vars.get("__k1"), c.vars.get("__k2")) if u is not None])]


def _lift_choices(instrs):
    """"You may pay [1] to stun a unit": the unit is a target chosen as the ability goes on the chain, independently of
    the decision to pay (CR 355.12, 355.5): move the effect's leading choices ahead of the cost so they are hoisted."""
    lead = []
    while instrs and isinstance(instrs[0], O.Choose) and not getattr(instrs[0], "at_resolution", False) and instrs[0].targeted:
        lead.append(instrs.pop(0))
    return lead, instrs


def parse_sentence(s, state):
    s = s.strip()
    if s.endswith("."):
        s = s[:-1]
    s = BRACKET_WORDS.sub(lambda m: m.group(1), s)
    sl = s.lower()
    # "X, then Y" / "X and then Y"
    m = re.match(r"(.+?), (?:and )?then (.+)$", s, re.I)
    if m and not sl.startswith("look at") and not sl.startswith("banish") and not sl.startswith("deal"):
        return parse_sentence(m.group(1), state) + parse_sentence(m.group(2), state)
    m = re.match(r"pay ((?:\[[^\]]+\])+) to (.+)$", s, re.I)
    if m:
        from . import parse_cost
        c = parse_cost(m.group(1))
        lead, eff = _lift_choices(parse_sentence(m.group(2), state))
        return lead + [O.PayResources(c["energy"], c["power"], out="__paid", optional=False), O.If(O.has_var("__paid"), eff + [O.SetVar("__did", True)])]
    m = re.match(r"you score (\w+) points?$", sl)
    if m:
        return [O.GainPoints(parse_amount(m.group(1)))]
    m = re.match(r"(give me [+\-]\d+ \[m\] this turn) and ready me$", sl)
    if m:
        return parse_sentence(m.group(1), state) + [O.Ready(Ref("self"))]
    m = re.match(r"give (.+?) temporary$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.GiveKeyword(ref, "temporary", True, duration="permanent")]
    m = re.match(r"(?:it|they) gains? \[(\w+)( \d+)?\] this (turn|combat)$", sl)
    if m:
        return [O.GiveKeyword(Ref("t"), m.group(1).lower(), int(m.group(2)) if m.group(2) else True, duration=m.group(3))]
    m = re.match(r"play (?:it|them) to (?:your )?base, ignoring (?:its|their) cost$", sl)
    if m:
        return [O.PlayCard(Ref("t"), ignore="all", loc=lambda g, c: ("base", c.controller))]
    m = re.match(r"play (?:it|them)(?: here)?, ignoring (?:its|their) cost$", sl)
    if m:
        return [O.PlayCard(Ref("t"), ignore="all")]
    m = re.match(r"(?:you may )?play (?:it|them), ignoring (?:its|their) energy cost$", sl)
    if m:
        return [O.PlayCard(Ref("t"), ignore="energy")]
    m = re.match(r"play (an? (?:unit|spell|gear|card)) costing no more than \[(\d+)\](?: and no more than \[a\])? from your trash, ignoring its cost$", sl)
    if m:
        sel, _, _, _ = parse_sel(m.group(1) + " from your trash")
        n = int(m.group(2))
        sel.pred = lambda g, c, u, n=n: (g.objects[u].defn.energy or 0) <= n
        return [O.Choose(sel, out="__pc", targeted=False), O.PlayCard(Ref("__pc"), ignore="all")]
    m = re.match(r"the next unit you play this turn enters ready$", sl)
    if m:
        return [O.DelayedPassive("enter_ready", {}, uses=1)]
    m = re.match(r"units you play this turn enter ready$", sl)
    if m:
        return [O.DelayedPassive("enter_ready", {}, uses=None)]
    m = re.match(r"the next spell you play this turn costs \[(\d+)\] less$", sl)
    if m:
        return [O.DelayedPassive("cost_reduce", {"energy": int(m.group(1)), "filter": lambda g, u: g.objects[u].base_defn().type == "spell"}, uses=1)]
    m = re.match(r"the next (?:spell|unit|card) you play this turn deals (\d+) bonus damage$", sl)
    if m:
        return [O.DelayedPassive("bonus_damage", {"amount": int(m.group(1)), "spell_only": True}, uses=1)]
    m = re.match(r"the next unit you play this turn costs \[(\d+)\] less$", sl)
    if m:
        return [O.DelayedPassive("cost_reduce", {"energy": int(m.group(1)), "filter": lambda g, u: g.objects[u].base_defn().is_unit}, uses=1)]
    m = re.match(r"the next (?:spell|unit|card) you play this turn costs \[(\d+)\] less$", sl)
    if m:
        return [O.DelayedPassive("cost_reduce", {"energy": int(m.group(1))}, uses=1)]
    m = re.match(r"pay ((?:\[[^\]]+\])+)$", sl)
    if m:
        from . import parse_cost
        c = parse_cost(m.group(1).upper())
        return [O.PayResources(c["energy"], c["power"], out="__did", optional=False)]
    m = re.match(r"counter a spell that costs no more than \[(\d+)\]( and no more than \[a\])?$", sl)
    if m:
        n = int(m.group(1))
        pmax = 1 if m.group(2) else 99
        return [O.Choose(Sel("spell", zone="chain", pred=lambda g, c, u, n=n, pmax=pmax: any(it.uid == u and it.kind == "spell" for it in g.chain) and (g.objects[u].defn.energy or 0) <= n and (g.objects[u].defn.power or 0) <= pmax), out="__sp", targeted=True),
                O.CounterItem(lambda g, c: next((it.id for it in g.chain if it.uid == c.vars.get("__sp")), None))]
    m = re.match(r"recycle one of your runes$", sl)
    if m:
        return [O.Choose(Sel("rune", side="friendly"), out="__rn", targeted=False), O.Recycle(Ref("__rn"))]
    m = re.match(r"each player kills one of their gear$", sl)
    if m:
        return _each_player_kills("gear")
    m = re.match(r"prevent all spell and ability damage this turn$", sl)
    if m:
        return [O.DelayedPassive("replace:damage", {"applies": lambda g, c, ev: not ev.get("combat") and not ev.get("unit_source"), "replace": lambda g, c, ev: None})]
    m = re.match(r"put (\w+) into your hand and recycle the rest$", sl)
    if m:
        return [O.ChooseFromList(lambda g, c: list(c.vars.get("looked", [])), out="__pick", n=_num(m.group(1)) or 1), O.ToHand(Ref("__pick")),
                O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"])]
    m = re.match(r"spend (\d+) xp$", sl)
    if m:
        return [O.SpendXP(int(m.group(1)), out="__did", optional=False)]
    m = re.match(r"they reveal their hand$", sl)
    if m:
        return [O.Emit("reveal", player=lambda g, c: g.opponent(c.controller), cards=lambda g, c: list(g.players[g.opponent(c.controller)].hand))]
    m = re.match(r"reveal the top card of your (?:main )?deck$", sl)
    if m:
        return [O.Look(1, out="looked", reveal=True)]
    m = re.match(r"(?:then )?recycle it$", sl)
    if m:
        return [O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"] if c.vars.get("looked") else ([c.vars["t"]] if c.vars.get("t") else []))]
    m = re.match(r"ready me$", sl)
    if m:
        return [O.Ready(Ref("self"))]
    m = re.match(r"exhaust me$", sl)
    if m:
        return [O.Exhaust(Ref("self"))]
    m = re.match(r"kill me$", sl)
    if m:
        return [O.Kill(Ref("self"))]
    m = re.match(r"heal me$", sl)
    if m:
        return [O.Heal(Ref("self"))]
    m = re.match(r"give (.+?) ([+\-]\d+) \[m\] this turn and (.+?) ([+\-]\d+) \[m\] this turn$", sl)
    if m:
        a = parse_sentence(f"give {m.group(1)} {m.group(2)} [m] this turn", state)
        b = parse_sentence(f"give {m.group(3)} {m.group(4)} [m] this turn", state)
        return a + b
    m = re.match(r"choose (.+?) and (.+)$", sl)
    if m and ("unit" in m.group(1) or "gear" in m.group(1)):
        try:
            a = parse_sentence("choose " + m.group(1), state)
            b = parse_sentence("choose " + m.group(2), state)
            return a + b
        except ParseError:
            pass
    # "Deal damage equal to my/its Might": the spell or ability deals it (only "I/it/they deal ..." names a unit as
    # the source, CR 418.6.b.3)
    m = re.match(r"deal damage equal to my might to (.+)$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.Deal(O.might_of(Ref("self")), ref)]
    m = re.match(r"deal damage equal to (?:its|their) might to (.+)$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.Deal(O.might_of(Ref("t")), ref)]
    m = re.match(r"the next time (it|they) (?:dies|die) this turn, recall (?:it|them) exhausted instead$", sl)
    if m:
        return [O.DelayedPassive("replace:die", {"applies": lambda g, c, ev: ev.get("uid") == c.vars.get("t"),
                                                 "replace": lambda g, c, ev: dict(ev, replaced_with="recall", exhaust=True)}, uses=1)]
    m = re.match(r"move (.+?) and ready (?:it|them)$", sl)
    if m:
        return parse_sentence("move " + m.group(1), state) + [O.Ready(Ref("t"))]
    m = re.match(r"move (an? (?:friendly |enemy )?unit(?: [\w ]*?)?)$", sl)
    if m and (" to " in m.group(1) or m.group(1).endswith((" here", " there"))):
        m = None
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.ChooseLocation(out="__dest", include_bases=True, pred=lambda g, c, l: c.vars.get("t") in g.objects and g.valid_destination(c.vars["t"], l, mover=c.controller)), O.Move(ref, Ref("__dest"))]
    m = re.match(r"draw (\w+) or channel (\w+) runes? exhausted$", sl)
    if m:
        return [O.ChooseMode([("draw", [O.Draw(parse_amount(m.group(1)))]), ("channel", [O.Channel(parse_amount(m.group(2)), exhausted=True)])])]
    m = re.match(r"channel (\w+) runes? exhausted and draw (\w+)$", sl)
    if m:
        return [O.Channel(parse_amount(m.group(1)), exhausted=True), O.Draw(parse_amount(m.group(2)))]
    m = re.match(r"play (a|an|two|three) (ready )?(\d+) \[m\] (\w[\w ]*?) unit tokens?(?: with ((?:\[?(?:temporary|tank|assault|shield|deflect|ganking|legion|vision|hunt|hidden|accelerate|backline|disarm)\]?(?: \d+)?(?: and |, | )?)+))?( here| to your base| into your base| to its location| there)?$", sl)
    if m:
        cnt = _num(m.group(1)) or 1
        ready = bool(m.group(2))
        tok = m.group(4).strip().title()
        grant = None
        if m.group(5):
            grant = {k.lower().replace(" ", "_").replace("-", "_"): (int(v) if v else True) for k, v in re.findall(r"\[?([a-z][\w\-]+)\]?(?: (\d+))?", m.group(5))}
        locw = (m.group(6) or "").strip()
        loc = "here" if locw == "here" else (Ref("__tloc") if locw in ("to its location", "there") else
                                            ("base" if locw else "choose"))      # unspecified: CR 355.2.a
        return [O.PlayToken(tok, loc=loc, ready=ready, count=cnt, grant=grant)]
    m = re.match(r"play a bomb gear token to a battlefield$", sl)
    if m:
        return [O.ChooseLocation(out="__bl"), O.PlayToken("Bomb", loc=Ref("__bl"))]
    m = re.match(r"each player kills one of their units$", sl)
    if m:
        return _each_player_kills("unit")
    m = re.match(r"(?:its|their) owner channels (\w+) runes? exhausted$", sl)
    if m:
        return [O.Channel(parse_amount(m.group(1)), exhausted=True, player=O.owner_of(Ref("t")))]
    m = re.match(r"its base might becomes (\d+) this turn$", sl)
    if m:
        return [O.SetMight(Ref("t"), int(m.group(1)))]
    m = re.match(r"return me to my owner's hand$", sl)
    if m:
        return [O.ToHand(Ref("self"))]
    m = re.match(r"spend (?:a|my) buff to (.+)$", sl)
    if m:
        # CR 355.10.c.1: "[do X] to [do Y]": X is a cost, Y's choices are targets chosen as the item is finalized
        lead, eff = _lift_choices(parse_sentence(m.group(1), state))
        return lead + [O.SetVar("__did", lambda g, c: g.do_spend_buff(c.source, c)), O.If(O.has_var("__did"), eff)]
    m = re.match(r"buff me and ready me$", sl)
    if m:
        return [O.Buff(Ref("self")), O.Ready(Ref("self"))]
    m = re.match(r"activate the (conquer|hold|score) effects of (.+)$", sl)
    if m:
        sel, _, _, _ = parse_sel(m.group(2))
        return [O.ActivateTriggers(sel, m.group(1))]
    m = re.match(r"(?:its|their) controller (?:draws|draw) (\w+)$", sl)
    if m:
        return [O.Draw(parse_amount(m.group(1)), player=O.controller_of(Ref("t")))]
    m = re.match(r"gain control of (?:a spell|it)$", sl)
    if m:
        raise ParseError("gain control of spell")
    # ---- conditionals / optional
    m = re.match(r"if you do, (.*)", s, re.I)
    if m:
        return [O.If(O.has_var("__did"), parse_sentence(m.group(1), state))]
    m = re.match(r"you may (.*)", s, re.I)
    if m:
        body = parse_sentence(m.group(1), state)
        return [O.May(body + [O.SetVar("__did", True)], label=m.group(1)[:40], out="__may")]
    m = re.match(r"(?:then|and then) (.*)", s, re.I)
    if m:
        return parse_sentence(m.group(1), state)
    m = re.match(r"if (it's|it is) your (beginning phase|turn), (.*?) instead$", s, re.I)
    if m:
        raise ParseError("instead-conditional")
    m = re.match(r"if (.+?), (.*)", s, re.I)
    if m and not sl.startswith("if you do"):
        cond = parse_condition(m.group(1))
        return [O.If(cond, parse_sentence(m.group(2), state))]
    m = re.match(r"(.+?) if (.+)$", s, re.I)
    if m and " if you do" not in sl:
        try:
            cond = parse_condition(m.group(2))
            return [O.If(cond, parse_sentence(m.group(1), state))]
        except ParseError:
            pass
    m = re.match(r"opponents can't play cards this turn$", sl)
    if m:
        return [O.Do(lambda g, c: g.add_turn_effect(c, "cant_play", {"players": [q for q in range(len(g.players)) if q != c.controller]}), label="opponents can't play")]
    m = re.match(r"your next card costs ((?:\[[^\]]+\])+) less(?: this turn)?$", sl)
    if m:
        from . import parse_cost
        c = parse_cost(m.group(1).upper().replace("[A]", "[A]"))
        return [O.DelayedPassive("cost_reduce", {"energy": c["energy"], "power": len(c["power"])}, uses=1)]
    m = re.match(r"predict equal to its power cost$", sl)
    if m:
        return [O.Predict(lambda g, c: (c.shown_off or {}).get("power", 0))]
    m = re.match(r"take a turn after this one$", sl)
    if m:
        return [O.Do(lambda g, c: g.turn_queue.insert(0, c.controller), label="extra turn")]
    m = re.match(r"you can look at their facedown cards this turn$", sl)
    if m:
        return [O.Do(lambda g, c: g.peek_facedown.__setitem__(c.controller, g.turn), label="look at their facedown cards")]
    m = re.match(r"return a friendly unit and an enemy unit to their owners' hands$", sl)
    if m:
        return [O.Choose(Sel("unit", side="friendly"), out="__f"), O.Choose(Sel("unit", side="enemy"), out="__e"), O.ToHand(Ref("__f")), O.ToHand(Ref("__e"))]
    m = re.match(r"counter an enemy spell or ability that chooses a friendly (unit or gear|unit|gear)$", sl)
    if m:
        kinds = {"unit or gear": ("unit", "gear"), "unit": ("unit",), "gear": ("gear",)}[m.group(1)]

        def _item_ok(g, c, it, kinds=kinds):
            # Not So Fast: a finalized enemy chain item whose choices include a unit/gear I control (CR 355.9.a.2)
            if it.controller == c.controller or it.ctx is None or it.removed or not it.finalized:
                return False
            for x in g.current_targets(it.ctx):         # not targets that left the board and came back (359.3.e.9.a)
                o = g.objects.get(x)
                if o is not None and o.zone == "board" and o.controller == c.controller \
                        and set(kinds) & set(g.chars(x).types):
                    return True
            return False

        def _enemy_item_targeting_mine(g, c, u):
            return any(it.uid == u and _item_ok(g, c, it) for it in g.chain)
        # chosen by its card/source (a token unit's ability counts too); the countered item is the one that
        # qualifies, not just the first item that source has on the chain
        return [O.Choose(Sel("any", zone="any", pred=_enemy_item_targeting_mine), out="__sp", targeted=True),
                O.CounterItem(lambda g, c: next((it.id for it in reversed(g.chain) if it.uid == c.vars.get("__sp")
                                                 and _item_ok(g, c, it)), None))]
    m = re.match(r"swap the mights of two units at the same battlefield this turn$", sl)
    if m:
        def _swap(g, c):
            a, b = c.vars.get("__a"), c.vars.get("__b")
            if a is None or b is None or a == b:
                return
            ma, mb = g.chars(a).might or 0, g.chars(b).might or 0
            g.add_mod(a, "might", mb - ma, "turn", c.source)
            g.add_mod(b, "might", ma - mb, "turn", c.source)
        partner = lambda g, c, u: any(v != u and g.objects[v].location == g.objects[u].location
                                      for v in g.units_at(g.objects[u].location))
        second = O.Choose(Sel("unit", where="battlefield", pred=lambda g, c, u: c.vars.get("__a") is not None and u != c.vars["__a"] and g.objects[u].location == g.objects[c.vars["__a"]].location), out="__b")
        second.depends = True          # legality is checked through the first choice (it needs a partner there)
        return [O.Choose(Sel("unit", where="battlefield", pred=partner), out="__a"), second,
                O.Do(_swap, label="swap mights")]
    m = re.match(r"move me to its location and it to my original location$", sl)
    if m:
        return [O.SwapLocations(Ref("self"), Ref("t"))]
    # ---- "exhaust me [and COST] to EFFECT": optional self-cost (the "you may" wrapper makes it a choice)
    m = re.match(r"exhaust me(?: and (.+?))? to (.+)$", sl)
    if m:
        cost = parse_sentence(m.group(1), state) if m.group(1) else []
        lead, eff = _lift_choices(parse_sentence(m.group(2), state))
        return lead + [O.If(lambda g, c: c.source in g.objects and not g.objects[c.source].exhausted, [O.Exhaust(Ref("self"))] + cost + eff)]
    m = re.match(r"(discard \w+|pay (?:\[[^\]]+\])+) and exhaust me to (.+)$", sl)
    if m:
        return parse_sentence("exhaust me and " + m.group(1) + " to " + m.group(2), state)
    m = re.match(r"(kill|exhaust|banish) (an? .+?) to (.+)$", sl)
    if m and not sl.startswith(("kill a unit to", "exhaust a unit to")):
        sel, _, _, _ = parse_sel(("friendly " if "friendly" not in m.group(2) and "enemy" not in m.group(2) and "you control" not in m.group(2) else "") + m.group(2)[m.group(2).index(" ") + 1:])
        if m.group(1) == "exhaust":
            sel.ready = True
        op = {"kill": O.Kill, "exhaust": O.Exhaust, "banish": O.Banish}[m.group(1)]
        lead, eff = _lift_choices(parse_sentence(m.group(3), state))      # CR 355.10.c.1, as above
        return lead + [O.Choose(sel, out="__cost", targeted=False), O.If(O.has_var("__cost"), [op(Ref("__cost"))] + eff)]
    m = re.match(r"(.+?) and (pay (?:\[[^\]]+\])+ to .+)$", sl)
    if m:
        return parse_sentence(m.group(1), state) + parse_sentence(m.group(2), state)
    # ---- "X and Y" with two simple effects
    m = re.match(r"(draw \w+|discard \w+|gain \w+ xp|ready me|stun it|kill it|buff it|exhaust it) and (channel .+|draw \w+|discard \w+|gain \w+ xp|ready me|stun it|kill it|buff it|exhaust it|give me .+)$", sl)
    if m:
        return parse_sentence(m.group(1), state) + parse_sentence(m.group(2), state)
    m = re.match(r"each player channels (\w+) runes?( exhausted)?$", sl)
    if m:
        return [O.Channel(parse_amount(m.group(1)), exhausted=bool(m.group(2))), O.Channel(parse_amount(m.group(1)), exhausted=bool(m.group(2)), player="opponent")]
    # ---- templates
    m = re.match(r"draw (\w+)(?: cards?)?$", sl)
    if m:
        return [O.Draw(parse_amount(m.group(1)))]
    m = re.match(r"draw (\w+) for each (.+)$", sl)
    if m:
        cnt = count_phrase(m.group(2))
        k = parse_amount(m.group(1))
        return [O.Draw(lambda g, c, cnt=cnt, k=k: k * (cnt(g, c) if callable(cnt) else cnt))]
    m = re.match(r"(?:each|an) opponent draws (\w+)$", sl)
    if m:
        return [O.Draw(parse_amount(m.group(1)), player="opponent")]
    m = re.match(r"(?:its|their) controller draws (\w+)$", sl)
    if m:
        return [O.Draw(parse_amount(m.group(1)), player=O.controller_of(Ref("t")))]
    m = re.match(r"(?:each player|all players) draws? (\w+)$", sl)
    if m:
        return [O.Draw(parse_amount(m.group(1))), O.Draw(parse_amount(m.group(1)), player="opponent")]
    m = re.match(r"deal (\w+)(?: damage)? to (.+?)(?:, then (.+))?$", sl)
    if m and not m.group(2).startswith("each of up to"):
        amt = parse_amount(m.group(1))
        tgt = m.group(2)
        extra = m.group(3)
        if tgt.startswith("all ") or tgt.startswith("each "):
            sel, _, _, _ = parse_sel(tgt)
            res = [O.Deal(amt, sel)]
        else:
            ins, ref, many = choose(tgt, _next_out(state))
            res = ins + [O.Deal(amt, ref)]
        if extra:
            res += parse_sentence(extra, state)
        return res
    m = re.match(r"deal (\w+) to each of up to (\w+) units$", sl)
    if m:
        ins, ref, _ = choose(f"up to {m.group(2)} units", _next_out(state))
        return ins + [O.Deal(parse_amount(m.group(1)), ref)]
    m = re.match(r"deal (\w+)(?: damage)? split among (.+)$", sl)
    if m:
        tgt = m.group(1)
        if "at a single battlefield" in m.group(2) or "at one battlefield" in m.group(2):
            return [O.ChooseLocation(out="__bf", targeted=True),
                    O.Choose(Sel("unit", where="loc:__bf"), out="__split", n=O.split_cap(parse_amount(tgt)), up_to=True),
                    O.Split(parse_amount(tgt), Ref("__split"))]
        if m.group(2).startswith("enemy units here") or m.group(2) == "units here":
            return [O.Choose(Sel("unit", side="enemy" if "enemy" in m.group(2) else None, where="here"), out="__split", n=O.split_cap(parse_amount(tgt)), up_to=True),
                    O.Split(parse_amount(tgt), Ref("__split"))]
        raise ParseError("split target")
    m = re.match(r"kill (.+)$", sl)
    if m and not m.group(1).startswith("all ") and " to " not in m.group(1) and " and " not in m.group(1):
        ins, ref, many = choose(m.group(1), _next_out(state))
        return ins + [O.Kill(ref)]
    m = re.match(r"kill (all|each) (.+)$", sl)
    if m:
        sel, _, _, _ = parse_sel(m.group(2))
        return [O.Kill(sel)]
    m = re.match(r"buff (.+)$", sl)
    if m:
        if m.group(1).startswith("all ") or m.group(1).startswith("each ") or m.group(1).startswith("friendly units"):
            sel, _, _, _ = parse_sel(m.group(1))
            return [O.Buff(sel)]
        ins, ref, _ = choose(m.group(1), _next_out(state), targeted=True)
        return ins + [O.Buff(ref)]
    m = re.match(r"\[?stun\]? (.+)$", sl)
    if m:
        t = m.group(1)
        if t.startswith("all ") or t.startswith("each "):
            sel, _, _, _ = parse_sel(t)
            return [O.Stun(sel)]
        ins, ref, _ = choose(t, _next_out(state))
        return ins + [O.Stun(ref)]
    m = re.match(r"ready (.+)$", sl)
    if m:
        t = m.group(1)
        if t.startswith("all ") or t.startswith("each ") or t.startswith("friendly units") or t == "your units":
            sel, _, _, _ = parse_sel(t if not t.startswith("your") else "friendly units")
            return [O.Ready(sel)]
        ins, ref, _ = choose(t, _next_out(state))
        return ins + [O.Ready(ref)]
    m = re.match(r"exhaust (.+)$", sl)
    if m:
        t = m.group(1)
        if t.startswith("all ") or t.startswith("each "):
            sel, _, _, _ = parse_sel(t)
            return [O.Exhaust(sel)]
        ins, ref, _ = choose(t, _next_out(state))
        return ins + [O.Exhaust(ref)]
    m = re.match(r"banish (.+?)(?:, then (.+))?$", sl)
    if m and not m.group(1).startswith("the top"):
        ins, ref, _ = choose(m.group(1), _next_out(state))
        res = ins + [O.Banish(ref)]
        if m.group(2):
            res += parse_sentence(m.group(2), state)
        return res
    m = re.match(r"recycle (\w+)(?: cards?)?(?: from your trash)?$", sl)
    if m and _num(m.group(1)):
        return [O.Recycle(n=_num(m.group(1)), zone="trash")]
    m = re.match(r"recycle (.+)$", sl)
    if m and _num(m.group(1).split()[0]) is None:
        ins, ref, _ = choose(m.group(1), _next_out(state), targeted=False)
        return ins + [O.Recycle(ref)]
    m = re.match(r"discard (\w+)(?: cards?)?$", sl)
    if m and _num(m.group(1)):
        return [O.Discard(_num(m.group(1)))]
    m = re.match(r"(?:each|an) opponent discards (\w+)$", sl)
    if m and _num(m.group(1)):
        return [O.Discard(_num(m.group(1)), player="opponent")]
    m = re.match(r"channel (\w+) runes? exhausted$", sl)
    if m:
        return [O.Channel(parse_amount(m.group(1)), exhausted=True)]
    m = re.match(r"channel (\w+) runes?$", sl)
    if m:
        return [O.Channel(parse_amount(m.group(1)))]
    m = re.match(r"gain (\w+) xp$", sl)
    if m:
        return [O.GainXP(parse_amount(m.group(1)))]
    m = re.match(r"gain (\w+) points?$", sl)
    if m:
        return [O.GainPoints(parse_amount(m.group(1)))]
    m = re.match(r"score (\w+) points?$", sl)
    if m:
        return [O.GainPoints(parse_amount(m.group(1)))]
    m = re.match(r"(?:an|each) opponent (?:gains|scores) (\w+) points?$", sl)
    if m:
        return [O.GainPoints(parse_amount(m.group(1)), player="opponent")]
    m = re.match(r"\[?predict(?: (\d+))?\]?$", sl)
    if m:
        return [O.Predict(int(m.group(1)) if m.group(1) else 1)]
    m = re.match(r"(?:they|it|its owner) burns? (\d+)$", sl)
    if m:
        return [O.Burn(int(m.group(1)), player=Ref("__p"))]
    m = re.match(r"reveal the top (\w+) cards? of your main deck$", sl)
    if m:
        raise ParseError("reveal top cards")
    m = re.match(r"put the top (\w+) cards? of your main deck into your trash$", sl)
    if m:
        return [O.Mill(parse_amount(m.group(1)))]
    m = re.match(r"play (?:me|this) to your base, ignoring (?:my|its) cost$", sl)
    if m:
        return [O.PlayCard(Ref("self"), ignore="all", loc=lambda g, c: ("base", c.controller))]
    m = re.match(r"play (?:me|this) from your trash$", sl)
    if m:
        return [O.PlayCard(Ref("self"))]
    m = re.match(r"that player (gains|scores) (\w+) points?$", sl)
    if m:
        return [O.GainPoints(parse_amount(m.group(2)), player=Ref("__p"))]
    m = re.match(r"that player channels (\w+) runes?( exhausted)?$", sl)
    if m:
        return [O.Channel(parse_amount(m.group(1)), exhausted=bool(m.group(2)), player=Ref("__p"))]
    m = re.match(r"your non-token units cost ((?:\[[^\]]+\])+) more to play this turn$", sl)
    if m:
        from . import parse_cost
        c = parse_cost(m.group(1))
        return [O.DelayedPassive("cost_reduce", {"energy": -c["energy"], "filter": lambda g, u: g.objects[u].base_defn().is_unit and not g.objects[u].base_defn().is_token}, uses=None)]
    m = re.match(r"\[?burn (\d+)\]?$", sl)
    if m:
        return [O.Burn(int(m.group(1)))]
    m = re.match(r"heal (.+)$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.Heal(ref)]
    m = re.match(r"empower (.+)$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.Empower(ref)]
    m = re.match(r"disempower (.+)$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.Disempower(ref)]
    m = re.match(r"give (.+?) ([+\-]\d+) \[m\] this turn(?:, to a minimum of (\d+) \[m\])?$", sl)
    if m:
        tgt, amt, mn = m.group(1), int(m.group(2)), m.group(3)
        if tgt.startswith("friendly units") or tgt.startswith("enemy units") or tgt.startswith("all ") or tgt.startswith("each ") or tgt.startswith("units"):
            sel, _, _, _ = parse_sel(tgt)
            return [O.GiveMight(sel, amt, min_value=int(mn) if mn else None)]
        ins, ref, _ = choose(tgt, _next_out(state))
        return ins + [O.GiveMight(ref, amt, min_value=int(mn) if mn else None)]
    m = re.match(r"give (.+?) ([+\-])\[m\] this turn equal to (.+)$", sl)
    if m:
        amt = parse_amount(m.group(3))
        sign = 1 if m.group(2) == "+" else -1
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.GiveMight(ref, (lambda g, c, a=amt, s=sign: s * (a(g, c) if callable(a) else a)))]
    m = re.match(r"give (.+?) ((?:\[[\w\- ]+\](?: \d+)?(?:,? and |, | )?)+) this turn$", sl)
    if m:
        kws = re.findall(r"\[([\w\- ]+?)(?: (\d+))?\]", m.group(2))
        tgt = m.group(1)
        if tgt.startswith("friendly units") or tgt.startswith("all ") or tgt.startswith("each "):
            sel, _, _, _ = parse_sel(tgt)
            return [O.GiveKeyword(sel, k.lower().replace(" ", "_").replace("-", "_"), int(v) if v else True) for k, v in kws]
        ins, ref, _ = choose(tgt, _next_out(state))
        return ins + [O.GiveKeyword(ref, k.lower().replace(" ", "_").replace("-", "_"), int(v) if v else True) for k, v in kws]
    m = re.match(r"give (.+?) \[temporary\]$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.GiveKeyword(ref, "temporary", True, duration="permanent")]
    m = re.match(r"give (.+?) \[(\w+)\]( \d+)? this turn equal to its might$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.GiveKeyword(ref, m.group(2).lower(), O.might_of(ref))]
    m = re.match(r"move (.+?) (to .+|here|there)$", sl)
    if m:
        tgt, dest = m.group(1), m.group(2)
        dins, dref = _move_dest(dest)
        if tgt.startswith("all ") or tgt.startswith("each ") or tgt.startswith("any number of") or tgt.startswith("friendly units") or tgt.startswith("enemy units") or tgt.startswith("units"):
            sel, n, up_to, _ = parse_sel(tgt)
            if tgt.startswith("any number of"):
                return dins + [O.Choose(sel, out="__mv", n=6, up_to=True), O.Move(Ref("__mv"), dref)]
            return dins + [O.Move(sel, dref)]
        ins, ref, _ = choose(tgt, _next_out(state))
        return ins + [O.SetVar("__tloc", O.loc_of(ref))] + dins + [O.Move(ref, dref)]
    m = re.match(r"(?:recall|return) (.+?) to (?:its|their|your) (?:owner's |controller's )?base$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.Recall(ref)]
    m = re.match(r"return (.+?) to (?:its|their) owner's hand$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.ToHand(ref)]
    m = re.match(r"return (.+?) from your trash to your hand$", sl)
    if m:
        ins, ref, _ = choose(m.group(1) + " from your trash", _next_out(state), targeted=False)
        return ins + [O.ToHand(ref)]
    m = re.match(r"play an? (\d+) \[m\] (\w[\w ]*?) unit token(?: (.*))?$", sl)
    if m:
        tok = m.group(2).strip().title() if m.group(2).strip().lower() != "sand soldier" else "Sand Soldier"
        rest = (m.group(3) or "").strip()
        loc = "choose"          # no location in the text: base or a battlefield you control (CR 355.2.a)
        ready = False
        grant = None
        if rest.startswith("here") or rest.startswith("to this battlefield"):
            loc = "here"
            rest = re.sub(r"^(here|to this battlefield)", "", rest).strip()
        elif rest.startswith("to your base") or rest.startswith("to base") or rest.startswith("in your base"):
            loc = "base"
            rest = re.sub(r"^(to|in) (your )?base", "", rest).strip()
        if rest.startswith("ready"):
            ready = True
            rest = rest[5:].strip()
        if rest.startswith("with [deflect]"):
            grant = {"deflect": 1}
            rest = rest[len("with [deflect]"):].strip()
        if rest.startswith("to its location") or rest.startswith("there"):
            loc = Ref("__tloc")
            rest = re.sub(r"^(to its location|there)", "", rest).strip()
        if rest:
            raise ParseError(f"token qualifier {rest!r}")
        return [O.PlayToken(tok, loc=loc, ready=ready, grant=grant)]
    m = re.match(r"play (\w+) (\d+) \[m\] (\w+) unit tokens?( here| to your base)?$", sl)
    if m and _num(m.group(1)):
        loc = "here" if m.group(4) and "here" in m.group(4) else ("base" if m.group(4) else "choose")
        return [O.PlayToken(m.group(3).title(), loc=loc, count=_num(m.group(1)))]
    m = re.match(r"play a gold gear token( exhausted)?$", sl)
    if m:
        return [O.PlayToken("Gold", loc="base", exhausted=bool(m.group(1)))]
    m = re.match(r"play (\w+) gold gear tokens?( exhausted)?$", sl)
    if m and _num(m.group(1)):
        return [O.PlayToken("Gold", loc="base", count=_num(m.group(1)), exhausted=bool(m.group(2)))]
    m = re.match(r"counter (a spell|it|that spell)$", sl)
    if m:
        return [O.Choose(Sel("spell", zone="chain", pred=lambda g, c, u: any(it.uid == u and it.kind == "spell" for it in g.chain)), out="__sp", targeted=True),
                O.CounterItem(lambda g, c: next((it.id for it in g.chain if it.uid == c.vars.get("__sp")), None))]
    m = re.match(r"counter an? (unit|gear)$", sl)
    if m:
        k = m.group(1)
        return [O.Choose(Sel("card", zone="chain", pred=lambda g, c, u, k=k: any(it.uid == u and it.kind == k for it in g.chain)), out="__sp", targeted=True),
                O.CounterItem(lambda g, c: next((it.id for it in g.chain if it.uid == c.vars.get("__sp")), None))]
    m = re.match(r"look at the top (\w+) cards? of your (?:main )?deck$", sl)
    if m:
        return [O.Look(parse_amount(m.group(1)), out="looked")]
    m = re.match(r"look at the top (\w+) cards? of your (?:main )?deck, then recycle (?:any number of|some or all of) them$", sl)
    if m:
        return [O.Look(parse_amount(m.group(1)), out="looked"), O.Predict(parse_amount(m.group(1)))]
    m = re.match(r"(?:you may )?reveal an? (\w+) from among them and draw it$", sl)
    if m:
        kind = m.group(1)
        return [O.ChooseFromList(lambda g, c, k=kind: [u for u in c.vars.get("looked", []) if k in g.objects[u].defn.types], out="__pick", up_to=True),
                O.ToHand(Ref("__pick"))]
    m = re.match(r"recycle the rest$", sl)
    if m:
        return [O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"])]
    m = re.match(r"put the rest on the bottom of your (?:main )?deck(?: in any order)?$", sl)
    if m:
        return [O.Recycle(lambda g, c: [u for u in c.vars.get("looked", []) if g.objects[u].zone == "deck"])]
    m = re.match(r"draw (?:it|them)$", sl)
    if m:
        return [O.ToHand(Ref("looked"))]
    m = re.match(r"take control of (.+?)(?: this turn)?$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.TakeControl(ref, duration="turn" if sl.endswith("this turn") else "permanent")]
    m = re.match(r"attach (?:me|this) to (.+)$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.Attach(Ref("self"), ref)]
    m = re.match(r"double (.+?)'s might this turn$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.DoubleMight(ref)]
    m = re.match(r"(?:it|they) deals? damage equal to (?:its|their) might to (.+)$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.Deal(O.might_of(Ref("t")), ref, source=Ref("t"))]
    m = re.match(r"they deal damage equal to their mights to each other$", sl)
    if m:
        return [O.Deal(O.might_of(Ref("t")), Ref("t2"), source=Ref("t")), O.Deal(O.might_of(Ref("t2")), Ref("t"), source=Ref("t2"))]
    m = re.match(r"i deal damage equal to my might to (.+)$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.Deal(O.might_of(Ref("self")), ref, source=Ref("self"))]
    m = re.match(r"\[?add\]? ((?:\[[^\]]+\])+)$", sl)
    if m:
        from . import parse_cost
        c = parse_cost(m.group(1).upper().replace("[A]", "[A]"))
        return [O.Add(energy=c["energy"], power=c["power"])]
    m = re.match(r"spend (?:my|its) buff$", sl)
    if m:
        return [O.SpendBuff(Ref("self"))]
    m = re.match(r"(?:choose|you may choose) (.+)$", sl)
    if m:
        ins, ref, _ = choose(m.group(1), _next_out(state))
        return ins + [O.SetVar("__tloc", O.loc_of(ref))]
    m = re.match(r"each opponent (?:loses|lose) (\w+) points?$", sl)
    if m:
        return [O.LosePoints(parse_amount(m.group(1)), player="opponent")]
    m = re.match(r"lose (\w+) points?$", sl)
    if m:
        return [O.LosePoints(parse_amount(m.group(1)))]
    m = re.match(r"prevent the next (\d+) damage (?:that would be dealt )?to (.+?) this turn$", sl)
    if m:
        ins, ref, _ = choose(m.group(2), _next_out(state))
        return ins + [O.Prevent(ref, int(m.group(1)))]
    m = re.match(r"(?:it|they) can't be chosen by enemy spells and abilities this turn$", sl)
    if m:
        return [O.GiveKeyword(Ref("t"), "untargetable", True)]
    m = re.match(r"reveal (?:it|them)$", sl)
    if m:
        return [O.Emit("reveal", player=lambda g, c: c.controller, cards=Ref("t"))]
    raise ParseError(f"sentence {s!r}")


def parse_condition(c):
    if re.fullmatch(r"you showed off(?: a card| a gear| a unit| a spell)?", c.strip().lower()):
        return lambda g, ctx: bool(getattr(ctx, "shown_off", None))
    c = c.strip().rstrip(".").lower()
    if c in ("you do", "you did"):
        return O.has_var("__did")
    if c in ("it's your turn", "it is your turn"):
        return O.is_my_turn
    if c in ("it's not your turn", "it isn't your turn"):
        return O.not_(O.is_my_turn)
    m = re.match(r"you assigned (\d+) or more excess damage(?: to enemy units)?$", c)
    if m:
        return lambda g, cx, n=int(m.group(1)): g.turn_memo.get(("excess_damage", cx.controller), 0) >= n
    m = re.match(r"you control (\d+) or fewer runes$", c)
    if m:
        return lambda g, cx, n=int(m.group(1)): len(g.players[cx.controller].runes) <= n
    m = re.match(r"(?:it's|it is) (?:\[?empowered\]?)$", c)
    if m:
        return lambda g, cx: cx.vars.get("t") in g.objects and bool(g.objects[cx.vars["t"]].empowered)
    m = re.match(r"(?:it's|it is) an? (spell|unit|gear|equipment)$", c)
    if m:
        w = m.group(1)
        return lambda g, cx, w=w: cx.vars.get("t") in g.objects and (w in g.objects[cx.vars["t"]].base_defn().types or w.capitalize() in g.objects[cx.vars["t"]].base_defn().tags)
    m = re.match(r"you spent \[(\d+)\] or more$", c)
    if m:
        return lambda g, cx, n=int(m.group(1)): bool(cx.event) and (cx.event.get("energy") or 0) >= n
    m = re.match(r"you control (\d+) or more (\w+)$", c)
    if m:
        n = int(m.group(1))
        cnt = count_phrase(m.group(2) if m.group(2) != "runes" else "runes you control")
        return lambda g, cx, n=n, cnt=cnt: (cnt(g, cx) if callable(cnt) else cnt) >= n
    m = re.match(r"you have (\d+) or more cards in (?:your )?hand$", c)
    if m:
        return lambda g, cx, n=int(m.group(1)): len(g.players[cx.controller].hand) >= n
    m = re.match(r"you have (\w+) or fewer cards in (?:your )?hand$", c)
    if m:
        return lambda g, cx, n=_num(m.group(1)): len(g.players[cx.controller].hand) <= n
    m = re.match(r"you have (\d+) or more xp$", c)
    if m:
        return lambda g, cx, n=int(m.group(1)): g.players[cx.controller].xp >= n
    m = re.match(r"you control a facedown card$", c)
    if m:
        return lambda g, cx: any(b.facedown.get(cx.controller) for b in g.battlefields)
    m = re.match(r"you control (?:a|an) (.+)$", c)
    if m:
        sel, _, _, _ = parse_sel("friendly " + m.group(1))
        return lambda g, cx, s=sel: bool(s.candidates(g, cx))
    m = re.match(r"(?:it|they)(?:'s| is| are) (?:a |an )?(\w+) unit$", c)
    if m:
        w = m.group(1)
        if w in DOMAIN_WORDS:
            return lambda g, cx, d=w: cx.vars.get("t") in g.objects and d in g.chars(cx.vars["t"]).domains
        return lambda g, cx, t=w.capitalize(): cx.vars.get("t") in g.objects and t in g.chars(cx.vars["t"]).tags
    m = re.match(r"(?:it|they)(?:'s| is| are) (attacking|defending|exhausted|buffed|stunned|\[?mighty\]?)$", c)
    if m:
        w = m.group(1).strip("[]")
        def f(g, cx, w=w):
            u = cx.vars.get("t")
            if u not in g.objects:
                return False
            o = g.objects[u]
            return {"attacking": o.designation == "attacker", "defending": o.designation == "defender", "exhausted": o.exhausted,
                    "buffed": o.buffs > 0, "stunned": o.stunned, "mighty": g.chars(u).mighty}[w]
        return f
    m = re.match(r"(?:i am|i'm) at a battlefield$", c)
    if m:
        return lambda g, cx: cx.source in g.objects and g.objects[cx.source].location is not None and g.objects[cx.source].location[0] == "bf"
    m = re.match(r"there is an? (.+?) here$", c)
    if m:
        sel, _, _, _ = parse_sel(m.group(1) + " here")
        return lambda g, cx, s=sel: bool(s.candidates(g, cx))
    m = re.match(r"you have (\d+)\+ units (?:here|at that battlefield)$", c)
    if m:
        return lambda g, cx, n=int(m.group(1)): len(g.units_at(cx.here, cx.controller)) >= n if cx.here else False
    m = re.match(r"an opponent controls a battlefield$", c)
    if m:
        return lambda g, cx: any(b.controller is not None and b.controller != cx.controller for b in g.battlefields)
    m = re.match(r"you control another (.+)$", c)
    if m:
        sel, _, _, _ = parse_sel("another friendly " + m.group(1))
        return lambda g, cx, s=sel: bool(s.candidates(g, cx))
    m = re.match(r"this kills it$", c)
    if m:
        return lambda g, cx: cx.vars.get("t") in g.objects and g.objects[cx.vars["t"]].zone == "trash"
    m = re.match(r"you paid the additional cost$", c)
    if m:
        return O.played_cost_additional("add")
    m = re.match(r"i'?m (?:at a battlefield|in combat)$", c)
    if m:
        return lambda g, cx: cx.source in g.objects and g.objects[cx.source].location is not None and g.objects[cx.source].location[0] == "bf"
    m = re.match(r"i'?m (buffed|exhausted|empowered|\[?mighty\]?)$", c)
    if m:
        w = m.group(1).strip("[]")
        def f2(g, cx, w=w):
            o = g.objects.get(cx.source)
            if o is None:
                return False
            return {"buffed": o.buffs > 0, "exhausted": o.exhausted, "empowered": bool(o.empowered), "mighty": g.chars(cx.source).mighty}[w]
        return f2
    m = re.match(r"(?:you|an opponent) ha(?:s|ve) played another (spell|card|unit) this turn$", c)
    if m:
        return O.legion
    m = re.match(r"you control this battlefield$", c)
    if m:
        return lambda g, cx: cx.here is not None and cx.here[0] == "bf" and g.battlefields[cx.here[1]].controller == cx.controller
    raise ParseError(f"condition {c!r}")


# ---------------------------------------------------------------------------- triggers
TRIGGER_PATTERNS = [
    (r"when you play me( or this)?", "play_self"),
    (r"when you play (?:me|this) or at the start of your beginning phase", lambda g, s, ev: (ev.get("kind") == "play" and ev.get("uid") == s) or (ev.get("kind") == "beginning_phase" and ev.get("player") == g.objects[s].controller)),
    (r"when you play me or i attack", lambda g, s, ev: (ev.get("kind") == "play" and ev.get("uid") == s) or (ev.get("kind") == "attack" and ev.get("uid") == s)),
    (r"when you play a card from hidden", lambda g, s, ev: ev.get("kind") == "play" and ev.get("player") == g.objects[s].controller and ev.get("from_zone") == "facedown"),
    (r"when you play a card from anywhere other than your hand", lambda g, s, ev: ev.get("kind") == "play" and ev.get("player") == g.objects[s].controller and ev.get("from_zone") not in ("hand", None)),
    (r"when you play a card on an opponent's turn", lambda g, s, ev: ev.get("kind") == "play" and ev.get("player") == g.objects[s].controller and g.turn_player != ev["player"]),
    (r"when you play a spell on an opponent's turn", lambda g, s, ev: ev.get("kind") == "play" and ev.get("player") == g.objects[s].controller and ev.get("card_type") == "spell" and g.turn_player != ev["player"]),
    (r"when you play a unit during a showdown", lambda g, s, ev: ev.get("kind") == "play" and ev.get("player") == g.objects[s].controller and ev.get("card_type") == "unit" and g.showdown is not None),
    (r"when you play your first card each turn", lambda g, s, ev: ev.get("kind") == "play" and not ev.get("token") and ev.get("player") == g.objects[s].controller and ev.get("nth", len(g.players[ev["player"]].played_this_turn)) == 1),
    (r"when you play a card with energy cost \[(\d+)\] or more", "you_play_card"),
    (r"when you play me from face ?down on your turn", lambda g, s, ev: ev.get("kind") == "play" and ev.get("uid") == s and ev.get("from_zone") == "facedown" and g.turn_player == ev.get("player")),
    (r"when a unit you control becomes mighty", "unit_becomes_mighty"),
    (r"when a showdown begins here", "showdown_start_here"),
    (r"when you win a combat here", lambda g, s, ev: ev.get("kind") == "combat_result" and ev.get("winner") == g.objects[s].controller and ev.get("loc") == g.objects[s].place),
    (r"when i move from a location", "move_self"),
    (r"at the start of your main phase", "start_main"),
    (r"when you conquer or hold", "you_score"),
    (r"when you hold or conquer", "you_score"),
    (r"when an opponent scores", lambda g, s, ev: ev.get("kind") == "score" and ev.get("player") != g.objects[s].controller),
    (r"when you banish a card you own", lambda g, s, ev: ev.get("kind") == "banish" and ev.get("player") == g.objects[s].controller),
    (r"when you move an enemy unit", lambda g, s, ev: ev.get("kind") == "move" and ev.get("player") != g.objects[s].controller and not ev.get("standard")),
    (r"when a stunned enemy unit here dies", lambda g, s, ev: ev.get("kind") == "die" and ev.get("player") != g.objects[s].controller and ev.get("stunned") and ev.get("loc") == g.objects[s].place),
    (r"when you hide a card here", lambda g, s, ev: ev.get("kind") == "hide" and ev.get("player") == g.objects[s].controller and ev.get("loc") == g.objects[s].place),
    (r"when you kill a unit with a spell", lambda g, s, ev: ev.get("kind") == "die" and ev.get("killer") == g.objects[s].controller and ev.get("by") == "spell"),
    (r"the first time i win a combat each turn", "win_combat_self"),
    (r"when a friendly unit attacks or defends alone", lambda g, s, ev: ev.get("kind") in ("attack", "defend") and ev.get("player") == g.objects[s].controller and len(g.units_at(ev["loc"], ev["player"])) == 1),
    (r"when i attack or defend one on one", lambda g, s, ev: ev.get("kind") in ("attack", "defend") and ev.get("uid") == s and len(g.units_at(ev["loc"])) == 2),
    (r"when you draw your second card each turn", lambda g, s, ev: ev.get("kind") == "draw" and ev.get("player") == g.objects[s].controller and g.turn_memo.get(("draws", ev["player"])) == 2),
    (r"when you reduce (?:a|an) (?:enemy )?unit's might", lambda g, s, ev: False),
    (r"when you play me to a battlefield", lambda g, s, ev: ev.get("kind") == "play" and ev.get("uid") == s and ev.get("loc") is not None and ev["loc"][0] == "bf"),
    (r"when you play this from face ?down", lambda g, s, ev: ev.get("kind") == "play" and ev.get("uid") == s and ev.get("from_zone") == "facedown"),
    (r"when you play me from face ?down", lambda g, s, ev: ev.get("kind") == "play" and ev.get("uid") == s and ev.get("from_zone") == "facedown"),
    (r"when this leaves the board", "leave_self"),
    (r"when i leave the board", "leave_self"),
    (r"when you play a spell that costs \[(\d+)\] or more", "you_play_spell"),
    (r"when you play a unit that costs \[(\d+)\] or more", "you_play_unit"),
    (r"when you play a card that costs \[(\d+)\] or more", "you_play_card"),
    (r"when i become empowered", "empowered_self"),
    (r"when you buff me", lambda g, s, ev: ev.get("kind") == "buff" and ev.get("uid") == s and _by_me(g, s, ev)),
    (r"when you ready a friendly unit", lambda g, s, ev: ev.get("kind") == "ready" and ev.get("player") == g.objects[s].controller
     and ev.get("uid") in g.objects and g.objects[ev["uid"]].zone == "board" and "unit" in g.chars(ev["uid"]).types),
    (r"when you spend a buff", lambda g, s, ev: ev.get("kind") == "spend_buff" and ev.get("player") == g.objects[s].controller),
    (r"when you recycle a rune", lambda g, s, ev: ev.get("kind") == "recycle" and ev.get("player") == g.objects[s].controller and g.objects[ev["uid"]].defn.type == "rune"),
    (r"when you recycle one or more cards", "you_recycle_batch"),
    (r"when you discard one or more cards", "you_discard_batch"),
    (r"when one of your units becomes mighty", "unit_becomes_mighty"),
    (r"when one or more enemy units die", "enemy_units_die_batch"),
    (r"when one or more friendly units die", "friendly_units_die_batch"),
    (r"when a player plays a spell", "any_plays_spell"),
    (r"when an opponent plays a unit", lambda g, s, ev: ev.get("kind") == "play" and ev.get("player") != g.objects[s].controller and ev.get("card_type") == "unit"),
    (r"when you kill a stunned enemy unit", lambda g, s, ev: ev.get("kind") == "die" and ev.get("player") != g.objects[s].controller and ev.get("stunned")),
    (r"when you stun an enemy unit at a battlefield", lambda g, s, ev: ev.get("kind") == "stun" and ev.get("by") == g.objects[s].controller and ev.get("loc", (None,))[0] == "bf"),
    # "one or more": once per Stun action (its batch); "enemy": not a unit of your own
    (r"when you stun one or more enemy units", lambda g, s, ev: ev.get("kind") == "stun" and ev.get("by") == g.objects[s].controller
     and not g.is_friendly(ev.get("player"), g.objects[s].controller) and _first_in_batch(g, s, ev, "you_stun")),
    (r"when you stun one or more units", lambda g, s, ev: ev.get("kind") == "stun" and ev.get("by") == g.objects[s].controller
     and _first_in_batch(g, s, ev, "you_stun")),
    (r"when you stun an enemy unit", lambda g, s, ev: ev.get("kind") == "stun" and ev.get("by") == g.objects[s].controller
     and not g.is_friendly(ev.get("player"), g.objects[s].controller)),
    (r"when you stun (?:a|an) units?", lambda g, s, ev: ev.get("kind") == "stun" and ev.get("by") == g.objects[s].controller),
    (r"when i move from a battlefield", lambda g, s, ev: ev.get("kind") == "move" and ev.get("uid") == s and ev.get("from") is not None and ev["from"][0] == "bf"),
    (r"when a friendly unit moves from my location", lambda g, s, ev: ev.get("kind") == "leave_loc" and ev.get("player") == g.objects[s].controller and ev.get("from") == g.objects[s].place and ev.get("uid") != s),
    (r"when a unit moves from here", lambda g, s, ev: ev.get("kind") == "leave_loc" and ev.get("from") == g.objects[s].place and ev.get("uid") != s),
    (r"when another friendly unit becomes exhausted", lambda g, s, ev: ev.get("kind") == "exhaust" and ev.get("player") == g.objects[s].controller and ev.get("uid") != s),
    (r"when i conquer after an attack", lambda g, s, ev: ev.get("kind") == "conquer" and s in ev.get("units", ()) and g.combat is not None),
    (r"when i conquer an open battlefield", "conquer_self"),
    (r"when you conquer here with one or more mighty units", lambda g, s, ev: ev.get("kind") == "conquer" and ev.get("player") == g.objects[s].controller and ev.get("loc") == g.objects[s].place and any(g.chars(u).mighty for u in ev.get("units", ()))),
    (r"when you defend at a battlefield", "you_defend"),
    (r"when i'?m dealt damage", "damaged_self"),
    (r"when you choose me with a spell", lambda g, s, ev: ev.get("kind") == "target" and s in ev.get("targets", ())
     and ev.get("player") == g.objects[s].controller and ev.get("item_kind") == "spell"),
    # "you choose": only my controller's spells and abilities (an opponent choosing me doesn't trigger it)
    (r"when you choose or ready me", lambda g, s, ev: (ev.get("kind") == "target" and s in ev.get("targets", ())
     and ev.get("player") == g.objects[s].controller) or (ev.get("kind") == "ready" and ev.get("uid") == s)),
    (r"when a buffed friendly unit dies", lambda g, s, ev: ev.get("kind") == "die" and ev.get("player") == g.objects[s].controller and ev.get("buffed")),
    (r"when another non-recruit unit you control dies", lambda g, s, ev: ev.get("kind") == "die" and ev.get("player") == g.objects[s].controller and ev.get("uid") != s and "Recruit" not in g.objects[ev["uid"]].defn.tags),
    (r"when you empower something else", lambda g, s, ev: ev.get("kind") == "empower" and ev.get("player") == g.objects[s].controller and ev.get("uid") != s),
    (r"when my might becomes (\d+) or more", "mighty_self"),
    (r"when you use an activated ability of a gear", lambda g, s, ev: ev.get("kind") == "activate" and ev.get("player") == g.objects[s].controller and ev.get("gear")),
    (r"when i'?m played and when i conquer", lambda g, s, ev: (ev.get("kind") == "play" and ev.get("uid") == s) or (ev.get("kind") == "conquer" and s in ev.get("units", ()))),
    (r"when i defend or i'?m played from hidden", lambda g, s, ev: (ev.get("kind") == "defend" and ev.get("uid") == s) or (ev.get("kind") == "play" and ev.get("uid") == s and ev.get("from_zone") == "facedown")),
    (r"the first time a friendly unit dies each turn", "friendly_unit_dies"),
    (r"the first time i conquer each turn", "conquer_self"),
    (r"the first time i attack each turn", "attack_self"),
    (r"when you play your second card in a turn", lambda g, s, ev: ev.get("kind") == "play" and ev.get("player") == g.objects[s].controller and ev.get("nth", len(g.players[ev["player"]].played_this_turn)) == 2),
    (r"when you play this", "play_self"),
    (r"when i attack or defend", lambda g, s, ev: ev.get("kind") in ("attack", "defend") and ev.get("uid") == s),
    (r"when i attack", "attack_self"),
    (r"when i defend", "defend_self"),
    (r"when i hold", "hold_self"),
    (r"when i conquer", "conquer_self"),
    (r"when i conquer or hold", "score_self"),
    (r"when i hold or conquer", "score_self"),
    (r"when i score", "score_self"),
    (r"when i move to a battlefield", "move_self_to_bf"),
    (r"when i move", "move_self"),
    (r"when i die", "die_self"),
    (r"when i die in combat", "die_self_combat"),
    (r"when i win a combat", "win_combat_self"),
    (r"when i lose a combat", "lose_combat_self"),
    (r"when i become exhausted", "exhaust_self"),
    (r"when i become ready", "ready_self"),
    (r"when i become buffed", "buffed_self"),
    (r"when i become stunned", "stunned_self"),
    (r"when i become empowered", "empowered_self"),
    (r"when i become mighty", "mighty_self"),
    (r"when i'm dealt damage", "damaged_self"),
    (r"when i deal damage", "deals_damage_self"),
    (r"when you attach an equipment to me", "equipped_self"),
    (r"when you equip me", "equipped_self"),
    (r"when you hold here", "you_hold_here"),
    (r"when you conquer here", "you_conquer_here"),
    (r"when you score here", "you_score_here"),
    (r"when you hold or conquer here", "you_score_here"),
    (r"when you conquer or hold here", "you_score_here"),
    (r"when you defend here", lambda g, s, ev: ev.get("kind") == "combat_start" and ev.get("defender") == g.objects[s].controller and ev.get("loc") == g.objects[s].place),
    (r"when you attack here", lambda g, s, ev: ev.get("kind") == "combat_start" and ev.get("attacker") == g.objects[s].controller and ev.get("loc") == g.objects[s].place),
    (r"when you hold", "you_hold"),
    (r"when you conquer", "you_conquer"),
    (r"when you score", "you_score"),
    (r"when you or an ally hold", "you_hold"),
    (r"when you or an ally conquer", "you_conquer"),
    (r"when you play a spell", "you_play_spell"),
    (r"when you play another unit", "you_play_unit"),
    (r"when you play a unit here", "you_play_unit_here"),
    (r"when you play a unit", "you_play_unit"),
    (r"when you play a gear", "you_play_gear"),
    (r"when you play a unit or gear", "you_play_unit_or_gear"),
    (r"when you play a card from face ?down", lambda g, s, ev: ev.get("kind") == "play" and ev.get("player") == g.objects[s].controller and ev.get("from_zone") == "facedown"),
    (r"when you play a card", "you_play_card"),
    (r"when you play another card", "you_play_card"),
    (r"when an opponent plays a spell", "opponent_plays_spell"),
    (r"when another friendly unit dies", "another_friendly_unit_dies"),
    (r"when a friendly unit dies", "friendly_unit_dies"),
    (r"when an enemy unit dies", "enemy_unit_dies"),
    (r"when a unit dies here", "unit_dies_here"),
    (r"when an enemy unit dies here", "enemy_unit_dies_here"),
    (r"when a friendly unit dies here", "friendly_unit_dies_here"),
    (r"when a friendly unit moves", "friendly_unit_moves"),
    (r"when another friendly unit attacks", "friendly_unit_attacks"),
    (r"when you buff a unit", "you_buff"),
    (r"when you buff a friendly unit", "you_buff"),
    (r"when you discard a card", "you_discard"),
    (r"when you draw a card", "you_draw"),
    (r"when you channel a rune", "you_channel"),
    (r"when you gain xp", "you_gain_xp"),
    (r"when you win a combat", "you_win_combat"),
    (r"when you lose a combat", "you_lose_combat"),
    (r"when you hide a card", "you_hide"),
    (r"when a combat that i was in ends", "survive_combat_self"),
    (r"when you choose a friendly unit", lambda g, s, ev: ev.get("kind") == "target" and ev.get("player") == g.objects[s].controller
     and any(u in g.objects and g.objects[u].zone == "board" and g.objects[u].controller == g.objects[s].controller
             and "unit" in g.chars(u).types for u in ev.get("targets", ()))),
    (r"when an enemy unit attacks a battlefield you control", lambda g, s, ev: ev.get("kind") == "attack" and ev.get("player") != g.objects[s].controller and g.battlefields[ev["loc"][1]].controller == g.objects[s].controller),
    (r"when an enemy unit moves here", "enemy_unit_enters_here"),
    (r"when a friendly unit moves here", "friendly_unit_enters_here"),
    (r"when an enemy unit becomes stunned", "enemy_unit_stunned"),
    (r"when a friendly unit becomes stunned", "friendly_unit_stunned"),
    (r"when a friendly unit becomes mighty", "unit_becomes_mighty"),
    (r"at the start of your beginning phase", "start_beginning"),
    (r"at start of your beginning phase", "start_beginning"),
    (r"at the start of each player's first beginning phase", lambda g, s, ev: ev.get("kind") == "beginning_phase" and g.turn <= 2),
    (r"at the start of your turn", "start_beginning"),
    (r"at the end of your turn", "end_turn"),
    (r"at the end of each turn", "end_any_turn"),
    (r"at the end of the turn", "end_any_turn"),
    (r"at the start of each player's beginning phase", "start_any_turn"),
    (r"when combat starts here", "combat_start_here"),
    (r"when a showdown starts here", "showdown_start_here"),
    (r"when combat ends here", "combat_end_here"),
    (r"when you empower (?:a|an) (?:friendly )?(?:unit|gear|permanent)", "you_empower"),
    (r"when you empower me", lambda g, s, ev: ev.get("kind") == "empower" and ev.get("uid") == s and _by_me(g, s, ev)),
    (r"the first time i move each turn", "move_self"),
    (r"the first time you play a spell each turn", "you_play_spell"),
    (r"the first time you play a unit each turn", "you_play_unit"),
    (r"when i'?m chosen by an enemy spell or ability", lambda g, s, ev: ev.get("kind") == "target" and s in ev.get("targets", ())
     and ev.get("player") is not None and not g.is_friendly(ev["player"], g.objects[s].controller)),
    (r"when you reveal a card", "you_reveal"),
    (r"when i'?m discarded", "discard_self"),
    (r"when you discard me", "discard_self"),
    (r"when i'?m recycled", "recycle_self"),
    (r"when you banish me", "banish_self"),
    (r"when i'?m banished", "banish_self"),
    (r"when you show off", "you_showoff"),
    (r"when the equipped unit attacks", "equipped_unit_attacks"),
    (r"when the equipped unit dies", "equipped_unit_dies"),
    (r"when the equipped unit conquers", "equipped_unit_conquers"),
    (r"when the equipped unit holds", "equipped_unit_holds"),
    (r"when the equipped unit moves", "equipped_unit_moves"),
    (r"when the equipped unit defends", "equipped_unit_defends"),
    (r"when the equipped unit wins a combat", "equipped_unit_wins_combat"),
    (r"when the equipped unit becomes mighty", "equipped_unit_mighty"),
    (r"when the equipped unit is dealt damage", "equipped_unit_damaged"),
    (r"when the equipped unit deals damage", "equipped_unit_deals_damage"),
]

STORE_EVENT_TARGET = {"you_buff", "you_stun", "friendly_unit_dies", "another_friendly_unit_dies", "enemy_unit_dies", "any_unit_dies",
                      "unit_dies_here", "enemy_unit_dies_here", "friendly_unit_dies_here", "you_play_unit", "you_play_unit_here",
                      "you_play_gear", "you_play_unit_or_gear", "you_play_spell", "you_play_card", "friendly_unit_moves",
                      "friendly_unit_attacks", "enemy_unit_enters_here", "friendly_unit_enters_here", "enemy_unit_stunned",
                      "friendly_unit_stunned", "unit_becomes_mighty", "you_draw", "you_discard", "you_channel", "you_empower",
                      "opponent_plays_spell", "you_hide", "you_reveal"}


def match_trigger(prefix):
    p = prefix.lower().strip().rstrip(",")
    p = BRACKET_WORDS.sub(lambda m: m.group(1), p)
    p = p.replace("when this is played", "when you play this").replace("when i'm played", "when you play me")
    once = False
    if p.startswith("once each turn, "):
        once = True
        p = p[len("once each turn, "):]
    for pat, ev in sorted(TRIGGER_PATTERNS, key=lambda t: -len(t[0])):
        m = re.match(pat + r"(?:,| or when|$)", p)
        if m and m.end() >= len(p) - 1:
            if m.groups() and m.group(1) and isinstance(ev, str) and ev.startswith("you_play_"):
                n = int(m.group(1))
                base = _ev_fn(ev)
                return (lambda g, s, e, base=base, n=n: base(g, s, e) and g.objects[e["uid"]].base_defn().energy >= n), once, None
            return ev, once, None
        # "When X, if COND," handled by caller
    # generic "when you play <object phrase>"
    m = re.match(r"when you play (?:a|an|another) (.+)$", p)
    if m:
        try:
            sel, _, _, _ = parse_sel("a " + m.group(1))
            if not isinstance(sel, Ref):
                return (lambda g, s, ev, sel=sel: ev.get("kind") == "play" and ev.get("player") == g.objects[s].controller and ev.get("uid") != s and _card_matches(g, ev["uid"], sel)), once, None
        except ParseError:
            pass
    m = re.match(r"when you play me or (?:another|a|an) (.+)$", p)
    if m:
        try:
            sel, _, _, _ = parse_sel("a " + m.group(1))
            return (lambda g, s, ev, sel=sel: ev.get("kind") == "play" and ev.get("player") == g.objects[s].controller and (ev.get("uid") == s or _card_matches(g, ev["uid"], sel))), once, None
        except ParseError:
            pass
    m = re.match(r"when an opponent plays (?:a|an) (.+)$", p)
    if m:
        try:
            sel, _, _, _ = parse_sel("a " + m.group(1))
            return (lambda g, s, ev, sel=sel: ev.get("kind") == "play" and ev.get("player") != g.objects[s].controller and _card_matches(g, ev["uid"], sel)), once, None
        except ParseError:
            pass
    m = re.match(r"when a player plays (?:a|an) (.+?)( here)?$", p)
    if m:
        try:
            sel, _, _, _ = parse_sel("a " + m.group(1))
            here = bool(m.group(2))
            return (lambda g, s, ev, sel=sel, here=here: ev.get("kind") == "play" and _card_matches(g, ev["uid"], sel) and (not here or ev.get("loc") == g.objects[s].place)), once, None
        except ParseError:
            pass
    # compound: "when you play me or when i hold"
    m = re.match(r"(.+?) or (when .+)$", p)
    if m:
        a = match_trigger(m.group(1))
        b = match_trigger(m.group(2))
        if a and b:
            fa, fb = _ev_fn(a[0]), _ev_fn(b[0])
            return (lambda g, s, ev, fa=fa, fb=fb: fa(g, s, ev) or fb(g, s, ev)), once or a[1] or b[1], None
    return None


def _card_matches(g, uid, sel):
    """Does a card (in any zone) match a Sel's printed characteristics?"""
    if uid not in g.objects:
        return False
    d = g.objects[uid].base_defn()
    k = sel.kind
    if k == "unit" and not d.is_unit: return False
    if k == "gear" and not d.is_gear: return False
    if k == "spell" and d.type != "spell": return False
    if k == "permanent" and not d.is_permanent: return False
    if sel.tags and not any(t in d.tags for t in sel.tags): return False
    if sel.token is not None and d.is_token != sel.token: return False
    if sel.mighty is not None and ((d.might or 0) >= 5) != sel.mighty: return False
    if sel.supertype and d.supertype != sel.supertype: return False
    if sel.min_might is not None and (d.might or 0) < sel.min_might: return False
    if sel.max_might is not None and (d.might or 0) > sel.max_might: return False
    if sel.keyword and not d.keywords.get(sel.keyword): return False
    return True


def _ev_fn(ev):
    from ..abilities import TRIGGERS
    return TRIGGERS[ev] if isinstance(ev, str) else ev


# ---------------------------------------------------------------------------- static abilities
def _exile_loc(ev):
    # "Units you PLAY TO battlefields you control": the location the unit was played to. Baron Nashor's "I enter
    # there" moves the entry to the Baron Pit, but its controller orders the two replacements (CR 372.1), so a unit
    # played to a battlefield they control still enters ready.
    return ev.get("play_loc") or ev.get("loc")


def parse_static(line):
    bl = line.strip().lower().rstrip(".")
    if bl == "units can't be played here":
        return [Static("self", "rule", ("cant_play_here",), source_text=line)]
    if bl == "units you play to battlefields you control enter ready":
        return [Replacement("enter_ready", lambda g, s, ev: ev.get("player") == g.objects[s].controller and _exile_loc(ev) is not None and _exile_loc(ev)[0] == "bf" and g.battlefields[_exile_loc(ev)[1]].controller == ev["player"],
                            lambda g, s, ev: dict(ev, ready=True), label=line)]
    if bl == "spells and abilities affecting units here each deal 1 bonus damage":
        return [Static("self", "rule", ("bonus_damage_here", 1), source_text=line)]
    """Returns list of Static abilities or raises."""
    l = line.lower().rstrip(".")
    cond = None
    m = re.match(r"while (.+?), (.+)$", l)
    if m:
        cond = parse_static_condition(m.group(1))
        l = m.group(2)
    m = re.match(r"(.+?) while (.+)$", l)
    if m and cond is None:
        try:
            cond = parse_static_condition(m.group(2))
            l = m.group(1)
        except ParseError:
            pass
    l = re.sub(r"^i get ", "i have ", l)
    l = re.sub(r"^(other friendly units|friendly units|enemy units) have ([+\-]\d+ \[m\]) here$", r"\1 here have \2", l)
    m = re.match(r"i have ([+\-]\d+) \[m\]$", l)
    if m:
        return [Static("self", "might", int(m.group(1)), cond=cond, source_text=line)]
    m = re.match(r"i have ([+\-]\d+) \[m\] and \[(\w+)\]$", l)
    if m:
        return [Static("self", "might", int(m.group(1)), cond=cond, source_text=line), Static("self", "keyword", (m.group(2).lower(), True), cond=cond, source_text=line)]
    m = re.match(r"(your|other|your other) (units|tokens) enter ready$", l)
    if m:
        tok = m.group(2) == "tokens"
        return [Replacement("enter_ready", lambda g, s_, ev, tok=tok: ev.get("uid") != s_ and ev.get("player") == g.objects[s_].controller and (not tok or g.objects[ev["uid"]].base_defn().is_token),
                            lambda g, s_, ev: dict(ev, ready=True), label=line)]
    m = re.match(r"i have an additional ([+\-]\d+) \[m\]$", l)
    if m:
        return [Static("self", "might", int(m.group(1)), cond=cond, source_text=line)]
    m = re.match(r"i am an? (\w+)$", l)
    if m:
        return [Static("self", "tag", m.group(1).capitalize(), cond=cond, source_text=line)]
    if l in ("ganking", "hidden", "tank", "deflect", "vision"):
        return []
    m = re.match(r"my might is increased by (?:the number of )?(.+)$", l)
    if m:
        cnt = count_phrase(m.group(1))
        return [Static("self", "might", lambda g, src, u, cnt=cnt: _cnt(g, src, cnt), cond=cond, source_text=line)]
    m = re.match(r"i have \[(\w+)\] equal to the number of (.+)$", l)
    if m:
        cnt = count_phrase(m.group(2))
        kwn = m.group(1).lower()
        return [Static("self", "keyword", lambda g, src, u, cnt=cnt, kwn=kwn: (kwn, _cnt(g, src, cnt)), cond=cond, source_text=line)]
    m = re.match(r"(stunned enemy units here) have (-\d+) \[m\], to a minimum of (\d+) \[m\]$", l)
    if m:
        sel, _, _, _ = parse_sel(m.group(1))
        n, mn = int(m.group(2)), int(m.group(3))
        return [Static(sel, "might", lambda g, src, u, n=n, mn=mn: max(n, mn - (g.chars(u).defn.might or 0)), cond=cond, source_text=line)]
    m = re.match(r"your (\w+)s' energy costs are reduced by \[(\d+)\](?:, to a minimum of \[(\d+)\])?$", l)
    if m:
        tag, n, mn = m.group(1).capitalize(), int(m.group(2)), int(m.group(3) or 0)
        return [Static("self", "rule", ("cost_reduce", lambda g, src, uid, e, p, n=n, mn=mn, tag=tag: (max(mn, e - n), p) if tag in g.objects[uid].base_defn().tags and g.objects[uid].owner == g.objects[src].controller else (e, p)), cond=cond, source_text=line)]
    m = re.match(r"friendly units may be played to open battlefields$", l)
    if m:
        return [Static("self", "rule", ("play_open_bf",), cond=cond, source_text=line)]
    m = re.match(r"units can't move (from here )?to base$", l)
    if m:
        # Vilemaw's Lair: only units at that battlefield; Minotaur Reckoner: "Units can't move to base." - every unit
        return [Static("self", "rule", ("cant_move_to_base", "here" if m.group(1) else "all"), cond=cond, source_text=line)]
    m = re.match(r"i have ([+\-]\d+) \[m\] for each (.+?)(?: at my battlefield| here)?$", l)
    if m:
        cnt = count_phrase(m.group(2))
        k = int(m.group(1))
        return [Static("self", "might", lambda g, src, u, cnt=cnt, k=k: k * _cnt(g, src, cnt), cond=cond, source_text=line)]
    m = re.match(r"i have ((?:\[[\w\- ]+\](?: \d+)?(?:,? and |, | )?)+)$", l)
    if m:
        kws = re.findall(r"\[([\w\- ]+?)(?: (\d+))?\]", m.group(1))
        return [Static("self", "keyword", (k.lower().replace(" ", "_").replace("-", "_"), int(v) if v else True), cond=cond, source_text=line) for k, v in kws]
    m = re.match(r"(.+?) have ([+\-]\d+) \[m\]$", l)
    if m:
        sel, _, _, _ = parse_sel(m.group(1).replace("other friendly", "other friendly"))
        if isinstance(sel, Ref):
            raise ParseError(line)
        return [Static(sel, "might", int(m.group(2)), cond=cond, source_text=line)]
    m = re.match(r"(.+?) have ((?:\[[\w\- ]+\](?: \d+)?(?:,? and |, | )?)+)$", l)
    if m:
        sel, _, _, _ = parse_sel(m.group(1))
        if isinstance(sel, Ref):
            raise ParseError(line)
        kws = re.findall(r"\[([\w\- ]+?)(?: (\d+))?\]", m.group(2))
        return [Static(sel, "keyword", (k.lower().replace(" ", "_").replace("-", "_"), int(v) if v else True), cond=cond, source_text=line) for k, v in kws]
    m = re.match(r"i can't be chosen by enemy spells and abilities$", l)
    if m:
        return [Static("self", "keyword", ("untargetable", True), cond=cond, source_text=line)]
    m = re.match(r"i can't be chosen by enemy spells and abilities unless i'm in combat$", l)
    if m:
        def not_in_combat(g, src, cond=cond):
            o = g.objects[src]
            fighting = g.combat is not None and o.location == ("bf", g.combat["bf"])
            return not fighting and (cond is None or cond(g, src))
        return [Static("self", "keyword", ("untargetable", True), cond=not_in_combat, source_text=line)]
    m = re.match(r"i can have any number of buffs$", l)
    if m:
        return [Static("self", "rule", ("many_buffs",), cond=cond, source_text=line)]
    m = re.match(r"i can't (?:be )?move(?:d)?$", l)
    if m:
        return [Static("self", "rule", ("cant_move",), cond=cond, source_text=line)]
    m = re.match(r"i don't deal combat damage$", l)
    if m:
        return [Static("self", "rule", ("no_combat_damage",), cond=cond, source_text=line)]
    m = re.match(r"units can move here from anywhere$", l)
    if m:
        return [Static("self", "rule", ("move_here_from_anywhere",), cond=cond, source_text=line)]
    m = re.match(r"(?:your |friendly )?units cost \[(\d+)\] less$", l)
    if m:
        n = int(m.group(1))
        return [Static("self", "rule", ("cost_reduce", lambda g, src, uid, e, p, n=n: (max(0, e - n), p) if g.objects[uid].base_defn().is_unit and g.objects[uid].owner == g.objects[src].controller else (e, p)), cond=cond, source_text=line)]
    m = re.match(r"(?:your |friendly )?spells cost \[(\d+)\] less$", l)
    if m:
        n = int(m.group(1))
        return [Static("self", "rule", ("cost_reduce", lambda g, src, uid, e, p, n=n: (max(0, e - n), p) if g.objects[uid].base_defn().type == "spell" and g.objects[uid].owner == g.objects[src].controller else (e, p)), cond=cond, source_text=line)]
    raise ParseError(f"static {line!r}")


def _cnt(g, src, cnt):
    from ..vm import Context
    o = g.objects[src]
    c = Context(o.controller, src, here=o.location)
    return cnt(g, c) if callable(cnt) else cnt


def parse_static_condition(c):
    c = c.strip().lower()
    if c in ("i'm at a battlefield", "i am at a battlefield", "i'm in combat"):
        return lambda g, src: g.objects[src].place is not None and g.objects[src].place[0] == "bf"
    if c in ("i'm in your base", "i'm in base", "i'm at your base"):
        return lambda g, src: g.objects[src].place is not None and g.objects[src].place[0] == "base"
    if c in ("i'm buffed",):
        return lambda g, src: g.objects[src].buffs > 0
    if c in ("i'm exhausted",):
        return lambda g, src: g.objects[src].exhausted
    if c in ("i'm ready",):
        return lambda g, src: not g.objects[src].exhausted
    if c in ("i'm empowered", "this is empowered"):
        return lambda g, src: bool(g.objects[src].empowered)
    if c in ("i'm mighty", "i'm [mighty]"):
        return lambda g, src: g.chars(src).mighty
    if c in ("i'm an attacker", "i'm attacking"):
        return lambda g, src: g.objects[src].designation == "attacker"
    if c in ("i'm a defender", "i'm defending"):
        return lambda g, src: g.objects[src].designation == "defender"
    if c in ("i'm in a showdown", "i'm in a showdown or combat"):
        return lambda g, src: g.showdown is not None and g.objects[src].place == ("bf", g.showdown["bf"])
    if c in ("it's your turn",):
        return lambda g, src: g.turn_player == g.objects[src].controller
    if c in ("it's not your turn", "it isn't your turn"):
        return lambda g, src: g.turn_player != g.objects[src].controller
    if c in ("you control this battlefield", "you or an ally control this battlefield"):
        return lambda g, src: g.objects[src].place is not None and g.objects[src].place[0] == "bf" and g.battlefields[g.objects[src].place[1]].controller == g.objects[src].controller
    m = re.match(r"you control (\d+) or more (\w+)$", c)
    if m:
        n = int(m.group(1))
        cnt = count_phrase(m.group(2) if m.group(2) != "runes" else "runes you control")
        return lambda g, src, n=n, cnt=cnt: _cnt(g, src, cnt) >= n
    m = re.match(r"you have (\d+) or more xp$", c)
    if m:
        return lambda g, src, n=int(m.group(1)): g.players[g.objects[src].controller].xp >= n
    m = re.match(r"you control (?:a|an|another) (.+)$", c)
    if m:
        sel, _, _, _ = parse_sel("friendly " + m.group(1))
        from ..vm import Context
        return lambda g, src, s=sel: bool(s.candidates(g, Context(g.objects[src].controller, src, here=g.objects[src].place)))
    m = re.match(r"you have (\w+) or fewer cards in (?:your )?hand$", c)
    if m:
        return lambda g, src, n=_num(m.group(1)): len(g.players[g.objects[src].controller].hand) <= n
    m = re.match(r"you have (\d+) or more cards in (?:your )?hand$", c)
    if m:
        return lambda g, src, n=int(m.group(1)): len(g.players[g.objects[src].controller].hand) >= n
    m = re.match(r"(?:there is|there's) (?:a|an) (.+?) here$", c)
    if m:
        sel, _, _, _ = parse_sel(m.group(1) + " here")
        from ..vm import Context
        return lambda g, src, s=sel: bool(s.candidates(g, Context(g.objects[src].controller, src, here=g.objects[src].place)))
    raise ParseError(f"static condition {c!r}")


# ---------------------------------------------------------------------------- costs
def parse_cost_phrase(text, defn):
    """'Discard 1, [1][Fury], [T]' -> cost dict. Raises on unknown non-resource costs."""
    from . import parse_cost
    cost = {"energy": 0, "power": []}
    parts = [p.strip() for p in re.split(r",\s*", text) if p.strip()]
    for p in parts:
        pl = p.lower()
        if re.fullmatch(r"(\[[^\]]+\]\s*)+", p):
            c = parse_cost(p)
            cost["energy"] += c["energy"]
            cost["power"] += c["power"]
            if c.get("exhaust"):
                cost["exhaust"] = True
            continue
        m = re.match(r"discard (\w+)(?: cards?)?$", pl)
        if m and _num(m.group(1)):
            cost["discard"] = _num(m.group(1))
            continue
        if pl in ("discard a card", "discard a gear", "discard a unit", "discard a spell"):
            cost["discard"] = 1
            if pl != "discard a card":
                cost["discard_type"] = pl.split()[-1]
            continue
        if pl in ("kill me", "kill this"):
            cost["kill_self"] = True
            continue
        if pl in ("banish me", "banish this"):
            cost["banish_self"] = True
            continue
        if pl in ("spend my buff", "spend a buff"):
            cost["spend_buff"] = True
            continue
        if pl in ("disempower me", "disempower this"):
            cost["disempower_self"] = True
            cost["custom"] = [O.Disempower(Ref("self"))]
            cost["ready_only"] = False
            continue
        m = re.match(r"kill (a|an|another) (.+)$", pl)
        if m:
            sel, _, _, _ = parse_sel("friendly " + m.group(2) if "friendly" not in m.group(2) and "enemy" not in m.group(2) else m.group(2))
            cost["sacrifice"] = sel
            continue
        m = re.match(r"exhaust (a|an|another) (.+)$", pl)
        if m:
            sel, _, _, _ = parse_sel(("friendly " if "friendly" not in m.group(2) else "") + m.group(2))
            sel.ready = True
            cost["custom"] = [O.Choose(sel, out="__ex", targeted=False), O.Exhaust(Ref("__ex"))]
            continue
        m = re.match(r"recycle (\w+)(?: cards?)? from your trash$", pl)
        if m and _num(m.group(1)):
            cost["recycle"] = _num(m.group(1))
            continue
        m = re.match(r"banish (a|an) (.+?) from your trash$", pl)
        if m:
            sel, _, _, _ = parse_sel(m.group(2) + " from your trash")
            cost["custom"] = [O.Choose(sel, out="__bn", targeted=False), O.Banish(Ref("__bn"))]
            continue
        m = re.match(r"spend (\d+) xp$", pl)
        if m:
            cost["xp"] = int(m.group(1))
            continue
        raise ParseError(f"cost {p!r}")
    return cost


# ---------------------------------------------------------------------------- lines
LEAD_KW = re.compile(r"^\s*\[(Reaction|Action|Legion|Empowered|Level \d+|Deathknell|Mighty|Hidden|Accelerate|Deflect(?: \d+)?|Tank|Ganking|Ambush|Deploy|Temporary|Vision|Hunt(?: \d+)?|Disarm(?: \d+)?|Assault(?: \d+)?|Shield(?: \d+)?|Backline|Weaponmaster|Quick-Draw|Unique|Equip|Empower|Flow|Repeat)\]\s*(?:\[>\])?\s*(?:[-—]\s*)?((?:\[(?:\d+|[ACT]|Fury|Calm|Mind|Body|Chaos|Order)\]\s*)*)(?:[-—]\s*)?,?\s*")
SHOWOFF = re.compile(r"^\s*\[Show Off\]\s*[^.]*\.?\s*")


def split_lead_keywords(line):
    flags = []
    while True:
        m = LEAD_KW.match(line) or SHOWOFF.match(line)
        if not m:
            break
        flags.append((m.group(1) if m.re is LEAD_KW else "show off").lower())
        rest = line[m.end():]
        if m.re is LEAD_KW and m.group(2) and rest.lstrip().startswith(":"):
            rest = m.group(2) + rest.lstrip()      # "[Reaction][>] [T]: ..." -- the cost belongs to an activated ability
            line = rest
            break
        line = rest
    line = line.strip()
    if line.lower() in ("[no text]", "", "."):
        line = ""
    return flags, line


def _flag_cond(flags):
    """Condition from lead keyword flags ([Legion], [Empowered], [Level N]), or None."""
    kwflags = set(f.split(" ")[0] for f in flags)
    cond = None
    if "legion" in kwflags:
        cond = lambda g, src: g.legion_active(g.objects[src].controller, src)
    if "empowered" in kwflags:
        cond = lambda g, src: bool(g.objects[src].empowered)
    lvl = [f for f in flags if f.startswith("level ")]
    if lvl:
        n = int(lvl[0].split(" ")[1])
        cond = lambda g, src, n=n: g.players[g.objects[src].controller].xp >= n
    return cond


def script_line(defn, line):
    """Parse one line of rules text into abilities. Returns list of abilities.

    Every ability parsed from a line led by [Legion] / [Empowered] / [Level N] carries that
    condition, even where a parser branch forgot to pass it on (Bandle Soldier, Scorchclaw)."""
    flags, body = split_lead_keywords(line)
    fc = _flag_cond(flags) if body else None
    abilities = _script_line(defn, line, fc)
    if fc is not None:
        for ab in abilities:
            inner = getattr(ab, "cond", "missing")
            if inner == "missing":
                continue
            if inner is None:
                ab.cond = fc
            elif inner is not fc:
                ab.cond = lambda g, src, a=inner, b=fc: b(g, src) and a(g, src)
    return abilities


def _script_line(defn, line, cond=None):
    flags, body = split_lead_keywords(line)
    kwflags = set(f.split(" ")[0] for f in flags)
    if not body:
        return []        # pure keyword line
    timing = "reaction" if "reaction" in kwflags else ("action" if "action" in kwflags else "main")
    bl = body.lower()
    # deathknell
    if "deathknell" in kwflags:
        eff = parse_effect(body)
        return [Triggered("die_self", eff, label="Deathknell", source_text=line, cond=cond, keyword="deathknell")]
    # activated: COST: EFFECT   (cost part contains a resource token or a known cost phrase and no sentence end)
    m = re.match(r"^([^:.]{1,80}?)\s*:\s*(.+)$", body)
    cost = None
    if m and not re.match(r"(when|at the|while|if |the |once each turn, when)", bl):
        try:
            cost = parse_cost_phrase(m.group(1), defn)
        except ParseError:
            cost = None
    if cost is not None:
        eff_text = m.group(2)
        eflags, eff_text = split_lead_keywords(eff_text)
        if "reaction" in eflags:
            timing = "reaction"
        elif "action" in eflags:
            timing = "action"
        # "[T]: [Reaction], [Legion] — ..." (Darius, Sun Disc): usable only while Legion is active
        legion_use = "legion" in {f.split(" ")[0] for f in eflags}
        once = False
        is_add = False
        restriction_text = None
        rm = re.search(r"\s*(?:use|activate) (?:this ability )?only (if|while|when|once each turn)(.*)$", eff_text, re.I)
        if rm:
            restriction_text = rm.group(0).strip()
            eff_text = eff_text[:rm.start()].strip()
            if "once each turn" in restriction_text.lower():
                once = True
        if re.match(r"once each turn[,:]?\s*", eff_text, re.I):
            once = True
            eff_text = re.sub(r"^once each turn[,:]?\s*", "", eff_text, flags=re.I)
        em = re.match(r"\[?Add\]?\s*((?:\[[^\]]+\])+)\.?(.*)$", eff_text)
        restriction = None
        if em:
            from . import parse_cost
            c = parse_cost(em.group(1))
            rest = em.group(2).strip().lower()
            restr = None
            if rest:
                rm = re.match(r"(?:use|spend)(?: (?:this|it|this energy|this power))? only (?:to play |during |to |on )?(.+?)\.?$", rest)
                if rm:
                    restr = rm.group(1)
                else:
                    raise ParseError(f"add restriction {rest!r}")
            eff = [O.Add(energy=c["energy"], power=c["power"], restriction=restr)]
            is_add = True
        else:
            eff = parse_effect(eff_text)
        restriction = None
        if restriction_text and not is_add:
            rt = re.sub(r"^(?:use|activate) (?:this ability )?only (?:if|while|when) ", "", restriction_text.lower().rstrip("."))
            if "once each turn" not in rt:
                try:
                    cnd = parse_condition(rt)
                    restriction = lambda g, src, cnd=cnd: _cond_from_src(g, src, cnd)
                except ParseError:
                    try:
                        sc = parse_static_condition(rt)
                        restriction = sc
                    except ParseError:
                        raise ParseError(f"restriction {rt!r}")
        if legion_use:
            inner = restriction
            restriction = lambda g, src, inner=inner: g.legion_active(g.objects[src].controller, src) and (inner is None or inner(g, src))
        return [Activated(cost, eff, timing=timing, once_per_turn=once, is_add=is_add, label=line[:40], source_text=line, cond=cond, restriction=restriction)]
    # triggered: "When ..., effect"
    m = re.match(r"^((?:Once each turn, )?(?:When|Whenever|At (?:the )?start|At (?:the )?end|The first time)[^,]*(?:,[^,]*?(?= if ))?),\s*(.+)$", body)
    if m:
        prefix, rest = m.group(1), m.group(2)
        tr = match_trigger(prefix)
        if tr is None:
            # maybe "When X, if COND, effect"
            raise ParseError(f"trigger {prefix!r}")
        ev, once, _ = tr
        filt = None
        cm = re.match(r"if (.+?), (.+)$", rest, re.I)
        if cm:
            c2 = parse_condition(cm.group(1))
            rest = cm.group(2)
            filt = lambda g, s, e, c2=c2: _cond_from_src(g, s, c2, e)
        optional = rest.lower().startswith("you may ")
        store = {}
        if isinstance(ev, str) and ev in STORE_EVENT_TARGET:
            store = {"uid": "t"}
        state = {"tcount": 1 if store else 0}
        store["player"] = "__p"           # "that player" / "they": the player the event is about (Obelisk of Power)
        if re.search(r"\bmoves? from\b", prefix, re.I):
            store["from"] = "__tloc"      # "When I move from a location, ... there" (Lillia, Fae Fawn)
        if re.search(r"\bthat battlefield\b", rest, re.I) and not re.search(r"\bchoose a battlefield\b", rest, re.I):
            # "When I move to a battlefield / you stun a unit at a battlefield / you play a Deploy gear, ... that
            # battlefield" (Irresistible Faefolk, Vex, Mocking, Exemplar of Demacia): the event's location
            store["loc"] = "__bl"
        eff = parse_effect(rest, state)
        once_flag = once or prefix.lower().startswith("the first time")
        if re.match(r"the first time a friendly unit dies each turn", prefix, re.I):
            # CR 383.1: "the first time" counts every friendly death this turn, including ones before this object was
            # on the board (Wraith of Echoes played after a unit died doesn't trigger on the next death); deaths at the
            # same time are one instance (383.1.b), so the trigger needs the turn's first batch of friendly deaths.
            def filt(g, s, ev, inner=filt):
                if g.turn_memo.get(("first_unit_die_batch", g.objects[s].controller)) != ev.get("batch"):
                    return False
                return inner is None or inner(g, s, ev)
        return [Triggered(ev, eff, filt=filt, once_per_turn=once_flag, label=line[:40], source_text=line, store=store, cond=cond, optional=optional)]
    # play permissions
    if bl in ("you may play me to an open battlefield.", "you may play me to an open battlefield"):
        return [PlayPermission("open_bf", label=line)]            # CR 170.11.c: unoccupied and uncontrolled
    if bl in ("i enter ready.", "i enter ready"):
        return [Replacement("enter_ready", lambda g, s, ev: ev.get("uid") == s, lambda g, s, ev: dict(ev, ready=True), label=line, zone="any")]
    if bl in ("this enters exhausted.", "this enters exhausted"):
        return [Replacement("enter_ready", lambda g, s, ev: ev.get("uid") == s, lambda g, s, ev: dict(ev, ready=False), label=line, zone="any")]
    # play permissions, cost modifiers, additional costs, enter-ready replacements
    m = re.match(r"i can be played to a battlefield you'?re attacking\.?$", bl)
    if m:
        return [PlayPermission("attacking_bf", label=line)]       # only the battlefield of a combat you're attacking in
    m = re.match(r"you may play me to an occupied enemy battlefield\.?$", bl)
    if m:
        return [PlayPermission("occupied_enemy_bf", label=line)]  # CR 170.11.a: enemy-controlled with a unit there
    m = re.match(r"i cost \[(\d+)\] less\.?$", bl)
    if m:
        n = int(m.group(1))
        return [PlayPermission("cost", cost_mod=lambda g, u, e, p, n=n: (max(0, e - n), p), cond=cond, label=line)]
    m = re.match(r"(?:i cost|this costs) \[(\d+)\] less for each (.+?)\.?$", bl)
    if m:
        n = int(m.group(1))
        cnt = count_phrase(m.group(2))
        return [PlayPermission("cost", cost_mod=lambda g, u, e, p, n=n, cnt=cnt: (max(0, e - n * _cnt(g, u, cnt)), p), label=line)]
    m = re.match(r"(?:i cost|this costs) \[(\d+)\] less if (.+?)\.?$", bl)
    if m:
        n = int(m.group(1))
        cnd = parse_condition(m.group(2))
        return [PlayPermission("cost", cost_mod=lambda g, u, e, p, n=n, cnd=cnd: (max(0, e - n), p) if _cond_from_src(g, u, cnd) else (e, p), label=line)]
    m = re.match(r"i enter ready if (.+?)\.?$", bl)
    if m:
        cnd = parse_condition(m.group(1))
        return [Replacement("enter_ready", lambda g, s, ev, cnd=cnd: ev.get("uid") == s and _cond_from_src(g, s, cnd), lambda g, s, ev: dict(ev, ready=True), label=line, zone="any")]
    m = re.match(r"if (.+?), i enter ready\.?$", bl)
    if m:
        cnd = parse_condition(m.group(1))
        return [Replacement("enter_ready", lambda g, s, ev, cnd=cnd: ev.get("uid") == s and _cond_from_src(g, s, cnd), lambda g, s, ev: dict(ev, ready=True), label=line, zone="any")]
    m = re.match(r"other friendly units enter ready\.?$", bl)
    if m:
        return [Replacement("enter_ready", lambda g, s, ev: ev.get("uid") != s and ev.get("player") == g.objects[s].controller, lambda g, s, ev: dict(ev, ready=True), label=line)]
    m = re.match(r"as an additional cost to play (?:me|this), (.+?)\.?$", bl)
    if m:
        ins = parse_sentence(m.group(1), {"tcount": 0})
        req = next((i.sel for i in ins if isinstance(i, O.Choose)), None)
        return [PlayPermission("additional_cost", value=(req, ins, True), label=line)]
    m = re.match(r"(?:as you play (?:me|this), )?you may (.+?) as an additional cost(?: to play (?:me|this))?\.(?: if you do, (.+?)\.?)?$", bl)
    if m:
        ins = parse_sentence(m.group(1), {"tcount": 0})
        extra = m.group(2)
        if extra and re.match(r"(?:i cost|reduce my cost by) \[(\d+)\]", extra):
            n = int(re.match(r"(?:i cost|reduce my cost by) \[(\d+)\]", extra).group(1))
            return [PlayPermission("additional_cost", value=(None, ins, False), label=line),
                    PlayPermission("cost", cost_mod=lambda g, u, e, p, n=n: (max(0, e - n), p) if g.objects[u].temp.get("add_paid") else (e, p), label=line)]
        after = parse_sentence(extra, {"tcount": 0}) if extra else []
        return [PlayPermission("additional_cost", value=(None, ins, False), label=line)] + \
               ([Triggered("play_self", after, filt=lambda g, s, ev: g.objects[s].temp.get("add_paid") or bool((ev.get("paid") or {}).get("add")), label=line[:40], source_text=line)] if after else [])
    m = re.match(r"(?:your )?spells and abilities deal (\d+) bonus damage\.?$", bl)
    if m:
        return [Static("self", "rule", ("bonus_damage", int(m.group(1))), label=line, source_text=line)]
    m = re.match(r"i can't be readied\.?$", bl)
    if m:
        return [Static("self", "rule", ("cant_ready",), label=line, source_text=line)]
    m = re.match(r"i must be assigned combat damage last\.?$", bl)
    if m:
        return [Static("self", "keyword", ("backline", True), label=line, source_text=line)]
    m = re.match(r"i must be assigned combat damage first\.?$", bl)
    if m:
        return [Static("self", "keyword", ("tank", True), label=line, source_text=line)]
    m = re.match(r"while i'?m at a battlefield, the energy costs? for spells you play (?:is|are) reduced by \[(\d+)\](?:, to a minimum of \[(\d+)\])?\.?$", bl)
    if m:
        n, mn = int(m.group(1)), int(m.group(2) or 0)
        return [Static("self", "rule", ("cost_reduce", lambda g, src, uid, e, p, n=n, mn=mn: (max(mn, e - n), p) if g.objects[uid].base_defn().type == "spell" and g.objects[uid].owner == g.objects[src].controller else (e, p)),
                       cond=lambda g, src: g.objects[src].place is not None and g.objects[src].place[0] == "bf", label=line, source_text=line)]
    m = re.match(r"my might is increased by your points\.?$", bl)
    if m:
        return [Static("self", "might", lambda g, src, u: g.players[g.objects[src].controller].points, label=line, source_text=line)]
    m = re.match(r"i have ([+\-]\d+) \[m\] and enter ready\.?$", bl)
    if m:
        return [Static("self", "might", int(m.group(1)), label=line, source_text=line),
                Replacement("enter_ready", lambda g, s, ev: ev.get("uid") == s, lambda g, s, ev: dict(ev, ready=True), label=line, zone="any")]
    # static
    stat = parse_static(body)
    if cond is not None:
        for s in stat:
            s.cond = (lambda a, b: (lambda g, src: a(g, src) and (b is None or b(g, src))))(cond, s.cond)
    return stat


def _cond_from_src(g, s, c2, ev=None):
    from ..vm import Context
    o = g.objects[s]
    ctx = Context(o.controller, s, here=o.location)
    ctx.shown_off = g.shown_off.get(s)
    if ev is not None:
        ctx.event = ev
        ctx.vars["ev"] = ev
        if ev.get("kind") == "play" and ev.get("uid") == s:
            ctx.paid = dict(ev.get("paid") or {})      # "When you play me, if you paid the additional cost"
    return bool(c2(g, ctx))


def script_card(defn):
    """Returns (abilities, effect_abilities, complete)."""
    abilities, effect_abilities = [], []
    complete = True
    errors = []
    text = clean_text(defn.text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if defn.type == "spell":
        # the whole text is the spell effect, possibly with keyword prefixes and trailing abilities
        kw_only = [l for l in lines if split_lead_keywords(l)[1] == ""]
        lines = [l for l in lines if l not in kw_only] or lines
        flags, body = split_lead_keywords(" ".join(lines))
        body = body.strip()
        try:
            state = {"tcount": 0}
            eff = parse_effect(body, state)
            from . import SpellEffect
            abilities.append(SpellEffect(eff, label=defn.name, source_text=body))
        except ParseError as e:
            complete = False
            errors.append(str(e))
    else:
        from . import empower_costs
        has_empower_kw = bool(empower_costs(defn))
        for line in lines:
            if has_empower_kw and re.match(r"\s*\[Empower\]", line):
                continue          # the Empower keyword ability (and its cost) comes from keyword_abilities
            try:
                abilities.extend(script_line(defn, line))
            except ParseError as e:
                complete = False
                errors.append(str(e))
    etext = clean_text(defn.effect_text)
    for line in [l.strip() for l in etext.split("\n") if l.strip()]:
        try:
            flags, body = split_lead_keywords(line)
            if not body:
                # keywords granted to the unit this is attached to, e.g. "[Shield 2]" or "[Tank]"
                for f in flags:
                    m = re.match(r"(.+?)(?:\s+(\d+))?$", f)
                    name = m.group(1).strip().replace(" ", "_").replace("-", "_")
                    effect_abilities.append(Static("attached", "keyword", (name, int(m.group(2)) if m.group(2) else True),
                                                   source_text=line))
                continue
            abs_ = script_line(defn, line)
            for a in abs_:
                if isinstance(a, Static) and a.sel == "self":
                    a.sel = "attached"
            effect_abilities.extend(abs_)
        except ParseError as e:
            complete = False
            errors.append(str(e))
    if errors:
        defn.keywords["_unparsed"] = errors
    return abilities, effect_abilities, complete
