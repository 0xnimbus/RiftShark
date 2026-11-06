"""Auto-scripter: parse templated rules text into abilities. See grammar in auto_grammar.py (WIP)."""
from __future__ import annotations


def script_card(defn):
    """Return (abilities, effect_abilities, complete) or None when nothing could be parsed."""
    try:
        from . import auto_grammar
    except ImportError:
        return None
    return auto_grammar.script_card(defn)
