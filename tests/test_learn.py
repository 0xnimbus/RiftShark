"""Learning loop: features use only the deciding player's information, the value net and learned policies work."""
import json
import pathlib
import random
import sys

import pytest

from riftsim.core.cards import CardDB
from riftsim.core.deck import Deck
from riftsim.core.game import Game
from riftsim.core.learn.features import encode, size
from riftsim.core.learn.model import ValueNet
from riftsim.core.policies import GreedyPolicy, determinize, make_policy
from riftsim.core.replay import play_game
from riftsim.core.scripts import script_all

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


@pytest.fixture(scope="module")
def db():
    return script_all(CardDB.load(str(ROOT / "data/cards/riftbound.json")))


@pytest.fixture(scope="module")
def decks(db):
    return [Deck.load(str(ROOT / "data/decks/tournament/kaisa_void.json"), db),
            Deck.load(str(ROOT / "data/decks/tournament/riven_exile.json"), db)]


def _positions(db, decks, n=60, seed=3):
    g = Game(db, decks, seed=seed, log=False)
    pols = [GreedyPolicy(seed=1), GreedyPolicy(seed=2)]
    out = []
    while len(out) < n:
        d = g.run()
        if d is None:
            break
        if d.kind == "action":
            out.append(g.clone())
        g.choose(pols[d.player].choose(g, d))
    return out


def test_features_ignore_hidden_information(db, decks):
    """Resampling everything a player cannot see (opponent hand, decks, facedown cards) never changes their features."""
    rng = random.Random(0)
    for g in _positions(db, decks):
        for p in (0, 1):
            x = encode(g, p)
            assert len(x) == size()
            for _ in range(2):
                assert encode(determinize(g, p, rng), p) == x


def test_value_net_forward_matches_numpy(db, decks):
    np = pytest.importorskip("numpy")
    rs = np.random.RandomState(0)
    n = size()
    d = {"mean": rs.randn(n).tolist(), "std": (rs.rand(n) + 0.5).tolist(), "w1": rs.randn(8, n).tolist(),
         "b1": rs.randn(8).tolist(), "w2": rs.randn(8).tolist(), "b2": 0.3}
    net = ValueNet(d)
    x = rs.randn(n)
    z = (x - np.array(d["mean"])) / np.array(d["std"])
    ref = 1 / (1 + np.exp(-(np.tanh(np.array(d["w1"]) @ z + d["b1"]) @ np.array(d["w2"]) + 0.3)))
    assert abs(net.predict_x(x.tolist()) - ref) < 1e-9


def test_selfplay_train_and_learned_policy(db, decks, tmp_path):
    import train_loop as T
    r = T._selfplay_game(([str(ROOT / "data/decks/tournament/kaisa_void.json"),
                           str(ROOT / "data/decks/tournament/riven_exile.json")], 5, "greedy", 3, 0.0))
    assert r["winner"] in (0, 1) and len(r["x"]) == len(r["y"]) > 0
    np = pytest.importorskip("numpy")
    f = tmp_path / "d.npz"
    np.savez(f, x=np.array(r["x"] * 5, dtype=np.float32), y=np.array(r["y"] * 5, dtype=np.float32),
             game=np.repeat(np.arange(5), len(r["y"])).astype(np.int32))
    info = T.train([str(f)], str(tmp_path / "m.json"), hidden=8, epochs=3)
    assert info["positions"] == 5 * len(r["y"])
    pols = [make_policy(f"learned:{tmp_path / 'm.json'}", seed=1), make_policy("greedy", seed=2)]
    g, _ = play_game(db, decks, 9, pols, record=False, max_turns=60, log=False)
    assert g.over


def test_interaction_features_count_affordable_reactions(db, decks):
    """Version 3 appends held interaction: reaction cards in hand, how many the ready runes pay for, counters among them."""
    from riftsim.core.learn.features import size_v2, size_v3, size_v4
    for g in _positions(db, decks, n=40, seed=5):
        for p in (0, 1):
            ps = g.players[p]
            ready = sum(1 for u in ps.runes if not g.objects[u].exhausted)
            react = [g.objects[u].defn for u in ps.hand if g.objects[u].defn.keywords.get("reaction")]
            x = encode(g, p)
            assert len(x) == size_v4() + 9 and size_v4() == size_v3() + 4 and size_v3() == size_v2() + 3
            v3 = x[:size_v3()]
            assert v3[-3] == len(react) / 3
            assert v3[-2] == sum(1 for d in react if (d.energy or 0) <= ready) / 3


def test_opponent_turn_lets_the_waiting_player_respond(db, decks):
    """In the simulated opponent turn the waiting player may use reactions (held energy has a use there)."""
    from riftsim.core.learn.policy import opponent_turn, to_turn_end
    asked = []

    class Spy:
        def choose(self, g, d):
            asked.append(d.player)
            return ("pass",) if ("pass",) in d.options else d.options[0]

    rng = random.Random(1)
    for g in _positions(db, decks, n=150, seed=7)[20:]:
        if asked:
            break
        d = g.pending
        if d is None or d.player != g.turn_player or ("end_turn",) not in d.options:
            continue
        p = d.player
        h = determinize(g, p, rng)
        h.choose(("end_turn",))
        to_turn_end(h, p, GreedyPolicy(1, samples=1))
        opponent_turn(h, p, GreedyPolicy(2, samples=1), respond=Spy())
    assert asked and all(a in (0, 1) for a in asked)
