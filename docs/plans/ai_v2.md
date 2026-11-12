# AI v2 plan: a fast opponent model, a deeper search, and learning from that search

## Why

Gen 14 is a one-turn lookahead plus a linear judge. 15 attempts to improve it tied or lost
(docs/results/training_2026-11-10.md). The deeper searches we tried failed for one reason: inside the search, the
opponent's turn was played by the quick hand-written AI, which is far weaker than gen 14. A deeper look is only
as good as its picture of the opponent. Gen 14 itself is too slow to play the opponent inside a search, because
each of its moves already simulates every option.

## The plan

1. **Policy net: a fast copy of gen 14.** A model that scores options straight from the position and a description of
   each option: what kind of move, which card (card identities included), cost, targets. No simulation, so a move takes
   milliseconds instead of about a second. It is trained to pick what gen 14 picks, from about 2000 recorded gen-14
   games (each decision with its options and gen 14's choice). Written with numpy; the engine stays dependency-free.
   - Check: how often it agrees with gen 14, and its win rate against gen 14 when it plays alone (expected: weaker, much faster).
2. **Two-turn search with the policy net as the opponent.** For our main decisions, the best few options (by gen 14's
   one-turn judgement) are played out through the rest of our turn and the opponent's whole turn. The policy net plays the
   opponent, and our own answers in its turn, so held counters and combat tricks are actually used. The position is judged
   at the start of our next turn. All copies are determinised from our own view, so the AI never sees hidden information.
   - Check: gate vs gen 14 and Riven/Kennen vs all decks (the matchups where holding interaction matters).
3. **Learn from the search (expert iteration).** Self-play with the two-turn search AI. Train the policy net on the
   search's choices and the judge on the results, then repeat. Each round the opponent model inside the search gets
   stronger, so the search does too. This is the loop that can keep improving, unlike the current judge.
4. **Neural judge with card identities**, trained on the much larger data from step 3, once the data is there.

## Costs (4 cores)

| Step | Work | Machine time |
|---|---|---|
| 1 | record 2000 gen-14 games with options; option features; train and test the policy net | ~1 day |
| 2 | search code; speed tuning; gate + Riven/Kennen checks (searching games are ~5-10x slower) | ~1 day |
| 3 | each round: ~1000 search self-play games (~6-10 h) + training + gate | ~half a day per round |
| 4 | after 2-3 rounds of step 3 | ~1 day |

Each step has its own pass/fail check against gen 14 before the next one starts.
