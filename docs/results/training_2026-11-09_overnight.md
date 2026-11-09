# Overnight training 2026-11-09 (gen 8 as the benchmark)

Derrick (06:03 UTC): use gen 8 as the benchmark and train the AI to use its interaction and look further than one
turn ahead. Every candidate played gen 8 head to head (same decks and shuffle, seats swapped); promotion needs 55%+.
"Mirror" gates give both AIs the same deck, so the matchup between two different decks adds no noise.

| candidate | idea | games | score vs gen 8 |
|---|---|---|---|
| learned-deep:gen_008 | close calls re-checked through the opponent's whole turn, our counters allowed there (PR #30) | 192 | 51.6% |
| learned-deep:gen_008:0.15:3 | the same on far more decisions (margin 0.15), 3 samples | 57 + 80 | 56.1%, then 41.3% (65/140 together) |
| learned-r:gen_008 | in the lookahead the opponent may answer during our turn (tricks, counters) | 199 | 43.7% |
| learned:gen_008:s6 | 6 sampled hands per option instead of 3 (less noise) | 200 | 49.5% |
| cand_v3k | new linear model on held-reaction features, 1800 games incl. 600 new ones with Kennen | 200 | 44.5% |
| cand_v2k | new linear model, older features, gens 12-13 + the 600 new games | 200 | 50.5% |
| gen 8 + gen 10 + gen 13 | three value nets averaged as the judge (mirror) | 199 | 51.8% |
| learned-tmcts:60 | MCTS with both players' choices in the tree, leaves judged at the next turn (mirror) | 80 | 30.0% |

## What this says

- Nothing beat gen 8. More search on top of the same value model (looking through the opponent's turn, more
  samples, more decisions checked) lands at 44-52%: the search is not what limits it.
- Letting the simulated opponent react during our turn made play worse (43.7%). The opponent inside the lookahead
  is the cheap one-sample AI and it answers badly, so the judge learned to fear the wrong things. A better opponent
  model costs a lot more time per move.
- MCTS over both players' choices lost badly at 60 iterations: the budget is spread over the opponent's replies and
  every option gets only a few visits. The greedy lookahead spends the same time on every option evenly.
- Retraining on new data (incl. the first Kennen games and the engine fixes) gives models that tie gen 8. The linear
  value model has reached what it can learn from the features it sees; held reactions still get no weight.

## Next levers (not tried yet)

1. A value model that can represent interaction: a small net on top of the linear model trained on far more
   positions (the 8000-game wide-and-deep try overfit at 32 hidden units; try 8-16 with weight decay).
2. A policy target instead of only a value target: record which option the deep search picked and train a move
   ranker, so the fast AI learns the deep search's choices directly (needs deep-search self-play, ~20 s a game here).
3. A real opponent model inside the lookahead: the opponent's reply chosen by the learned AI itself (2-3x slower).
