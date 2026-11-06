# Gameplay audit (880 games, policy expert)

## Rule invariant problems

None found.

## Mechanics used (per game average)

| deck | games | win% | turns | runes_channeled | draw | play_unit | play_spell | play_gear | play_champion | unit_played_to_battlefield | ambush | hide | play_from_facedown | reaction_on_chain | play_in_showdown | play_in_combat | play_on_opponents_turn | activate | equip | empower | targeting | triggers | replacements | move_standard | ganking_move | move_by_effect | combat | attacker | defender | conquer | hold | stun | counter | recall | xp_events |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Azir, Emperor of the Sands (Andrew L McD | 170 | 21 | 8.8 | 18.0 | 12.5 | 3.3 | 4.6 | 6.3 | 1.0 | 0.9 | 0.1 | 1.1 | 0.9 | 1.8 | 0.4 | 0.8 | 0.0 | 15.3 | 12.6 | 0.0 | 4.1 | 8.6 | 0.0 | 7.7 | 0.0 | 0.2 | 2.7 | 3.5 | 3.4 | 2.4 | 2.7 | 0.7 | 0.6 | 2.4 | 0.0 |
| Curator of the Sands (Kenny Tran, 34th R | 180 | 52 | 7.4 | 13.9 | 15.3 | 8.3 | 7.7 | 0.0 | 1.0 | 3.5 | 0.0 | 0.3 | 0.3 | 2.5 | 0.6 | 0.7 | 0.0 | 0.0 | 0.0 | 0.0 | 6.0 | 15.8 | 0.0 | 9.2 | 0.1 | 0.1 | 1.8 | 2.6 | 4.2 | 2.4 | 3.8 | 0.0 | 0.7 | 0.0 | 1.1 |
| Gloomist (vince, 9th Convergence IV) | 170 | 68 | 7.5 | 15.2 | 12.4 | 8.6 | 2.0 | 3.0 | 1.0 | 4.6 | 0.3 | 1.7 | 1.0 | 1.6 | 0.5 | 0.5 | 0.0 | 5.2 | 3.9 | 0.2 | 2.2 | 12.1 | 0.7 | 10.2 | 0.9 | 0.2 | 2.5 | 3.6 | 5.0 | 2.6 | 4.6 | 2.0 | 0.2 | 2.0 | 0.1 |
| Irelia, Blade Dancer (Arito, 2nd Converg | 170 | 29 | 7.9 | 16.2 | 11.7 | 6.4 | 6.6 | 2.4 | 1.0 | 2.3 | 0.0 | 0.4 | 0.4 | 2.0 | 0.5 | 0.7 | 0.0 | 5.0 | 5.0 | 0.0 | 8.6 | 17.5 | 0.4 | 9.0 | 0.7 | 0.8 | 2.9 | 3.7 | 2.7 | 2.5 | 3.2 | 0.4 | 0.6 | 2.2 | 0.3 |
| Kai'Sa, Daughter of the Void (Dan Bridge | 180 | 57 | 8.0 | 14.4 | 12.3 | 9.5 | 5.5 | 0.4 | 1.0 | 3.8 | 0.0 | 0.4 | 0.4 | 1.4 | 0.6 | 0.5 | 0.0 | 4.2 | 0.0 | 0.0 | 8.0 | 9.6 | 0.0 | 9.9 | 0.1 | 0.2 | 2.0 | 3.1 | 4.5 | 2.8 | 4.1 | 0.0 | 0.1 | 0.0 | 0.0 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | 170 | 55 | 7.3 | 14.6 | 9.9 | 7.0 | 5.9 | 0.7 | 1.0 | 4.0 | 0.7 | 0.2 | 0.2 | 1.3 | 0.5 | 0.4 | 0.0 | 0.0 | 0.0 | 0.0 | 7.6 | 9.8 | 0.6 | 9.3 | 0.3 | 0.0 | 2.2 | 2.9 | 4.7 | 2.2 | 4.6 | 0.0 | 0.4 | 0.8 | 2.9 |
| Riven, The Exile (MERC Koopastar, 1st Co | 180 | 71 | 7.6 | 14.6 | 11.8 | 9.1 | 3.5 | 1.7 | 1.0 | 4.3 | 0.0 | 0.9 | 0.6 | 1.8 | 0.5 | 0.4 | 0.0 | 2.1 | 0.9 | 0.0 | 5.4 | 15.2 | 5.7 | 13.5 | 0.6 | 0.4 | 2.3 | 4.3 | 4.9 | 3.4 | 4.0 | 0.2 | 0.4 | 1.5 | 0.4 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | 180 | 49 | 8.0 | 16.3 | 11.7 | 7.1 | 4.8 | 2.2 | 1.0 | 2.9 | 0.0 | 0.8 | 0.8 | 1.9 | 0.4 | 0.4 | 0.0 | 5.7 | 3.4 | 0.7 | 8.2 | 10.7 | 0.9 | 9.8 | 0.0 | 1.0 | 2.3 | 3.6 | 5.0 | 2.5 | 3.9 | 0.7 | 0.3 | 1.7 | 0.0 |
| Viktor, Herald of the Arcane (Calvin Jin | 180 | 32 | 8.1 | 16.2 | 14.3 | 3.4 | 9.7 | 2.8 | 1.0 | 1.1 | 0.0 | 1.4 | 1.1 | 1.1 | 0.8 | 1.7 | 0.0 | 8.7 | 1.4 | 0.0 | 7.7 | 12.3 | 0.0 | 14.3 | 0.1 | 0.2 | 3.1 | 5.3 | 4.5 | 3.3 | 2.8 | 0.5 | 0.2 | 0.5 | 0.0 |
| Void Burrower (funnyanger, 18th Converge | 180 | 64 | 7.6 | 14.7 | 9.2 | 10.5 | 1.9 | 1.4 | 1.0 | 6.4 | 1.1 | 0.0 | 0.0 | 1.1 | 0.1 | 0.3 | 0.0 | 0.0 | 0.0 | 0.0 | 2.7 | 11.5 | 0.0 | 10.5 | 0.0 | 0.2 | 2.7 | 5.6 | 5.6 | 2.9 | 4.3 | 0.0 | 0.0 | 0.0 | 0.0 |

Average turns 16.5; longest chain 8; games without a winner 0; first player won 528/880.

## Matchups (row vs column: win%, games, 95% interval)

| deck | opponent | win% | games | 95% interval |
|---|---|---|---|---|
| Azir, Emperor of the Sands (Andrew L McD | Curator of the Sands (Kenny Tran, 34th R | 20 | 20 | 8-42 |
| Azir, Emperor of the Sands (Andrew L McD | Gloomist (vince, 9th Convergence IV) | 10 | 10 | 2-40 |
| Azir, Emperor of the Sands (Andrew L McD | Irelia, Blade Dancer (Arito, 2nd Converg | 40 | 20 | 22-61 |
| Azir, Emperor of the Sands (Andrew L McD | Kai'Sa, Daughter of the Void (Dan Bridge | 15 | 20 | 5-36 |
| Azir, Emperor of the Sands (Andrew L McD | Master Yi, Wuju Bladesman (Derpinox, 24t | 30 | 20 | 15-52 |
| Azir, Emperor of the Sands (Andrew L McD | Riven, The Exile (MERC Koopastar, 1st Co | 5 | 20 | 1-24 |
| Azir, Emperor of the Sands (Andrew L McD | Rogue Assassin (Alex Gorica, 2nd Riftbou | 10 | 20 | 3-30 |
| Azir, Emperor of the Sands (Andrew L McD | Viktor, Herald of the Arcane (Calvin Jin | 35 | 20 | 18-57 |
| Azir, Emperor of the Sands (Andrew L McD | Void Burrower (funnyanger, 18th Converge | 15 | 20 | 5-36 |
| Curator of the Sands (Kenny Tran, 34th R | Gloomist (vince, 9th Convergence IV) | 50 | 20 | 30-70 |
| Curator of the Sands (Kenny Tran, 34th R | Irelia, Blade Dancer (Arito, 2nd Converg | 70 | 20 | 48-85 |
| Curator of the Sands (Kenny Tran, 34th R | Kai'Sa, Daughter of the Void (Dan Bridge | 45 | 20 | 26-66 |
| Curator of the Sands (Kenny Tran, 34th R | Master Yi, Wuju Bladesman (Derpinox, 24t | 40 | 20 | 22-61 |
| Curator of the Sands (Kenny Tran, 34th R | Riven, The Exile (MERC Koopastar, 1st Co | 35 | 20 | 18-57 |
| Curator of the Sands (Kenny Tran, 34th R | Rogue Assassin (Alex Gorica, 2nd Riftbou | 55 | 20 | 34-74 |
| Curator of the Sands (Kenny Tran, 34th R | Viktor, Herald of the Arcane (Calvin Jin | 55 | 20 | 34-74 |
| Curator of the Sands (Kenny Tran, 34th R | Void Burrower (funnyanger, 18th Converge | 40 | 20 | 22-61 |
| Gloomist (vince, 9th Convergence IV) | Irelia, Blade Dancer (Arito, 2nd Converg | 85 | 20 | 64-95 |
| Gloomist (vince, 9th Convergence IV) | Kai'Sa, Daughter of the Void (Dan Bridge | 50 | 20 | 30-70 |
| Gloomist (vince, 9th Convergence IV) | Master Yi, Wuju Bladesman (Derpinox, 24t | 80 | 20 | 58-92 |
| Gloomist (vince, 9th Convergence IV) | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 20 | 22-61 |
| Gloomist (vince, 9th Convergence IV) | Rogue Assassin (Alex Gorica, 2nd Riftbou | 65 | 20 | 43-82 |
| Gloomist (vince, 9th Convergence IV) | Viktor, Herald of the Arcane (Calvin Jin | 90 | 20 | 70-97 |
| Gloomist (vince, 9th Convergence IV) | Void Burrower (funnyanger, 18th Converge | 75 | 20 | 53-89 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Kai'Sa, Daughter of the Void (Dan Bridge | 30 | 20 | 15-52 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Master Yi, Wuju Bladesman (Derpinox, 24t | 0 | 10 | -0-28 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Riven, The Exile (MERC Koopastar, 1st Co | 20 | 20 | 8-42 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Rogue Assassin (Alex Gorica, 2nd Riftbou | 35 | 20 | 18-57 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Viktor, Herald of the Arcane (Calvin Jin | 50 | 20 | 30-70 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Void Burrower (funnyanger, 18th Converge | 10 | 20 | 3-30 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Master Yi, Wuju Bladesman (Derpinox, 24t | 50 | 20 | 30-70 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 20 | 22-61 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Rogue Assassin (Alex Gorica, 2nd Riftbou | 55 | 20 | 34-74 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Viktor, Herald of the Arcane (Calvin Jin | 75 | 20 | 53-89 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Void Burrower (funnyanger, 18th Converge | 35 | 20 | 18-57 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 20 | 22-61 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Rogue Assassin (Alex Gorica, 2nd Riftbou | 55 | 20 | 34-74 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Viktor, Herald of the Arcane (Calvin Jin | 75 | 20 | 53-89 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Void Burrower (funnyanger, 18th Converge | 45 | 20 | 26-66 |
| Riven, The Exile (MERC Koopastar, 1st Co | Rogue Assassin (Alex Gorica, 2nd Riftbou | 85 | 20 | 64-95 |
| Riven, The Exile (MERC Koopastar, 1st Co | Viktor, Herald of the Arcane (Calvin Jin | 80 | 20 | 58-92 |
| Riven, The Exile (MERC Koopastar, 1st Co | Void Burrower (funnyanger, 18th Converge | 50 | 20 | 30-70 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Viktor, Herald of the Arcane (Calvin Jin | 65 | 20 | 43-82 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Void Burrower (funnyanger, 18th Converge | 35 | 20 | 18-57 |
| Viktor, Herald of the Arcane (Calvin Jin | Void Burrower (funnyanger, 18th Converge | 15 | 20 | 5-36 |
