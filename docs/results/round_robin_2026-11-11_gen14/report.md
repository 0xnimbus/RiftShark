# Gameplay audit (660 games, policy learned:gen_014)

## Rule invariant problems

None found.

## Mechanics used (per game average)

| deck | games | win% | turns | runes_channeled | draw | play_unit | play_spell | play_gear | play_champion | unit_played_to_battlefield | ambush | hide | play_from_facedown | reaction_on_chain | play_in_showdown | play_in_combat | play_on_opponents_turn | activate | equip | empower | targeting | triggers | replacements | move_standard | ganking_move | move_by_effect | combat | attacker | defender | conquer | hold | stun | counter | recall | xp_events |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Azir, Emperor of the Sands (Giovanni, 30 | 110 | 37 | 7.0 | 14.7 | 8.6 | 1.4 | 4.5 | 5.0 | 1.0 | 0.5 | 0.0 | 0.1 | 0.0 | 1.6 | 0.2 | 0.8 | 0.0 | 10.1 | 6.6 | 0.0 | 3.8 | 10.5 | 0.0 | 5.9 | 0.0 | 0.5 | 2.1 | 4.0 | 4.4 | 3.4 | 2.8 | 0.2 | 0.5 | 2.6 | 0.0 |
| Curator of the Sands (Kenny Tran, 34th R | 110 | 47 | 6.8 | 13.5 | 16.4 | 7.7 | 8.1 | 0.0 | 1.0 | 1.3 | 0.0 | 0.1 | 0.0 | 4.2 | 0.6 | 1.4 | 0.0 | 0.0 | 0.0 | 0.0 | 6.3 | 16.2 | 0.0 | 5.5 | 0.0 | 0.2 | 2.4 | 3.1 | 2.4 | 3.6 | 2.6 | 0.0 | 0.4 | 0.0 | 0.7 |
| Gloomist (vince, 9th Convergence IV) | 110 | 54 | 6.6 | 13.9 | 10.8 | 7.0 | 2.7 | 3.0 | 1.0 | 1.2 | 0.2 | 1.3 | 1.0 | 2.1 | 0.2 | 1.3 | 0.0 | 2.8 | 1.9 | 0.1 | 3.6 | 12.3 | 0.7 | 5.5 | 0.6 | 0.2 | 3.0 | 4.0 | 3.7 | 3.5 | 3.2 | 3.1 | 0.3 | 2.2 | 0.2 |
| Heart of the Tempest (Tilted2211, 1st Ra | 110 | 48 | 6.7 | 13.9 | 12.1 | 9.4 | 4.7 | 1.6 | 1.0 | 1.4 | 0.0 | 0.6 | 0.4 | 1.1 | 0.2 | 0.8 | 0.0 | 5.9 | 0.6 | 2.3 | 5.9 | 14.8 | 0.0 | 6.0 | 0.2 | 1.2 | 2.8 | 3.9 | 3.3 | 4.2 | 2.4 | 0.4 | 0.4 | 0.6 | 0.0 |
| Irelia, Blade Dancer (Arito, 2nd Converg | 110 | 31 | 6.7 | 14.0 | 10.3 | 5.5 | 5.7 | 1.9 | 1.0 | 0.3 | 0.0 | 0.3 | 0.3 | 3.1 | 0.4 | 1.3 | 0.0 | 2.4 | 2.4 | 0.0 | 8.4 | 17.5 | 0.3 | 5.0 | 0.4 | 1.4 | 2.3 | 2.9 | 2.9 | 3.5 | 2.4 | 0.4 | 0.6 | 1.3 | 0.2 |
| Kai'Sa, Daughter of the Void (Dan Bridge | 110 | 64 | 7.1 | 14.1 | 12.1 | 8.0 | 4.4 | 0.4 | 1.0 | 1.1 | 0.0 | 0.2 | 0.0 | 1.3 | 0.4 | 0.9 | 0.0 | 3.2 | 0.0 | 0.0 | 7.0 | 9.0 | 0.0 | 6.0 | 0.0 | 0.2 | 2.5 | 3.3 | 2.9 | 4.1 | 3.0 | 0.0 | 0.4 | 0.0 | 0.0 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | 110 | 54 | 6.5 | 13.2 | 9.5 | 6.6 | 4.9 | 0.7 | 1.0 | 0.8 | 0.6 | 0.1 | 0.1 | 2.3 | 0.5 | 1.1 | 0.0 | 0.0 | 0.0 | 0.0 | 7.0 | 9.4 | 0.6 | 6.1 | 0.3 | 0.3 | 2.7 | 4.0 | 3.0 | 4.1 | 3.0 | 0.0 | 0.3 | 0.7 | 2.7 |
| Riven, The Exile (MERC Koopastar, 1st Co | 110 | 67 | 6.7 | 13.4 | 10.5 | 8.1 | 3.3 | 1.4 | 1.0 | 4.9 | 0.0 | 0.4 | 0.2 | 2.2 | 0.3 | 0.6 | 0.0 | 1.0 | 0.4 | 0.0 | 5.2 | 14.2 | 6.8 | 8.6 | 0.3 | 1.6 | 2.7 | 4.1 | 5.1 | 4.3 | 3.2 | 0.0 | 0.3 | 1.3 | 0.3 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | 110 | 39 | 7.2 | 14.8 | 10.7 | 6.3 | 3.5 | 2.4 | 1.0 | 0.9 | 0.0 | 0.4 | 0.3 | 2.2 | 0.2 | 0.8 | 0.0 | 3.3 | 1.2 | 0.6 | 6.0 | 7.8 | 0.9 | 5.4 | 0.0 | 0.6 | 2.6 | 3.5 | 3.5 | 3.3 | 2.7 | 0.3 | 0.3 | 1.7 | 0.0 |
| Sett, The Boss (HXN Pandanaconda, 10th N | 110 | 52 | 6.7 | 13.8 | 9.2 | 9.2 | 1.9 | 0.9 | 1.0 | 2.5 | 1.2 | 0.0 | 0.0 | 0.6 | 0.1 | 1.1 | 0.0 | 0.0 | 0.0 | 0.0 | 6.3 | 14.4 | 0.4 | 5.4 | 0.1 | 0.7 | 3.0 | 4.7 | 3.4 | 3.6 | 3.2 | 0.3 | 0.3 | 0.6 | 0.0 |
| Viktor, Herald of the Arcane (Calvin Jin | 110 | 44 | 6.3 | 13.0 | 9.6 | 1.9 | 6.7 | 2.3 | 0.7 | 0.1 | 0.0 | 0.2 | 0.0 | 0.8 | 0.5 | 1.4 | 0.0 | 5.0 | 0.3 | 0.0 | 5.7 | 12.8 | 0.0 | 9.5 | 0.0 | 0.3 | 2.6 | 4.5 | 3.0 | 5.8 | 1.0 | 0.3 | 0.5 | 0.1 | 0.0 |
| Void Burrower (MICE Ramekiano, 1st Radia | 110 | 64 | 6.6 | 13.4 | 7.3 | 10.5 | 2.6 | 0.0 | 1.0 | 1.1 | 0.6 | 0.0 | 0.0 | 0.2 | 0.4 | 1.2 | 0.0 | 0.0 | 0.0 | 0.0 | 4.0 | 11.8 | 0.3 | 9.7 | 0.0 | 0.3 | 3.1 | 5.8 | 3.4 | 5.5 | 2.0 | 0.0 | 0.1 | 0.0 | 0.0 |

Average turns 14.1; longest chain 13; games without a winner 0; first player won 378/660.

## Matchups (row vs column: win%, games, 95% interval)

| deck | opponent | win% | games | 95% interval |
|---|---|---|---|---|
| Azir, Emperor of the Sands (Giovanni, 30 | Curator of the Sands (Kenny Tran, 34th R | 50 | 10 | 24-76 |
| Azir, Emperor of the Sands (Giovanni, 30 | Gloomist (vince, 9th Convergence IV) | 30 | 10 | 11-60 |
| Azir, Emperor of the Sands (Giovanni, 30 | Heart of the Tempest (Tilted2211, 1st Ra | 50 | 10 | 24-76 |
| Azir, Emperor of the Sands (Giovanni, 30 | Irelia, Blade Dancer (Arito, 2nd Converg | 50 | 10 | 24-76 |
| Azir, Emperor of the Sands (Giovanni, 30 | Kai'Sa, Daughter of the Void (Dan Bridge | 30 | 10 | 11-60 |
| Azir, Emperor of the Sands (Giovanni, 30 | Master Yi, Wuju Bladesman (Derpinox, 24t | 60 | 10 | 31-83 |
| Azir, Emperor of the Sands (Giovanni, 30 | Riven, The Exile (MERC Koopastar, 1st Co | 20 | 10 | 6-51 |
| Azir, Emperor of the Sands (Giovanni, 30 | Rogue Assassin (Alex Gorica, 2nd Riftbou | 50 | 10 | 24-76 |
| Azir, Emperor of the Sands (Giovanni, 30 | Sett, The Boss (HXN Pandanaconda, 10th N | 40 | 10 | 17-69 |
| Azir, Emperor of the Sands (Giovanni, 30 | Viktor, Herald of the Arcane (Calvin Jin | 20 | 10 | 6-51 |
| Azir, Emperor of the Sands (Giovanni, 30 | Void Burrower (MICE Ramekiano, 1st Radia | 10 | 10 | 2-40 |
| Curator of the Sands (Kenny Tran, 34th R | Gloomist (vince, 9th Convergence IV) | 60 | 10 | 31-83 |
| Curator of the Sands (Kenny Tran, 34th R | Heart of the Tempest (Tilted2211, 1st Ra | 40 | 10 | 17-69 |
| Curator of the Sands (Kenny Tran, 34th R | Irelia, Blade Dancer (Arito, 2nd Converg | 60 | 10 | 31-83 |
| Curator of the Sands (Kenny Tran, 34th R | Kai'Sa, Daughter of the Void (Dan Bridge | 20 | 10 | 6-51 |
| Curator of the Sands (Kenny Tran, 34th R | Master Yi, Wuju Bladesman (Derpinox, 24t | 50 | 10 | 24-76 |
| Curator of the Sands (Kenny Tran, 34th R | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 10 | 17-69 |
| Curator of the Sands (Kenny Tran, 34th R | Rogue Assassin (Alex Gorica, 2nd Riftbou | 80 | 10 | 49-94 |
| Curator of the Sands (Kenny Tran, 34th R | Sett, The Boss (HXN Pandanaconda, 10th N | 50 | 10 | 24-76 |
| Curator of the Sands (Kenny Tran, 34th R | Viktor, Herald of the Arcane (Calvin Jin | 40 | 10 | 17-69 |
| Curator of the Sands (Kenny Tran, 34th R | Void Burrower (MICE Ramekiano, 1st Radia | 30 | 10 | 11-60 |
| Gloomist (vince, 9th Convergence IV) | Heart of the Tempest (Tilted2211, 1st Ra | 40 | 10 | 17-69 |
| Gloomist (vince, 9th Convergence IV) | Irelia, Blade Dancer (Arito, 2nd Converg | 70 | 10 | 40-89 |
| Gloomist (vince, 9th Convergence IV) | Kai'Sa, Daughter of the Void (Dan Bridge | 40 | 10 | 17-69 |
| Gloomist (vince, 9th Convergence IV) | Master Yi, Wuju Bladesman (Derpinox, 24t | 50 | 10 | 24-76 |
| Gloomist (vince, 9th Convergence IV) | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 10 | 17-69 |
| Gloomist (vince, 9th Convergence IV) | Rogue Assassin (Alex Gorica, 2nd Riftbou | 80 | 10 | 49-94 |
| Gloomist (vince, 9th Convergence IV) | Sett, The Boss (HXN Pandanaconda, 10th N | 50 | 10 | 24-76 |
| Gloomist (vince, 9th Convergence IV) | Viktor, Herald of the Arcane (Calvin Jin | 70 | 10 | 40-89 |
| Gloomist (vince, 9th Convergence IV) | Void Burrower (MICE Ramekiano, 1st Radia | 40 | 10 | 17-69 |
| Heart of the Tempest (Tilted2211, 1st Ra | Irelia, Blade Dancer (Arito, 2nd Converg | 80 | 10 | 49-94 |
| Heart of the Tempest (Tilted2211, 1st Ra | Kai'Sa, Daughter of the Void (Dan Bridge | 10 | 10 | 2-40 |
| Heart of the Tempest (Tilted2211, 1st Ra | Master Yi, Wuju Bladesman (Derpinox, 24t | 30 | 10 | 11-60 |
| Heart of the Tempest (Tilted2211, 1st Ra | Riven, The Exile (MERC Koopastar, 1st Co | 30 | 10 | 11-60 |
| Heart of the Tempest (Tilted2211, 1st Ra | Rogue Assassin (Alex Gorica, 2nd Riftbou | 50 | 10 | 24-76 |
| Heart of the Tempest (Tilted2211, 1st Ra | Sett, The Boss (HXN Pandanaconda, 10th N | 50 | 10 | 24-76 |
| Heart of the Tempest (Tilted2211, 1st Ra | Viktor, Herald of the Arcane (Calvin Jin | 60 | 10 | 31-83 |
| Heart of the Tempest (Tilted2211, 1st Ra | Void Burrower (MICE Ramekiano, 1st Radia | 50 | 10 | 24-76 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Kai'Sa, Daughter of the Void (Dan Bridge | 50 | 10 | 24-76 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Master Yi, Wuju Bladesman (Derpinox, 24t | 40 | 10 | 17-69 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Riven, The Exile (MERC Koopastar, 1st Co | 20 | 10 | 6-51 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Rogue Assassin (Alex Gorica, 2nd Riftbou | 30 | 10 | 11-60 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Sett, The Boss (HXN Pandanaconda, 10th N | 30 | 10 | 11-60 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Viktor, Herald of the Arcane (Calvin Jin | 20 | 10 | 6-51 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Void Burrower (MICE Ramekiano, 1st Radia | 10 | 10 | 2-40 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Master Yi, Wuju Bladesman (Derpinox, 24t | 60 | 10 | 31-83 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 10 | 17-69 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Rogue Assassin (Alex Gorica, 2nd Riftbou | 70 | 10 | 40-89 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Sett, The Boss (HXN Pandanaconda, 10th N | 60 | 10 | 31-83 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Viktor, Herald of the Arcane (Calvin Jin | 70 | 10 | 40-89 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Void Burrower (MICE Ramekiano, 1st Radia | 50 | 10 | 24-76 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 10 | 17-69 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Rogue Assassin (Alex Gorica, 2nd Riftbou | 60 | 10 | 31-83 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Sett, The Boss (HXN Pandanaconda, 10th N | 60 | 10 | 31-83 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Viktor, Herald of the Arcane (Calvin Jin | 70 | 10 | 40-89 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Void Burrower (MICE Ramekiano, 1st Radia | 50 | 10 | 24-76 |
| Riven, The Exile (MERC Koopastar, 1st Co | Rogue Assassin (Alex Gorica, 2nd Riftbou | 90 | 10 | 60-98 |
| Riven, The Exile (MERC Koopastar, 1st Co | Sett, The Boss (HXN Pandanaconda, 10th N | 60 | 10 | 31-83 |
| Riven, The Exile (MERC Koopastar, 1st Co | Viktor, Herald of the Arcane (Calvin Jin | 60 | 10 | 31-83 |
| Riven, The Exile (MERC Koopastar, 1st Co | Void Burrower (MICE Ramekiano, 1st Radia | 60 | 10 | 31-83 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Sett, The Boss (HXN Pandanaconda, 10th N | 50 | 10 | 24-76 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Viktor, Herald of the Arcane (Calvin Jin | 60 | 10 | 31-83 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Void Burrower (MICE Ramekiano, 1st Radia | 30 | 10 | 11-60 |
| Sett, The Boss (HXN Pandanaconda, 10th N | Viktor, Herald of the Arcane (Calvin Jin | 70 | 10 | 40-89 |
| Sett, The Boss (HXN Pandanaconda, 10th N | Void Burrower (MICE Ramekiano, 1st Radia | 50 | 10 | 24-76 |
| Viktor, Herald of the Arcane (Calvin Jin | Void Burrower (MICE Ramekiano, 1st Radia | 20 | 10 | 6-51 |
