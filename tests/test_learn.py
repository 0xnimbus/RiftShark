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
