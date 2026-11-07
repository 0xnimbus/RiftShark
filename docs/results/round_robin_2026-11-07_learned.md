# Round-robin, 2026-11-07 01:20 UTC: 10 decks, the stronger "Learned" AI both sides, 874 games

AI: `learned:heuristic`, the turn-boundary lookahead that beats the old expert AI 87-13 (models/ladder.md). Engine at
0376e85 (#6, after the damage-assignment fix #5). Played on GitHub Actions, 15 shards (run 42313634208), adaptive: up to
20 games per pair, a pair stops early once its 95% interval is clear (8-20 games). Row deck's wins-losses against the
column deck; "expert AI" is the pooled 1800-game expert table (docs/results/round_robin_2026-11-06_2100.md).

No rule invariant problems; 0 crashes; 0 games hit the turn cap; first player won 530/874 (61%); average 16.6 turns.

| deck | overall | expert AI (1800 games) | Kai'Sa | Void Burrower | Riven | Viktor | Master Yi | Curator of the Sands | Gloomist | Azir | Rogue Assassin | Irelia |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Kai'Sa | 79% | 57% | - | 15-5 | 11-3 | 17-3 | 16-4 | 10-10 | 16-4 | 16-4 | 18-2 | 18-2 |
| Void Burrower | 65% | 65% | 5-15 | - | 12-8 | 10-10 | 13-7 | 12-8 | 15-5 | 17-3 | 15-5 | 18-2 |
| Riven | 61% | 72% | 3-11 | 8-12 | - | 11-9 | 9-11 | 13-7 | 13-7 | 16-4 | 16-4 | 18-2 |
| Viktor | 61% | 36% | 3-17 | 10-10 | 9-11 | - | 14-6 | 11-9 | 7-1 | 16-4 | 16-4 | 17-3 |
| Master Yi | 52% | 54% | 4-16 | 7-13 | 11-9 | 6-14 | - | 11-9 | 12-8 | 14-6 | 13-7 | 16-4 |
| Curator of the Sands | 48% | 45% | 10-10 | 8-12 | 7-13 | 9-11 | 9-11 | - | 11-9 | 8-12 | 10-10 | 11-1 |
| Gloomist | 44% | 71% | 4-16 | 5-15 | 7-13 | 1-7 | 8-12 | 9-11 | - | 12-8 | 14-6 | 14-6 |
| Azir | 38% | 24% | 4-16 | 3-17 | 4-16 | 4-16 | 6-14 | 12-8 | 8-12 | - | 9-11 | 18-2 |
| Rogue Assassin | 36% | 42% | 2-18 | 5-15 | 4-16 | 4-16 | 7-13 | 10-10 | 6-14 | 11-9 | - | 15-5 |
| Irelia | 16% | 32% | 2-18 | 2-18 | 2-18 | 3-17 | 4-16 | 1-11 | 6-14 | 2-18 | 5-15 | - |

## What changed with a stronger pilot

- **Kai'Sa is now clearly first (79%, was 57%)** and beats Riven 11-3; under the expert AI Riven beat Kai'Sa 24-16.
- **Gloomist falls from 71% to 44%** and **Riven from 72% to 61%**: their edge was largely the weak pilot on the other
  side of the table.
- **Viktor jumps from 36% to 61%** and **Azir from 24% to 38%**: decks that need plans over several turns gain the most
  from the better lookahead, as expected.
- Void Burrower (65%), Master Yi and Curator barely move. Irelia stays last (16%).

These numbers still come from an AI that is far from expert human play, so treat them as provisional; each stronger AI
generation (models/ladder.md) should be re-run through this table.
