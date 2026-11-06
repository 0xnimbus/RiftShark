"""Learning from self-play: position features, the value network, and the policy that uses it.

Loop (tools/train_loop.py): self-play with the best AI -> train a value net on (position, final winner) ->
gate the new net against the best AI head to head -> promote it if it wins clearly -> repeat.
"""
