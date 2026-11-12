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
| 2026-11-08 17:16 UTC | learned:sp_linear | learned:gen_008 | 48.5% (42-55) | 200 | 3000 new local self-play games + gens 5-13 data (8000 games, outcome labels); not promoted |
| 2026-11-08 17:16 UTC | learned:sp_wide | learned:gen_008 | 39.0% (33-46) | 200 | 3000 new local self-play games + gens 5-13 data (8000 games, outcome labels); not promoted (wide-and-deep, 32 hidden) |
| 2026-11-08 19:44 UTC | learned:v3_td | learned:gen_008 | 46.5% (40-53) | 200 | features v3 (held reactions) + TD labels with responses in the opponent turn, 1200 games; held-reaction weights ~0; not promoted |
| 2026-11-09 06:33 UTC | learned-deep:gen_008 | learned:gen_008 | 51.6% (44-58) | 192 | deep search with responding in the opponent turn (PR #30), seeds 54000 |
| 2026-11-09 07:30 UTC | learned-r:gen_008 | learned:gen_008 | 43.7% (37-51) | 199 | opponent may react during our turn in the lookahead (learned-r), seeds 56000 |
| 2026-11-09 08:43 UTC | learned:gen_008:s6 | learned:gen_008 | 49.5% (43-56) | 200 | one-turn lookahead with 6 determinised samples per option instead of 3, seeds 58000 |
| 2026-11-09 10:12 UTC | learned:models/cand_v3k.json | learned:gen_008 | 44.5% (38-51) | 200 | v3 linear, TD: sp_v3_1 + 600 new gen 8 self-play games incl. Kennen and the equipment fixes |
| 2026-11-09 10:30 UTC | learned:models/cand_v2k.json | learned:gen_008 | 50.5% (44-57) | 200 | v2-width linear, TD: gens 12-13 + the same 600 new games |
| 2026-11-09 10:50 UTC | learned:gen_008+gen_010+gen_013 | learned:gen_008 | 51.8% (45-59) | 199 | ensemble: gen 8 + gen 10 + gen 13 averaged in logit space, mirror matches |
| 2026-11-09 11:49 UTC | learned:models/cand_w8.json | learned:gen_008 | 46.5% (40-53) | 200 | wide-and-deep on top of gen 8: 8 hidden units, l2 1e-2, gens 6-13 + 600 new games (outcome labels); mirror |
| 2026-11-09 14:06 UTC | learned:models/cand_v4.json | learned:gen_008 | 42.7% (36-50) | 199 | v4 features (held answers: affordable removal, bounce, fast spells, loose Equipment), linear td on 1000 new gen-8 self-play games; mirror |
| 2026-11-09 18:38 UTC | learned:models/cand_rank1.json | learned:gen_008 | 43.5% (37-50) | 200 | gen 8's data (gens 6-8) + option-ranking pairs (each option of ~1200 decisions played out 3x to the end, pairs where mean results differ by 0.6+, weight 1); mirror |
| 2026-11-09 19:21 UTC | learned-rl:gen_008 | learned:gen_008 | 43.5% (35-53) | 115 | learned-rl: in the lookahead the opponent answers during our turn with the one-sample learned AI (gen 8) instead of the heuristic AI; mirror |
| 2026-11-10 01:47 UTC | learned:models/cand_mb.json | learned:gen_008 | 45.5% (39-52) | 200 | card-identity features of our own board masked (170-233) when training on gens 6-8: the judge can't reward a card just for being on the board; mirror |
| 2026-11-10 02:06 UTC | learned:models/cand_mhb.json | learned:gen_008 | 54.0% (47-61) | 200 | card-identity features of our hand and board masked (106-233), gens 6-8; mirror |
| 2026-11-10 02:26 UTC | learned:models/cand_mhb.json | learned:gen_008 | 52.0% (45-59) | 200 | cand_mhb confirmation on fresh seeds; mirror |
| 2026-11-10 02:49 UTC | learned:models/cand_mhb2.json | learned:gen_008 | 54.3% (47-61) | 199 | hand+board card identities masked, trained on gens 6-13 + 1600 newer games (outcome labels); mirror |
| 2026-11-10 03:07 UTC | learned:models/cand_mhb2.json | learned:gen_008 | 48.0% (41-55) | 200 | cand_mhb2 confirmation on fresh seeds; mirror |
| 2026-11-10 03:29 UTC | learned:models/cand_mall.json | learned:gen_008 | 50.2% (43-57) | 197 | all card identities masked (hand, our board, their board), gens 6-13 + 1600 newer games; mirror |
| 2026-11-10 08:44 UTC | learned:models/cand_mhb3.json | learned:models/cand_mhb.json | 49.2% (42-56) | 199 | masked judge retrained with 1000 self-play games of the masked judge itself, vs cand_mhb; mirror |
| 2026-11-10 20:54 UTC | learned:models/cand_g15lin.json | learned:gen_014 | 45.5% (39-52) | 200 | linear, masked, gens 6-8 + 4000 games of gen 14 self-play; mirror |
| 2026-11-10 21:12 UTC | learned:models/cand_g15nn.json | learned:gen_014 | 45.5% (39-52) | 200 | wide-and-deep (16 hidden, l2 1e-2) on the masked linear, same data; mirror |
| 2026-11-10 21:30 UTC | learned:models/cand_g15on.json | learned:gen_014 | 39.5% (33-46) | 200 | linear, masked, only the 3000 games of gen 14 self-play (on-policy); mirror |
| 2026-11-10 21:48 UTC | learned:models/cand_g15bd.json | learned:gen_014 | 46.0% (39-53) | 200 | linear, masked, gens 6-8 + turn-boundary rows only of 3000 gen-14 games (no what-if rows); mirror |
| 2026-11-11 04:31 UTC | learned:models/cand_g15mix.json | learned:gen_014 | 51.0% (44-58) | 200 | linear, masked, gens 6-8 + mixed self-play (gens 14/8/6/heuristic, epsilon 0.06); mirror |
| 2026-11-11 09:28 UTC | learned:models/cand_g15mix2.json | learned:gen_014 | 44.0% (37-51) | 200 | linear, masked, gens 6-8 + two mixed self-play runs (second: gens 14/8/6/3/heuristic, epsilon 0.12); mirror |
| 2026-11-11 10:50 UTC | learned:gen_014:rw | learned:gen_014 | 47.5% (41-54) | 200 | gen 14 with reaction windows judged after the opponent plays out its turn (rw); mirror |
| 2026-11-11 14:56 UTC | learned:models/cand_pg1.json | learned:gen_014 | 41.7% (35-49) | 199 | policy gradient iteration 1 (2000 games at T 0.1, normalized step 0.2) from gen_014; mirror |
| 2026-11-11 15:18 UTC | learned:models/cand_pg1s.json | learned:gen_014 | 42.5% (36-49) | 200 | policy gradient, 2000 games at T 0.1, raw step (lr 1, norm 0.087); mirror |
| 2026-11-11 15:40 UTC | learned:models/cand_pg1z.json | learned:gen_014 | 50.5% (44-57) | 200 | policy gradient, 2000 games at T 0.1, raw step on weights over 2 std errors only; mirror |
| 2026-11-11 19:26 UTC | learned:models/cand_pg2z.json | learned:gen_014 | 52.0% (45-59) | 200 | policy gradient, 5000 games (gen 14 + cand_pg1z) at T 0.1, raw step on weights over 2 std errors; mirror |
| 2026-11-11 19:48 UTC | learned:models/cand_pg2z_x3.json | learned:gen_014 | 49.0% (42-56) | 200 | policy gradient, 5000 games, step on weights over 2 std errors scaled x3; mirror |
| 2026-11-11 20:08 UTC | learned:models/cand_pg2z_x8.json | learned:gen_014 | 45.0% (38-52) | 200 | policy gradient, 5000 games, step on weights over 2 std errors scaled x8; mirror |
| 2026-11-12 07:11 UTC | learned:gen_014:p=policy_g14:ps3:crn:b=0.3:d6 | learned:gen_014 | 51.5% | 99 | AI v2 two-turn search: policy-net-pruned learned opponent, common random numbers, 6 samples, blend 0.3; game limit 2400 s; mirror |
| 2026-11-12 12:08 UTC | learned:gen_014:p=policy_g14:ps3:crn:b=0.3:d10 | learned:gen_014 | 65.0% (55-74) | 100 | AI v2 two-turn search with 10 shared samples, blend 0.3; seed 91000; game limit 4000 s; mirror |
