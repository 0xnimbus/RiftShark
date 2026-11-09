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
| cand_w8 | 8-unit neural correction on top of gen 8 (weight decay), 5000 games; better prediction (val loss 0.507 vs 0.528) (mirror) | 200 | 46.5% |
| learned-tmcts:60 | MCTS with both players' choices in the tree, leaves judged at the next turn (mirror) | 80 | 30.0% |
| cand_v4 (day) | v4 features for held answers (affordable removal, bounce, fast spells, loose Equipment), 1000 new games (mirror) | 200 | 42.7% |
| cand_rank1 (day) | gen 8's data plus option-ranking pairs from tools/rank_data.py (mirror) | 200 | 43.5% |

## What this says

- Nothing beat gen 8. More search on top of the same value model (looking through the opponent's turn, more
  samples, more decisions checked) lands at 44-52%: the search is not what limits it.
- Letting the simulated opponent react during our turn made play worse (43.7%). The opponent inside the lookahead
  is the cheap one-sample AI and it answers badly, so our AI plays around the wrong things. A better opponent
  model costs a lot more time per move.
- MCTS over both players' choices lost badly at 60 iterations: the budget is spread over the opponent's replies and
  every option gets only a few visits. The greedy lookahead spends the same time on every option evenly.
- Better prediction is not better play: the neural correction predicts results clearly better than gen 8 and still
  loses 46.5%. The judge is trained to predict who wins from where things stand, not to rank the options of one
  decision, and those are different jobs.
- Retraining on new data (incl. the first Kennen games and the engine fixes) gives models that tie gen 8. The linear
  value model has reached what it can learn from the features it sees; held reactions still get no weight.

## Kennen with the gen 8 AI (20 games per matchup, seats alternating)

| vs | Kennen win% |
|---|---|
| Irelia | 60 |
| Vex (Gloomist) | 55 |
| Viktor | 45 |
| Nasus (Curator) | 40 |
| Rek'Sai (Void Burrower) | 35 |
| Akali (Rogue Assassin) | 30 |
| Riven | 30 |
| Azir | 25 |
| Kai'Sa | 15 |
| Master Yi | 5 |

About 34% overall, while Kennen won the Europe Regional Championship. One game against Master Yi (seed 11) shows
why: on its first turns Kennen plays Edge of Night to its base as a plain gear with no unit to carry it (it can't
hide it without a battlefield), moves Equipment back and forth, and puts units in base without contesting while
Yi scores 5 points by turn 7. The value judge rewards cards on the board over cards held in hand and has never seen
what held bounce spells, counters and hidden cards are worth: the same blind spot that underrates Riven. This is
the clearest test case for the next levers.

## Next levers (not tried yet)

1. Train the judge for the job it does: rank the options of one decision. For sampled decisions, play every option
   out to the end of the game a few times with the current AI and train on which option did better (a pairwise loss
   over the options' turn-end positions), instead of only predicting the winner from a position. Costly labels
   (~10-20 playouts per decision), but aimed straight at move choice.
2. Features for what held cards can do next turn (an affordable bounce, kill, counter or hidden card, by target),
   since the current ones only count reactions in hand; Kennen and Riven are the test decks.
3. A real opponent model inside the lookahead: the opponent's reply chosen by the learned AI itself (2-3x slower).

## Day 2026-11-09: held-answer features and option-ranking labels

- **v4 features** (`_held_answers`: affordable removal, bounce, fast spells, Equipment with no unit) trained on 1000 new
  gen 8 self-play games: 42.7%. Trained to predict the winner, the new features got weights near zero, like the held
  reactions in v3.
- **Option-ranking labels** (`tools/rank_data.py`, lever 1 above): 400 games, 1186 decisions (37% reaction windows in
  the opponent's turn), every option (up to 4) played to the end 3 times with gen 8 (one sample) on both sides, in the
  same sampled world per playout. What the data says:
  - The labels are noisy: two playouts agree on which of two options is better only 60% of the time, and in 61% of
    playouts every option ends the same way. Most options of a decision barely change the result.
  - Gen 8's judge already ranks the options right 72.5% of the time where the mean results differ by 0.6+ (heuristic
    score alone: 69%); on single playouts 61%, near the 60% the labels agree with each other.
  - Training the linear judge with these pairs (gens 6-8 + 1353 pairs) did not raise held-out pair accuracy and scored
    43.5% against gen 8.
- Reading: the judge's weights are not the main error. The error is the position it is shown: the end of our turn
  with the opponent passing. The next experiment puts the learned AI itself in the opponent's seat inside the lookahead
  (the earlier `learned-r` used the cheap heuristic AI there and lost 43.7%).
