# Learned AI generations

Each generation trains the value net on self-play of the best AI so far, then plays it head to head (same decks and shuffles, seats swapped). It replaces the best AI only with a score of 55% or more.
Written by tools/train_loop.py; the `learned` policy and the play page's Learned difficulty use the generation in best.json.

| gen | date | self-play by | positions | val loss (constant) | val acc | vs best: score (95% interval) | games | promoted |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-06 23:04 UTC | expert | 79056 | 0.4884 (0.6931) | 0.7733 | 85.0% (79-89) vs expert | 200 | yes |

## Control matches

`learned:heuristic` uses the same turn-boundary lookahead with the hand-written score instead of a net, so it separates what the lookahead gains from what the trained net gains.

| date | AI | opponent | score (95% interval) | games | note |
|---|---|---|---|---|---|
| 2026-11-06 23:24 UTC | learned:heuristic | expert | 87.0% (79-92) | 100 | lookahead alone, no net: the main gain of generation 1 comes from judging options at the turn boundary |
| 2026-11-06 23:24 UTC | learned:gen_001 | learned:heuristic | 41.7% (30-54) | 60 | stopped at 60 of 100 games: the plain net (gen 1) is weaker than the hand-written score under the same lookahead |
| 2026-11-06 23:40 UTC | net v2 (residual on the hand-written score, gen 1 data) | learned:heuristic | 48.0% (38-58) | 100 | trained on expert self-play: no gain yet; next generations self-play with the stronger lookahead AI |
