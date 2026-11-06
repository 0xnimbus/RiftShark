# Gameplay audit (900 games, policy expert)

## Rule invariant problems

None found.

## Mechanics used (per game average)

| deck | games | win% | turns | runes_channeled | draw | play_unit | play_spell | play_gear | play_champion | unit_played_to_battlefield | ambush | hide | play_from_facedown | reaction_on_chain | play_in_showdown | play_in_combat | play_on_opponents_turn | activate | equip | empower | targeting | triggers | replacements | move_standard | ganking_move | move_by_effect | combat | attacker | defender | conquer | hold | stun | counter | recall | xp_events |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Azir, Emperor of the Sands (Andrew L McD | 180 | 26 | 8.7 | 17.9 | 12.4 | 3.2 | 4.6 | 6.3 | 1.0 | 0.9 | 0.1 | 1.1 | 0.9 | 1.8 | 0.4 | 0.8 | 0.0 | 15.1 | 12.5 | 0.0 | 4.1 | 8.5 | 0.0 | 7.7 | 0.0 | 0.2 | 2.7 | 3.6 | 3.5 | 2.5 | 2.8 | 0.7 | 0.6 | 2.3 | 0.0 |
| Curator of the Sands (Kenny Tran, 34th R | 180 | 50 | 7.4 | 14.0 | 15.3 | 8.3 | 7.7 | 0.0 | 1.0 | 3.6 | 0.0 | 0.3 | 0.3 | 2.6 | 0.6 | 0.7 | 0.0 | 0.0 | 0.0 | 0.0 | 6.0 | 15.8 | 0.0 | 9.4 | 0.1 | 0.1 | 1.8 | 2.5 | 4.1 | 2.4 | 3.8 | 0.0 | 0.7 | 0.0 | 1.1 |
| Gloomist (vince, 9th Convergence IV) | 180 | 72 | 7.4 | 15.2 | 12.3 | 8.3 | 2.9 | 2.8 | 1.0 | 4.7 | 0.3 | 1.7 | 1.6 | 2.0 | 0.6 | 0.8 | 0.0 | 4.6 | 3.4 | 0.2 | 3.0 | 12.5 | 0.7 | 9.9 | 0.9 | 0.2 | 2.3 | 3.2 | 5.6 | 2.5 | 4.7 | 2.2 | 0.2 | 1.9 | 0.2 |
| Irelia, Blade Dancer (Arito, 2nd Converg | 180 | 32 | 7.7 | 15.8 | 11.6 | 6.3 | 6.4 | 2.4 | 1.0 | 2.4 | 0.0 | 0.4 | 0.4 | 1.9 | 0.5 | 0.8 | 0.0 | 4.9 | 4.9 | 0.0 | 8.3 | 17.2 | 0.3 | 9.0 | 0.7 | 0.8 | 2.9 | 3.8 | 2.6 | 2.4 | 3.2 | 0.4 | 0.6 | 2.2 | 0.3 |
| Kai'Sa, Daughter of the Void (Dan Bridge | 180 | 56 | 7.9 | 14.4 | 12.2 | 9.4 | 5.4 | 0.4 | 1.0 | 3.7 | 0.0 | 0.4 | 0.4 | 1.4 | 0.6 | 0.5 | 0.0 | 4.2 | 0.0 | 0.0 | 7.9 | 9.5 | 0.0 | 9.8 | 0.1 | 0.2 | 2.1 | 3.2 | 4.3 | 2.8 | 4.0 | 0.0 | 0.2 | 0.0 | 0.0 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | 180 | 56 | 7.3 | 14.6 | 9.8 | 6.9 | 5.8 | 0.7 | 1.0 | 3.9 | 0.7 | 0.3 | 0.3 | 1.4 | 0.5 | 0.4 | 0.0 | 0.0 | 0.0 | 0.0 | 7.5 | 9.7 | 0.6 | 9.3 | 0.3 | 0.1 | 2.2 | 2.9 | 4.6 | 2.3 | 4.6 | 0.0 | 0.4 | 0.9 | 2.8 |
| Riven, The Exile (MERC Koopastar, 1st Co | 180 | 65 | 7.5 | 14.8 | 11.9 | 9.1 | 3.9 | 1.7 | 1.0 | 4.2 | 0.0 | 0.8 | 0.7 | 1.9 | 0.5 | 0.5 | 0.0 | 2.1 | 0.8 | 0.0 | 5.8 | 15.3 | 5.6 | 13.8 | 0.6 | 0.3 | 2.3 | 4.2 | 4.9 | 3.4 | 3.9 | 0.2 | 0.4 | 1.5 | 0.4 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | 180 | 47 | 8.1 | 16.4 | 11.7 | 7.2 | 4.9 | 2.3 | 1.0 | 3.0 | 0.0 | 0.9 | 0.8 | 2.0 | 0.4 | 0.4 | 0.0 | 5.9 | 3.6 | 0.7 | 8.3 | 10.8 | 1.0 | 10.1 | 0.0 | 1.0 | 2.3 | 3.7 | 4.9 | 2.5 | 3.9 | 0.7 | 0.3 | 1.8 | 0.0 |
| Viktor, Herald of the Arcane (Calvin Jin | 180 | 32 | 8.0 | 16.1 | 14.3 | 3.4 | 9.7 | 2.8 | 1.0 | 1.1 | 0.0 | 1.4 | 1.1 | 1.0 | 0.8 | 1.7 | 0.0 | 8.6 | 1.4 | 0.0 | 7.7 | 12.2 | 0.0 | 14.2 | 0.1 | 0.2 | 3.1 | 5.5 | 4.3 | 3.3 | 2.7 | 0.5 | 0.2 | 0.5 | 0.0 |
| Void Burrower (funnyanger, 18th Converge | 180 | 66 | 7.6 | 14.8 | 9.2 | 10.5 | 1.9 | 1.4 | 1.0 | 6.3 | 1.1 | 0.0 | 0.0 | 1.1 | 0.1 | 0.4 | 0.0 | 0.0 | 0.0 | 0.0 | 2.7 | 11.6 | 0.0 | 10.4 | 0.0 | 0.2 | 2.7 | 5.6 | 5.6 | 3.0 | 4.2 | 0.0 | 0.1 | 0.0 | 0.0 |

Average turns 16.4; longest chain 9; games without a winner 0; first player won 540/900.

## Matchups (row vs column: win%, games, 95% interval)

| deck | opponent | win% | games | 95% interval |
|---|---|---|---|---|
| Azir, Emperor of the Sands (Andrew L McD | Curator of the Sands (Kenny Tran, 34th R | 20 | 20 | 8-42 |
| Azir, Emperor of the Sands (Andrew L McD | Gloomist (vince, 9th Convergence IV) | 10 | 20 | 3-30 |
| Azir, Emperor of the Sands (Andrew L McD | Irelia, Blade Dancer (Arito, 2nd Converg | 50 | 20 | 30-70 |
| Azir, Emperor of the Sands (Andrew L McD | Kai'Sa, Daughter of the Void (Dan Bridge | 15 | 20 | 5-36 |
| Azir, Emperor of the Sands (Andrew L McD | Master Yi, Wuju Bladesman (Derpinox, 24t | 30 | 20 | 15-52 |
| Azir, Emperor of the Sands (Andrew L McD | Riven, The Exile (MERC Koopastar, 1st Co | 35 | 20 | 18-57 |
| Azir, Emperor of the Sands (Andrew L McD | Rogue Assassin (Alex Gorica, 2nd Riftbou | 20 | 20 | 8-42 |
| Azir, Emperor of the Sands (Andrew L McD | Viktor, Herald of the Arcane (Calvin Jin | 35 | 20 | 18-57 |
| Azir, Emperor of the Sands (Andrew L McD | Void Burrower (funnyanger, 18th Converge | 15 | 20 | 5-36 |
| Curator of the Sands (Kenny Tran, 34th R | Gloomist (vince, 9th Convergence IV) | 45 | 20 | 26-66 |
| Curator of the Sands (Kenny Tran, 34th R | Irelia, Blade Dancer (Arito, 2nd Converg | 70 | 20 | 48-85 |
| Curator of the Sands (Kenny Tran, 34th R | Kai'Sa, Daughter of the Void (Dan Bridge | 45 | 20 | 26-66 |
| Curator of the Sands (Kenny Tran, 34th R | Master Yi, Wuju Bladesman (Derpinox, 24t | 40 | 20 | 22-61 |
| Curator of the Sands (Kenny Tran, 34th R | Riven, The Exile (MERC Koopastar, 1st Co | 25 | 20 | 11-47 |
| Curator of the Sands (Kenny Tran, 34th R | Rogue Assassin (Alex Gorica, 2nd Riftbou | 50 | 20 | 30-70 |
| Curator of the Sands (Kenny Tran, 34th R | Viktor, Herald of the Arcane (Calvin Jin | 55 | 20 | 34-74 |
| Curator of the Sands (Kenny Tran, 34th R | Void Burrower (funnyanger, 18th Converge | 40 | 20 | 22-61 |
| Gloomist (vince, 9th Convergence IV) | Irelia, Blade Dancer (Arito, 2nd Converg | 80 | 20 | 58-92 |
| Gloomist (vince, 9th Convergence IV) | Kai'Sa, Daughter of the Void (Dan Bridge | 55 | 20 | 34-74 |
| Gloomist (vince, 9th Convergence IV) | Master Yi, Wuju Bladesman (Derpinox, 24t | 85 | 20 | 64-95 |
| Gloomist (vince, 9th Convergence IV) | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 20 | 22-61 |
| Gloomist (vince, 9th Convergence IV) | Rogue Assassin (Alex Gorica, 2nd Riftbou | 85 | 20 | 64-95 |
| Gloomist (vince, 9th Convergence IV) | Viktor, Herald of the Arcane (Calvin Jin | 85 | 20 | 64-95 |
| Gloomist (vince, 9th Convergence IV) | Void Burrower (funnyanger, 18th Converge | 70 | 20 | 48-85 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Kai'Sa, Daughter of the Void (Dan Bridge | 25 | 20 | 11-47 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Master Yi, Wuju Bladesman (Derpinox, 24t | 25 | 20 | 11-47 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Riven, The Exile (MERC Koopastar, 1st Co | 35 | 20 | 18-57 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Rogue Assassin (Alex Gorica, 2nd Riftbou | 35 | 20 | 18-57 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Viktor, Herald of the Arcane (Calvin Jin | 55 | 20 | 34-74 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Void Burrower (funnyanger, 18th Converge | 10 | 20 | 3-30 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Master Yi, Wuju Bladesman (Derpinox, 24t | 50 | 20 | 30-70 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Riven, The Exile (MERC Koopastar, 1st Co | 30 | 20 | 15-52 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Rogue Assassin (Alex Gorica, 2nd Riftbou | 55 | 20 | 34-74 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Viktor, Herald of the Arcane (Calvin Jin | 75 | 20 | 53-89 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Void Burrower (funnyanger, 18th Converge | 35 | 20 | 18-57 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Riven, The Exile (MERC Koopastar, 1st Co | 55 | 20 | 34-74 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Rogue Assassin (Alex Gorica, 2nd Riftbou | 55 | 20 | 34-74 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Viktor, Herald of the Arcane (Calvin Jin | 75 | 20 | 53-89 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Void Burrower (funnyanger, 18th Converge | 45 | 20 | 26-66 |
| Riven, The Exile (MERC Koopastar, 1st Co | Rogue Assassin (Alex Gorica, 2nd Riftbou | 75 | 20 | 53-89 |
| Riven, The Exile (MERC Koopastar, 1st Co | Viktor, Herald of the Arcane (Calvin Jin | 85 | 20 | 64-95 |
| Riven, The Exile (MERC Koopastar, 1st Co | Void Burrower (funnyanger, 18th Converge | 45 | 20 | 26-66 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Viktor, Herald of the Arcane (Calvin Jin | 65 | 20 | 43-82 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Void Burrower (funnyanger, 18th Converge | 35 | 20 | 18-57 |
| Viktor, Herald of the Arcane (Calvin Jin | Void Burrower (funnyanger, 18th Converge | 15 | 20 | 5-36 |
