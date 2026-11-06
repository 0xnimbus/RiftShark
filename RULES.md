# What the engine models (and what it does not yet)

This is a deliberately simplified model of Riftbound 1v1 so the search, batch runner and
replay tooling could be built and tested end to end. Everything below is in
`riftsim/engine.py`; the card data in `data/cards/demo_set.json` is **placeholder cards,
not real Riftbound cards**. Treat this file as the checklist to review against the real
rulebook before trusting any win rates.

## Modeled

- 2 players, 40 card main deck, 12 rune deck, 1 legend, 1 champion in a champion zone, 1 battlefield per player (picked at random from the deck's list each game). Deck legality is validated (40/12, max 3 copies, legend domain identity).
- Win at 8 points. Opening hand 4. Each turn: ready everything you control ("awaken"), score 1 point per battlefield you still hold, channel 2 runes (3 on the second player's first turn), draw 1.
- Costs: energy is paid by exhausting any ready rune; power is paid by recycling a rune of the matching domain (back to the bottom of the rune deck). Exhausted runes may be recycled.
- Burn out: drawing from an empty deck shuffles the trash back in and gives the opponent a point.
- Actions: play a unit/spell from hand, play the champion from the champion zone, move ready units (any set of base units to one battlefield, or a unit from a battlefield back to base), end turn. Units arrive exhausted unless Accelerated. Moving exhausts the unit.
- Arriving at an empty battlefield conquers it (1 point, once per battlefield per turn). Arriving at a defended one triggers combat: total attacking might vs total defending might, damage assigned to kill as many units as possible, Tank units must be assigned lethal damage first. If defenders are wiped the attackers conquer; if both sides survive the attackers are recalled to base. Damage and temporary buffs clear at end of turn.
- Final point rule: the winning point cannot come from a conquest unless every battlefield was scored this turn (the engine draws a card instead).
- Keywords: Assault N (+N might attacking), Shield N (+N might defending), Tank, Ganking (may move battlefield to battlefield), Accelerate (pay +1 energy and +1 power to arrive ready).
- Effects (spells and "on play" unit triggers): draw N, damage N to a unit, +N might buff until end of turn, kill a unit with might <= N, ready N runes. Legend abilities: "+1 might attacking for a domain", "draw on first conquest each turn".
- A safety cap of 40 actions per turn and 60 half-turns per game (counted as a draw).

## Not modeled yet (biggest gaps first)

1. **Real card text.** Only the effect primitives above exist; real cards need more (reactions, triggered abilities, gear, equipment, "hold" effects, choose-one, conditional costs).
2. **Priority and the reaction window.** Riftbound lets the non-active player respond (Reaction spells, burst speed). The engine is strictly turn-based: only the active player acts.
3. **Showdowns and combat ordering.** Combat is resolved as one simultaneous exchange with automatic damage assignment. The real game has a showdown with both players acting, chosen damage assignment, and Deflect/Hidden style keywords.
4. **Battlefield effects.** Battlefields are names only; their printed abilities do nothing.
5. **Multi-battlefield splits.** A move sends all chosen units to one battlefield; a unit cannot move twice in a turn even if an effect readies it.
6. **Mulligans, 3 and 4 player modes, legend-specific points thresholds.**

Each item is isolated enough to add without touching the search or replay code: new card
effects go in `_resolve_effect` and `effect_targets`, new structure (reactions) changes
`legal_actions`/`apply` and the turn loop.
