# Learned AI generations

Each generation trains the value net on self-play of the best AI so far, then plays it head to head (same decks and shuffles, seats swapped). It replaces the best AI only with a score of 55% or more.
Written by tools/train_loop.py; the `learned` policy and the play page's Learned difficulty use the generation in best.json.

| gen | date | self-play by | positions | val loss (constant) | val acc | vs best: score (95% interval) | games | promoted |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-06 23:04 UTC | expert | 79056 | 0.4884 (0.6931) | 0.7733 | 85.0% (79-89) vs expert | 200 | yes |
| 2 | 2026-11-07 02:43 UTC | learned:heuristic | 126880 | 0.457 (0.6931) | 0.782 | 40.7% (34-48) vs learned:heuristic | 199 | no |
| 3 | 2026-11-07 04:20 UTC | learned:heuristic (reuses gen 1+2 data) | 126880 | 0.5207 (0.6931) | 0.7524 | 55.3% (48-62) vs learned:heuristic | 197 | yes |
| 4 | 2026-11-07 05:09 UTC | learned:gen_003 | 168892 | 0.5396 (0.6931) | 0.7184 | 49.0% (42-56) vs learned:gen_003 | 200 | no |
| 5 | 2026-11-07 06:01 UTC | learned:gen_003 | 62412 | 0.3697 (0.6931) | 0.8078 | 49.5% (43-56) vs learned:gen_003 | 200 | no |
| 6 | 2026-11-07 07:04 UTC | learned:gen_003 | 125122 | 0.3922 (0.6931) | 0.8094 | 56.0% (49-63) vs learned:gen_003 | 200 | yes |
| 7 | 2026-11-07 07:51 UTC | learned:gen_006 | 189446 | 0.4574 (0.6931) | 0.7774 | 52.5% (46-59) vs learned:gen_006 | 200 | no |
| 8 | 2026-11-07 08:37 UTC | learned:gen_006 | 254986 | 0.4949 (0.6931) | 0.7573 | 55.0% (48-62) vs learned:gen_006 | 200 | yes |
| 9 | 2026-11-07 09:27 UTC | learned:gen_008 | 260414 | 0.5013 (0.6931) | 0.7465 | 43.5% (37-50) vs learned:gen_008 | 200 | no |
| 10 | 2026-11-07 10:21 UTC | learned:gen_008 | 266440 | 0.5206 (0.6931) | 0.7371 | 48.0% (41-55) vs learned:gen_008 | 200 | no |
| 11 | 2026-11-07 11:20 UTC | learned:gen_008 | 269132 | 0.494 (0.6931) | 0.7631 | 45.5% (39-52) vs learned:gen_008 | 200 | no |
| 12 | 2026-11-07 19:54 UTC | learned:gen_008 | 45026 | 0.5214 (0.6931) | 0.8591 | 42.5% (36-49) vs learned:gen_008 | 200 | no |
| 13 | 2026-11-07 21:18 UTC | learned:gen_008 | 486376 | 0.507 (0.6931) | 0.7607 | 49.5% (43-56) vs learned:gen_008 | 200 | no |

## Control matches

`learned:heuristic` uses the same turn-boundary lookahead with the hand-written score instead of a net, so it separates what the lookahead gains from what the trained net gains.

| date | AI | opponent | score (95% interval) | games | note |
|---|---|---|---|---|---|
| 2026-11-06 23:24 UTC | learned:heuristic | expert | 87.0% (79-92) | 100 | lookahead alone, no net: the main gain of generation 1 comes from judging options at the turn boundary |
| 2026-11-06 23:24 UTC | learned:gen_001 | learned:heuristic | 41.7% (30-54) | 60 | stopped at 60 of 100 games: the plain net (gen 1) is weaker than the hand-written score under the same lookahead |
| 2026-11-06 23:40 UTC | net v2 (residual on the hand-written score, gen 1 data) | learned:heuristic | 48.0% (38-58) | 100 | trained on expert self-play: no gain yet; next generations self-play with the stronger lookahead AI |
| 2026-11-07 03:35 UTC | learned:lin_002 | learned:heuristic | 59.2% (49-68) | 98 | linear value model (logistic regression on the features + score), gen 1+2 self-play data |
| 2026-11-07 03:57 UTC | learned:lin_002 | learned:heuristic | 51.5% (42-61) | 99 | linear model, confirmation run (new seeds) |
| 2026-11-07 22:49 UTC | learned-mcts:60:gen_008 | learned:gen_008 | 27.8% (12-51) | 18 | MCTS 60 iterations with the gen 8 model as leaf value: much weaker (judges mid-turn positions) |
| 2026-11-07 22:49 UTC | learned-deep:gen_008 | learned:gen_008 | 57.6% (48-67) | 99 | deep search: close calls re-checked through the opponent's reply turn (seeds 52000) |
| 2026-11-07 22:49 UTC | learned-deep:gen_008 | learned:gen_008 | 47.4% (38-57) | 97 | deep search, confirmation on new seeds (53000): combined 103/196, no clear gain |
