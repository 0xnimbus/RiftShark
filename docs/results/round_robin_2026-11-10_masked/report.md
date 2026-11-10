# Gameplay audit (550 games, policy learned:models/cand_mhb.json)

## Rule invariant problems

None found.

## Mechanics used (per game average)

| deck | games | win% | turns | runes_channeled | draw | play_unit | play_spell | play_gear | play_champion | unit_played_to_battlefield | ambush | hide | play_from_facedown | reaction_on_chain | play_in_showdown | play_in_combat | play_on_opponents_turn | activate | equip | empower | targeting | triggers | replacements | move_standard | ganking_move | move_by_effect | combat | attacker | defender | conquer | hold | stun | counter | recall | xp_events |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Azir, Emperor of the Sands (Giovanni, 30 | 100 | 46 | 7.0 | 14.7 | 8.7 | 1.4 | 4.5 | 5.1 | 1.0 | 0.3 | 0.0 | 0.2 | 0.1 | 1.6 | 0.1 | 0.8 | 0.0 | 10.3 | 6.8 | 0.0 | 4.0 | 12.0 | 0.0 | 6.7 | 0.0 | 0.6 | 2.7 | 4.9 | 4.0 | 4.1 | 2.6 | 0.2 | 0.5 | 3.0 | 0.0 |
| Curator of the Sands (Kenny Tran, 34th R | 100 | 52 | 6.9 | 13.5 | 15.8 | 7.7 | 8.2 | 0.0 | 1.0 | 1.2 | 0.0 | 0.1 | 0.1 | 4.2 | 0.7 | 1.4 | 0.0 | 0.0 | 0.0 | 0.0 | 6.6 | 14.6 | 0.0 | 5.5 | 0.0 | 0.2 | 2.6 | 3.2 | 2.8 | 3.8 | 2.7 | 0.0 | 0.7 | 0.0 | 0.7 |
| Gloomist (vince, 9th Convergence IV) | 100 | 49 | 6.6 | 13.8 | 10.3 | 6.8 | 2.6 | 2.7 | 1.0 | 1.1 | 0.2 | 1.1 | 0.7 | 1.8 | 0.2 | 1.2 | 0.0 | 2.9 | 1.9 | 0.1 | 3.4 | 10.3 | 0.6 | 5.4 | 0.6 | 0.2 | 3.0 | 4.1 | 3.3 | 3.6 | 2.7 | 2.5 | 0.4 | 1.8 | 0.2 |
| Heart of the Tempest (Tilted2211, 1st Ra | 100 | 47 | 6.7 | 14.0 | 12.2 | 9.1 | 5.0 | 1.6 | 0.9 | 1.4 | 0.0 | 0.7 | 0.6 | 1.3 | 0.3 | 0.9 | 0.0 | 6.2 | 0.6 | 2.3 | 6.4 | 15.2 | 0.0 | 6.0 | 0.2 | 1.2 | 2.8 | 3.8 | 3.8 | 4.4 | 2.1 | 0.7 | 0.5 | 0.8 | 0.0 |
| Irelia, Blade Dancer (Arito, 2nd Converg | 100 | 32 | 6.5 | 13.7 | 9.9 | 5.4 | 5.2 | 2.0 | 1.0 | 0.2 | 0.0 | 0.4 | 0.3 | 3.1 | 0.3 | 1.1 | 0.0 | 2.4 | 2.4 | 0.0 | 7.9 | 17.1 | 0.4 | 5.1 | 0.5 | 1.3 | 2.5 | 3.1 | 2.9 | 3.7 | 2.3 | 0.5 | 0.4 | 1.6 | 0.2 |
| Kai'Sa, Daughter of the Void (Dan Bridge | 100 | 66 | 7.4 | 14.8 | 12.6 | 8.3 | 4.6 | 0.4 | 1.0 | 1.1 | 0.0 | 0.2 | 0.1 | 1.2 | 0.3 | 0.9 | 0.0 | 3.4 | 0.0 | 0.0 | 7.2 | 10.0 | 0.0 | 6.3 | 0.0 | 0.2 | 2.5 | 3.3 | 2.9 | 4.3 | 3.0 | 0.0 | 0.5 | 0.1 | 0.0 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | 100 | 59 | 6.5 | 13.2 | 9.4 | 6.9 | 4.8 | 0.6 | 1.0 | 1.2 | 0.9 | 0.2 | 0.1 | 2.2 | 0.3 | 1.5 | 0.0 | 0.0 | 0.0 | 0.0 | 6.8 | 9.4 | 0.5 | 5.5 | 0.3 | 0.2 | 2.7 | 3.8 | 3.1 | 4.0 | 3.2 | 0.0 | 0.4 | 0.6 | 2.5 |
| Riven, The Exile (MERC Koopastar, 1st Co | 100 | 51 | 6.8 | 13.6 | 10.9 | 8.1 | 3.6 | 1.4 | 1.0 | 4.3 | 0.0 | 0.4 | 0.3 | 2.2 | 0.3 | 0.7 | 0.0 | 0.6 | 0.2 | 0.0 | 5.3 | 14.2 | 6.3 | 8.8 | 0.2 | 1.8 | 2.8 | 4.0 | 4.2 | 4.3 | 2.6 | 0.0 | 0.3 | 1.3 | 0.2 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | 100 | 44 | 7.3 | 15.0 | 10.9 | 7.0 | 3.3 | 2.2 | 1.0 | 1.0 | 0.0 | 0.6 | 0.5 | 2.2 | 0.2 | 0.9 | 0.0 | 3.1 | 1.2 | 0.6 | 5.8 | 8.9 | 0.9 | 6.0 | 0.0 | 0.5 | 2.8 | 3.5 | 4.0 | 4.0 | 2.8 | 0.4 | 0.3 | 1.9 | 0.0 |
| Viktor, Herald of the Arcane (Calvin Jin | 100 | 43 | 6.5 | 13.5 | 10.2 | 2.1 | 6.9 | 2.4 | 0.7 | 0.1 | 0.0 | 0.2 | 0.0 | 0.8 | 0.6 | 1.3 | 0.0 | 5.2 | 0.2 | 0.0 | 5.8 | 12.7 | 0.0 | 9.3 | 0.0 | 0.2 | 2.9 | 4.7 | 3.1 | 5.9 | 0.8 | 0.4 | 0.6 | 0.2 | 0.0 |
| Void Burrower (MICE Ramekiano, 1st Radia | 100 | 61 | 6.5 | 13.2 | 7.1 | 10.7 | 2.3 | 0.0 | 1.0 | 1.3 | 0.7 | 0.0 | 0.0 | 0.3 | 0.4 | 1.2 | 0.0 | 0.0 | 0.0 | 0.0 | 3.8 | 12.3 | 0.3 | 10.1 | 0.0 | 0.3 | 3.5 | 6.7 | 4.0 | 5.6 | 1.8 | 0.0 | 0.2 | 0.1 | 0.0 |

Average turns 14.2; longest chain 15; games without a winner 0; first player won 317/550.

## Matchups (row vs column: win%, games, 95% interval)

| deck | opponent | win% | games | 95% interval |
|---|---|---|---|---|
| Azir, Emperor of the Sands (Giovanni, 30 | Curator of the Sands (Kenny Tran, 34th R | 60 | 10 | 31-83 |
| Azir, Emperor of the Sands (Giovanni, 30 | Gloomist (vince, 9th Convergence IV) | 40 | 10 | 17-69 |
| Azir, Emperor of the Sands (Giovanni, 30 | Heart of the Tempest (Tilted2211, 1st Ra | 30 | 10 | 11-60 |
| Azir, Emperor of the Sands (Giovanni, 30 | Irelia, Blade Dancer (Arito, 2nd Converg | 60 | 10 | 31-83 |
| Azir, Emperor of the Sands (Giovanni, 30 | Kai'Sa, Daughter of the Void (Dan Bridge | 20 | 10 | 6-51 |
| Azir, Emperor of the Sands (Giovanni, 30 | Master Yi, Wuju Bladesman (Derpinox, 24t | 70 | 10 | 40-89 |
| Azir, Emperor of the Sands (Giovanni, 30 | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 10 | 17-69 |
| Azir, Emperor of the Sands (Giovanni, 30 | Rogue Assassin (Alex Gorica, 2nd Riftbou | 40 | 10 | 17-69 |
| Azir, Emperor of the Sands (Giovanni, 30 | Viktor, Herald of the Arcane (Calvin Jin | 40 | 10 | 17-69 |
| Azir, Emperor of the Sands (Giovanni, 30 | Void Burrower (MICE Ramekiano, 1st Radia | 60 | 10 | 31-83 |
| Curator of the Sands (Kenny Tran, 34th R | Gloomist (vince, 9th Convergence IV) | 30 | 10 | 11-60 |
| Curator of the Sands (Kenny Tran, 34th R | Heart of the Tempest (Tilted2211, 1st Ra | 80 | 10 | 49-94 |
| Curator of the Sands (Kenny Tran, 34th R | Irelia, Blade Dancer (Arito, 2nd Converg | 80 | 10 | 49-94 |
| Curator of the Sands (Kenny Tran, 34th R | Kai'Sa, Daughter of the Void (Dan Bridge | 50 | 10 | 24-76 |
| Curator of the Sands (Kenny Tran, 34th R | Master Yi, Wuju Bladesman (Derpinox, 24t | 60 | 10 | 31-83 |
| Curator of the Sands (Kenny Tran, 34th R | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 10 | 17-69 |
| Curator of the Sands (Kenny Tran, 34th R | Rogue Assassin (Alex Gorica, 2nd Riftbou | 70 | 10 | 40-89 |
| Curator of the Sands (Kenny Tran, 34th R | Viktor, Herald of the Arcane (Calvin Jin | 40 | 10 | 17-69 |
| Curator of the Sands (Kenny Tran, 34th R | Void Burrower (MICE Ramekiano, 1st Radia | 30 | 10 | 11-60 |
| Gloomist (vince, 9th Convergence IV) | Heart of the Tempest (Tilted2211, 1st Ra | 30 | 10 | 11-60 |
| Gloomist (vince, 9th Convergence IV) | Irelia, Blade Dancer (Arito, 2nd Converg | 80 | 10 | 49-94 |
| Gloomist (vince, 9th Convergence IV) | Kai'Sa, Daughter of the Void (Dan Bridge | 40 | 10 | 17-69 |
| Gloomist (vince, 9th Convergence IV) | Master Yi, Wuju Bladesman (Derpinox, 24t | 30 | 10 | 11-60 |
| Gloomist (vince, 9th Convergence IV) | Riven, The Exile (MERC Koopastar, 1st Co | 40 | 10 | 17-69 |
| Gloomist (vince, 9th Convergence IV) | Rogue Assassin (Alex Gorica, 2nd Riftbou | 50 | 10 | 24-76 |
| Gloomist (vince, 9th Convergence IV) | Viktor, Herald of the Arcane (Calvin Jin | 60 | 10 | 31-83 |
| Gloomist (vince, 9th Convergence IV) | Void Burrower (MICE Ramekiano, 1st Radia | 30 | 10 | 11-60 |
| Heart of the Tempest (Tilted2211, 1st Ra | Irelia, Blade Dancer (Arito, 2nd Converg | 50 | 10 | 24-76 |
| Heart of the Tempest (Tilted2211, 1st Ra | Kai'Sa, Daughter of the Void (Dan Bridge | 50 | 10 | 24-76 |
| Heart of the Tempest (Tilted2211, 1st Ra | Master Yi, Wuju Bladesman (Derpinox, 24t | 20 | 10 | 6-51 |
| Heart of the Tempest (Tilted2211, 1st Ra | Riven, The Exile (MERC Koopastar, 1st Co | 50 | 10 | 24-76 |
| Heart of the Tempest (Tilted2211, 1st Ra | Rogue Assassin (Alex Gorica, 2nd Riftbou | 40 | 10 | 17-69 |
| Heart of the Tempest (Tilted2211, 1st Ra | Viktor, Herald of the Arcane (Calvin Jin | 60 | 10 | 31-83 |
| Heart of the Tempest (Tilted2211, 1st Ra | Void Burrower (MICE Ramekiano, 1st Radia | 40 | 10 | 17-69 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Kai'Sa, Daughter of the Void (Dan Bridge | 20 | 10 | 6-51 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Master Yi, Wuju Bladesman (Derpinox, 24t | 40 | 10 | 17-69 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Riven, The Exile (MERC Koopastar, 1st Co | 20 | 10 | 6-51 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Rogue Assassin (Alex Gorica, 2nd Riftbou | 30 | 10 | 11-60 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Viktor, Herald of the Arcane (Calvin Jin | 50 | 10 | 24-76 |
| Irelia, Blade Dancer (Arito, 2nd Converg | Void Burrower (MICE Ramekiano, 1st Radia | 30 | 10 | 11-60 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Master Yi, Wuju Bladesman (Derpinox, 24t | 40 | 10 | 17-69 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Riven, The Exile (MERC Koopastar, 1st Co | 70 | 10 | 40-89 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Rogue Assassin (Alex Gorica, 2nd Riftbou | 80 | 10 | 49-94 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Viktor, Herald of the Arcane (Calvin Jin | 70 | 10 | 40-89 |
| Kai'Sa, Daughter of the Void (Dan Bridge | Void Burrower (MICE Ramekiano, 1st Radia | 80 | 10 | 49-94 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Riven, The Exile (MERC Koopastar, 1st Co | 50 | 10 | 24-76 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Rogue Assassin (Alex Gorica, 2nd Riftbou | 80 | 10 | 49-94 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Viktor, Herald of the Arcane (Calvin Jin | 80 | 10 | 49-94 |
| Master Yi, Wuju Bladesman (Derpinox, 24t | Void Burrower (MICE Ramekiano, 1st Radia | 40 | 10 | 17-69 |
| Riven, The Exile (MERC Koopastar, 1st Co | Rogue Assassin (Alex Gorica, 2nd Riftbou | 40 | 10 | 17-69 |
| Riven, The Exile (MERC Koopastar, 1st Co | Viktor, Herald of the Arcane (Calvin Jin | 70 | 10 | 40-89 |
| Riven, The Exile (MERC Koopastar, 1st Co | Void Burrower (MICE Ramekiano, 1st Radia | 10 | 10 | 2-40 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Viktor, Herald of the Arcane (Calvin Jin | 20 | 10 | 6-51 |
| Rogue Assassin (Alex Gorica, 2nd Riftbou | Void Burrower (MICE Ramekiano, 1st Radia | 50 | 10 | 24-76 |
| Viktor, Herald of the Arcane (Calvin Jin | Void Burrower (MICE Ramekiano, 1st Radia | 20 | 10 | 6-51 |
