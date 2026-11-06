import json
from pathlib import Path

import pytest

from riftsim import engine, replay, runner
from riftsim.cards import Registry
from riftsim.policies import GreedyPolicy, MCTSPolicy, RandomPolicy

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "data/cards/demo_set.json"
DECKS = [str(ROOT / "data/decks/fury_aggro.json"), str(ROOT / "data/decks/mind_control.json")]


@pytest.fixture
def reg():
    return Registry().load_set(CARDS)


def play(reg, pol0, pol1, seed):
    decks = [reg.load_deck(p) for p in DECKS]
    s = engine.new_game(reg, decks[0], decks[1], seed=seed)
    while not s.done:
        a = pol0(s) if s.active == 0 else pol1(s)
        assert a in engine.legal_actions(s)
        engine.apply(s, a)
    return s


def test_decks_are_legal(reg):
    for p in DECKS:
        d = reg.load_deck(p)
        assert len(d.main) == 40 and len(d.runes) == 12


def test_random_games_finish(reg):
    for seed in range(20):
        s = play(reg, RandomPolicy(seed), RandomPolicy(seed + 1), seed)
        assert s.done
        assert s.winner is None or s.players[s.winner].points >= s.config["victory_points"]


def test_greedy_beats_random(reg):
    wins = sum(play(reg, GreedyPolicy(i), RandomPolicy(i), i).winner == 0 for i in range(10))
    assert wins >= 7


def test_mcts_runs(reg):
    s = play(reg, MCTSPolicy(0, iterations=20, rollout_depth=4), GreedyPolicy(1), 3)
    assert s.done


def test_illegal_actions_raise(reg):
    decks = [reg.load_deck(p) for p in DECKS]
    s = engine.new_game(reg, decks[0], decks[1], seed=1)
    with pytest.raises(engine.IllegalAction):
        engine.apply(s, ("play", 9999, None, False))
    with pytest.raises(engine.IllegalAction):
        engine.apply(s, ("move", (9999,), 0))


def test_deterministic_and_replay_verifies(reg, tmp_path):
    r = runner.play_one(str(CARDS), DECKS, 7, ["greedy", "random"], replay_dir=tmp_path)
    rep = replay.load(r["replay"])
    ok, msg = replay.verify(rep, reg, str(CARDS))
    assert ok, msg
    # Tamper with the replay: an action that is not legal must be caught.
    rep["actions"].insert(0, ["move", [1], 0])
    ok, msg = replay.verify(rep, reg, str(CARDS))
    assert not ok and "not legal" in msg
    # Transcript renders.
    txt = replay.transcript(replay.load(r["replay"]), reg, str(CARDS))
    assert "WINS" in txt or "draw" in txt.lower()


def test_batch_parallel(tmp_path):
    summary = runner.run_batch(str(CARDS), DECKS, ["greedy", "greedy"], games=8, workers=2, replay_dir=tmp_path)
    assert summary["games"] == 8
    assert abs(sum(summary["win_rate"].values()) - (1 - summary["draws"] / 8)) < 1e-6
    assert len(list(tmp_path.glob("*.json"))) == 8
