"""Hand-written card scripts. Each function returns a list of abilities (replacing auto output) or a dict
{'abilities': [...], 'effect_abilities': [...], 'replace': bool}."""
from __future__ import annotations

from . import script, SpellEffect
from ..abilities import Static, Triggered, Activated, PlayPermission, Replacement
from ..selectors import Sel
from .. import ops as O
from ..vm import Ref
