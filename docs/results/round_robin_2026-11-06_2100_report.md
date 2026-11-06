# Gameplay audit (900 games, policy expert)

## Rule invariant problems

None found.

## Mechanics used (per game average)

| deck | games | win% | turns | runes_channeled | draw | play_unit | play_spell | play_gear | play_champion | unit_played_to_battlefield | ambush | hide | play_from_facedown | reaction_on_chain | play_in_showdown | play_in_combat | play_on_opponents_turn | activate | equip | empower | targeting | triggers | replacements | move_standard | ganking_move | move_by_effect | combat | attacker | defender | conquer | hold | stun | counter | recall | xp_events |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Azir, Emperor of the Sands (Andrew L McD | 180 | 26 | 8.7 | 17.9 | 12.9 | 3.2 | 4.7 | 6.6 | 1.0 | 0.9 | 0.1 | 1.1 | 0.9 | 1.9 | 0.4 | 0.8 | 0.0 | 15.4 | 12.5 | 0.0 | 4.2 | 8.6 | 0.0 | 7.1 | 0.0 | 0.2 | 2.7 | 3.4 | 3.5 | 2.5 | 2.7 | 0.8 | 0.6 | 2.4 | 0.0 |
| Curator of the Sands (Kenny Tran, 34th R | 180 | 45 | 7.8 | 14.4 | 16.2 | 8.6 | 7.9 | 0.0 | 1.0 | 3.2 | 0.0 | 0.3 | 0.2 | 2.5 | 0.7 | 0.7 | 0.0 | 0.0 | 0.0 | 0.0 | 5.9 | 15.3 | 0.0 | 9.1 | 0.0 | 0.2 | 2.1 | 3.1 | 3.9 | 2.7 | 3.7 | 0.0 | 0.7 | 0.0 | 1.1 |
| Gloomist (vince, 9th Convergence IV) | 180 | 71 | 7.4 | 15.5 | 12.4 | 8.7 | 3.1 | 2.9 | 1.0 | 4.8 | 0.3 | 1.6 | 1.4 | 2.1 | 0.5 | 0.7 | 0.0 | 5.0 | 3.5 | 0.1 | 3.4 | 12.6 | 0.6 | 10.1 | 0.8 | 0.2 | 2.3 | 3.3 | 5.5 | 2.5 | 4.7 | 2.0 | 0.3 | 2.0 | 0.2 |
| Irelia, Blade Dancer (Arito, 2nd Converg | 180 | 25 | 7.7 | 15.9 | 11.4 | 6.3 | 6.6 | 2.3 | 1.0 | 2.4 | 0.0 | 0.4 | 0.4 | 2.3 | 0.3 | 0.8 | 0.0 | 5.0 | 5.0 | 0.0 | 8.6 | 17.8 | 0.4 | 8.7 | 0.7 | 0.7 | 2.9 | 4.0 | 2.5 | 2.3 | 3.0 | 0.4 | 0.6 | 2.2 | 0.3 |
| Kai'Sa, Daughter of the Void (Dan Bridge | 180 | 58 | 8.1 | 14.4 | 12.3 | 9.3 | 5.5 | 0.4 | 1.0 | 3.7 | 0.0 | 0.4 | 0.4 | 1.2 | 0.6 | 0.6 | 0.0 | 4.8 | 0.0 | 0.0 | 8.3 | 10.0 | 0.0 | 9.7 | 0.0 | 0.1 | 1.8 | 2.7 | 4.7 | 2.7 | 4.1 | 0.0 | 0.1 | 0.0 | 0.0 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | 180 | 51 | 7.5 | 14.9 | 10.0 | 7.0 | 6.2 | 0.8 | 1.0 | 3.9 | 0.7 | 0.2 | 0.2 | 1.4 | 0.5 | 0.4 | 0.0 | 0.0 | 0.0 | 0.0 | 7.5 | 9.1 | 0.6 | 9.3 | 0.3 | 0.1 | 2.4 | 3.2 | 4.1 | 2.1 | 4.3 | 0.0 | 0.4 | 0.9 | 2.6 |
| Riven, The Exile (MERC Koopastar, 1st Co | 180 | 73 | 7.6 | 14.9 | 11.8 | 8.7 | 3.9 | 1.6 | 1.0 | 4.5 | 0.0 | 0.9 | 0.8 | 2.1 | 0.6 | 0.5 | 0.0 | 2.0 | 0.8 | 0.0 | 5.8 | 14.1 | 5.9 | 12.8 | 0.5 | 0.5 | 2.3 | 4.1 | 5.4 | 3.2 | 4.4 | 0.2 | 0.5 | 1.5 | 0.5 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | 180 | 48 | 8.1 | 16.3 | 11.7 | 7.2 | 4.5 | 2.2 | 1.0 | 2.9 | 0.0 | 0.9 | 0.8 | 1.8 | 0.3 | 0.5 | 0.0 | 5.8 | 3.5 | 0.7 | 8.1 | 10.7 | 1.0 | 10.2 | 0.0 | 1.0 | 2.3 | 3.7 | 4.7 | 2.7 | 3.8 | 0.7 | 0.2 | 1.8 | 0.0 |
| Viktor, Herald of the Arcane (Calvin Jin | 180 | 38 | 8.1 | 16.2 | 14.2 | 3.3 | 9.8 | 2.7 | 1.0 | 1.0 | 0.0 | 1.3 | 1.1 | 1.0 | 0.6 | 2.0 | 0.0 | 8.6 | 1.5 | 0.0 | 7.7 | 11.9 | 0.0 | 13.4 | 0.1 | 0.2 | 3.0 | 5.0 | 4.5 | 3.4 | 2.7 | 0.5 | 0.2 | 0.5 | 0.0 |
| Void Burrower (funnyanger, 18th Converge | 180 | 66 | 7.6 | 14.8 | 8.9 | 10.2 | 1.9 | 1.4 | 0.9 | 6.0 | 1.0 | 0.0 | 0.0 | 1.0 | 0.1 | 0.3 | 0.0 | 0.0 | 0.0 | 0.0 | 2.9 | 11.3 | 0.0 | 10.4 | 0.1 | 0.2 | 2.7 | 5.2 | 5.7 | 2.9 | 4.4 | 0.0 | 0.1 | 0.1 | 0.0 |

Average turns 16.6; longest chain 10; games without a winner 0; first player won 497/900.

## Matchups (row vs column: win%, games, 95% interval)

| deck | opponent | win% | games | 95% interval |
|---|---|---|---|---|
| Azir, Emperor of the Sands (Andrew L McD | Curator of the Sands (Kenny Tran, 34th R | 50 | 20 | 30-70 |
| Azir, Emperor of the Sands (Andrew L McD | Gloomist (vince, 9th Convergence IV) | 0 | 20 | -0-16 |
| Azir, Emperor of the Sands (Andrew L McD | Irelia, Blade Dancer (Arito, 2nd Converg | 60 | 20 | 39-78 |
| Azir, Emperor of the Sands (Andrew L McD | Kai'Sa, Daughter of the Void (Dan Bridge | 30 | 20 | 15-52 |
| Azir, Emperor of the Sands (Andrew L McD | Master Yi, Wuju Bladesman (Derpinox, 24t | 20 | 20 | 8-42 |
| Azir, Emperor of the Sands (Andrew L McD | Riven, The Exile (MERC Koopastar, 1st Co | 20 | 20 | 8-42 |
| Azir, Emperor of the Sands (Andrew L McD | Rogue Assassin (Alex Gorica, 2nd Riftbou | 20 | 20 | 8-42 |
| Azir, Emperor of the Sands (Andrew L McD | Viktor, Herald of the Arcane (Calvin Jin | 15 | 20 | 5-36 |
| Azir, Emperor of the Sands (Andrew L McD | Void Burrower (funnyanger, 18th Converge | 15 | 20 | 5-36 |
| Curator of the Sands (Kenny Tran, 34th R | Gloomist (vince, 9th Convergence IV) | 30 | 20 | 15-52 |
| Curator of the Sands (Kenny Tran, 34th R | Irelia, Blade Dancer (Arito, 2nd Converg | 85 | 20 | 64-95 |
| Curator of the Sands (Kenny Tran, 34th R | Kai'Sa, Daughter of the Void (Dan Bridge | 35 | 20 | 18-57 |
| Curator of the Sands (Kenny Tran, 34th R | Master Yi, Wuju Bladesman (Derpinox, 24t | 35 | 20 | 18-57 |
| Curator of the Sands (Kenny Tran, 34th R | Riven, The Exile (MERC Koopastar, 1st Co | 25 | 20 | 11-47 |
| Curator of the Sands (Kenny Tran, 34th R | Rogue Assassin (Alex Gorica, 2nd Riftbou | 35 | 20 | 18-57 |
| Curator of the Sands (Kenny Tran, 34th R | Viktor, Herald of the Arcane (Calvin Jin | 70 | 20 | 48-85 |
| Curator of the Sands (Kenny Tran, 34th R | Void Burrower (funnyanger, 18th Converge | 40 | 20 | 22-61 |
| Gloomist (vince, 9th Convergence IV) | Irelia, Blade Dancer (Arito, 2nd Converg | 95 | 20 | 76-99 |
| Gloomist (vince, 9th Convergence IV) | Kai'Sa, Daughter of the Void (Dan Bridge | 50 | 20 | 30-70 |
| Gloomist (vince, 9th Convergence IV) | Master Yi, Wuju Bladesman (Derpinox, 24t | 65 | 20 | 43-82 |
| Gloomist (vince, 9th Convergence IV) | Riven, The Exile (MERC Koopastar, 1st Co | 35 | 20 | 18-57 |
| Gloomist (vince, 9th Convergence IV) | Rogue Assassin (Alex Gorica, 2nd Riftbou | 90 | 20 | 70-97 |
| Gloomist (vince, 9th Convergence IV) | Viktor, Herald of the Arcane (Calvin Jin | 95 | 20 | 76-99 |
| Gloomist (vince, 9th Convergence IV) | Void Burrower (funnyanger, 18th Converge | 40 | 20 | 22-61 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Kai'Sa, Daughter of the Void (Dan Bridge | 35 | 20 | 18-57 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Master Yi, Wuju Bladesman (Derpinox, 24t | 20 | 20 | 8-42 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Riven, The Exile (MERC Koopastar, 1st Co | 15 | 20 | 5-36 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Rogue Assassin (Alex Gorica, 2nd Riftbou | 20 | 20 | 8-42 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Viktor, Herald of the Arcane (Calvin Jin | 55 | 20 | 34-74 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Void Burrower (funnyanger, 18th Converge | 20 | 20 | 8-42 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Master Yi, Wuju Bladesman (Derpinox, 24t | 65 | 20 | 43-82 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Riven, The Exile (MERC Koopastar, 1st Co | 45 | 20 | 26-66 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Rogue Assassin (Alex Gorica, 2nd Riftbou | 60 | 20 | 39-78 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Viktor, Herald of the Arcane (Calvin Jin | 60 | 20 | 39-78 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Void Burrower (funnyanger, 18th Converge | 45 | 20 | 26-66 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Riven, The Exile (MERC Koopastar, 1st Co | 30 | 20 | 15-52 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Rogue Assassin (Alex Gorica, 2nd Riftbou | 60 | 20 | 39-78 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Viktor, Herald of the Arcane (Calvin Jin | 60 | 20 | 39-78 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Void Burrower (funnyanger, 18th Converge | 10 | 20 | 3-30 |
| Riven, The Exile (MERC Koopastar, 1st Co | Rogue Assassin (Alex Gorica, 2nd Riftbou | 70 | 20 | 48-85 |
| Riven, The Exile (MERC Koopastar, 1st Co | Viktor, Herald of the Arcane (Calvin Jin | 85 | 20 | 64-95 |
| Riven, The Exile (MERC Koopastar, 1st Co | Void Burrower (funnyanger, 18th Converge | 70 | 20 | 48-85 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Viktor, Herald of the Arcane (Calvin Jin | 50 | 20 | 30-70 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Void Burrower (funnyanger, 18th Converge | 35 | 20 | 18-57 |
| Viktor, Herald of the Arcane (Calvin Jin | Void Burrower (funnyanger, 18th Converge | 30 | 20 | 15-52 |
