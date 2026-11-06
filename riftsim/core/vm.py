"""Effect virtual machine.

Card effects are written as nested trees (see ops.py: If, ForEach, May, Choose, Deal ...) and
compiled to flat instruction lists with jumps. The VM runs one flat program per frame and can
pause on any instruction that needs a player decision. All VM state (frames, pcs, contexts)
lives on the game object, so a paused game can be cloned, saved and resumed. That is what makes
search (MCTS) and replay verification possible on a rules engine with reactions.

Instruction protocol:  instr.run(game, ctx) -> None (advance) | int (jump to pc) | Decision
A Decision carries `out`: when the player decides, the chosen option is stored in ctx.vars[out]
and the pc advances.
"""
from __future__ import annotations


class Decision:
    """A pending player decision. `options` are hashable option values (what a policy chooses
    between); `labels` are human readable strings in the same order (for replays)."""
    __slots__ = ("player", "kind", "options", "labels", "out", "info")

    def __init__(self, player, kind, options, out=None, labels=None, info=None):
        self.player, self.kind, self.options, self.out = player, kind, list(options), out
        self.labels = labels if labels is not None else [str(o) for o in self.options]
        self.info = info or {}

    def __repr__(self):
        return f"Decision(P{self.player} {self.kind}: {len(self.options)} options)"


class Ref:
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"Ref({self.name})"


class Context:
    """Execution context of one chain item (spell, ability, trigger) or inline effect."""
    __slots__ = ("controller", "source", "vars", "here", "item", "shown_off", "repeat", "paid", "played_from",
                 "event", "origin_loc", "target_bf")

    def __init__(self, controller, source=None, here=None, item=None):
        self.controller, self.source = controller, source
        self.vars = {}
        self.here = here            # location the effect refers to with "here" (('base', p) or ('bf', i))
        self.item = item            # chain item id
        self.shown_off = None
        self.repeat = 0             # number of Repeat costs paid
        self.paid = {}              # optional additional costs paid, name -> bool
        self.played_from = None     # 'hand' | 'champion' | 'facedown' | 'trash' ...
        self.event = None           # the event that triggered this ability (dict)
        self.origin_loc = None
        self.target_bf = None       # for cards played from facedown: the battlefield index

    def clone(self):
        """Copy with its own containers: nested lists/dicts/sets in vars (targets, chosen stamps, costs) are copied
        too, so a lookahead clone can never write into the real game's context."""
        c = Context.__new__(Context)
        for k in Context.__slots__:
            v = getattr(self, k)
            setattr(c, k, _copy_containers(v) if isinstance(v, dict) else v)
        return c


def _copy_containers(v):
    if isinstance(v, dict):
        return {k: _copy_containers(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_copy_containers(x) for x in v]
    if isinstance(v, set):
        return set(v)
    return v


def val(game, ctx, v):
    """Resolve a value that may be a Ref, a callable (game, ctx) -> value, or a literal."""
    if isinstance(v, Ref):
        return ctx.vars.get(v.name)
    if callable(v) and not isinstance(v, type):
        return v(game, ctx)
    return v


class Frame:
    __slots__ = ("code", "pc", "ctx", "tag")

    def __init__(self, code, ctx, tag=None):
        self.code, self.pc, self.ctx, self.tag = code, 0, ctx, tag


class Instr:
    """Base class. Subclasses implement run(game, ctx)."""

    def run(self, game, ctx):
        raise NotImplementedError

    def compile(self, out, labels):
        """Default: emit self. Compound instructions override to emit flat code."""
        out.append(self)

    def __repr__(self):
        return f"{self.__class__.__name__}({', '.join(f'{k}={v!r}' for k, v in self.__dict__.items() if not k.startswith('_'))})"


class Jump(Instr):
    def __init__(self, target):
        self.target = target     # index or label name

    def run(self, game, ctx):
        return self.target


class JumpIf(Instr):
    def __init__(self, cond, target, negate=False):
        self.cond, self.target, self.negate = cond, target, negate

    def run(self, game, ctx):
        c = bool(val(game, ctx, self.cond))
        if c != self.negate:
            return self.target
        return None


class Label(Instr):
    def __init__(self, name):
        self.name = name

    def run(self, game, ctx):
        return None


def compile_effect(tree):
    """Flatten a nested instruction tree into a list; resolve labels to indices."""
    if tree is None:
        return []
    if isinstance(tree, Instr):
        tree = [tree]
    out = []
    counter = [0]
    for instr in tree:
        instr.compile(out, counter)
    # resolve labels
    positions = {}
    code = []
    for instr in out:
        if isinstance(instr, Label):
            positions[instr.name] = len(code)
        else:
            code.append(instr)
    for instr in code:
        # Jump, JumpIf and loop steps (ops._LoopNext) carry a label name until here
        t = getattr(instr, "target", None)
        if isinstance(t, str) and t in positions and (isinstance(instr, (Jump, JumpIf)) or type(instr).__name__ == "_LoopNext"):
            instr.target = positions[t]
    return code


def relocate(code, offset):
    """Copy compiled code so it can be placed `offset` instructions later (jump targets shifted)."""
    import copy as _copy
    out = []
    for instr in code:
        t = getattr(instr, "target", None)
        if isinstance(t, int) and (isinstance(instr, (Jump, JumpIf)) or type(instr).__name__ == "_LoopNext"):
            instr = _copy.copy(instr)
            instr.target = t + offset
        out.append(instr)
    return out


def new_label(counter, hint="L"):
    counter[0] += 1
    return f"{hint}{counter[0]}"


def run_vm(game):
    """Run the VM until a Decision is needed or all frames are done. Returns Decision or None."""
    while game.vm_frames:
        fr = game.vm_frames[-1]
        if fr.pc >= len(fr.code):
            game.vm_frames.pop()
            game.on_frame_done(fr)
            continue
        instr = fr.code[fr.pc]
        res = instr.run(game, fr.ctx)
        if isinstance(res, Decision):
            res.info.setdefault("frame", id(fr))
            game.pending = res
            return res
        if isinstance(res, int):
            fr.pc = res
        else:
            fr.pc += 1
        game.after_instruction()
    return None


def resume_vm(game, choice):
    """Apply a decision made for the top frame's current instruction."""
    fr = game.vm_frames[-1]
    d = game.pending
    game.pending = None
    if d.out is not None:
        fr.ctx.vars[d.out] = choice
    instr = fr.code[fr.pc]
    cont = getattr(instr, "resume", None)
    res = cont(game, fr.ctx, choice) if cont else None
    if isinstance(res, Decision):
        game.pending = res
        return res
    if isinstance(res, int):
        fr.pc = res
    else:
        fr.pc += 1
    game.after_instruction()
    return None
