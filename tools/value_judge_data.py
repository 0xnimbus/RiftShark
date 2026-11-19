"""Turn a `policy_data.py --values` file into judge training files (judge distillation, 2026-11-18).

out_values.npz: x (features of each one-turn sample after a searched candidate), y (that candidate's two-turn win
probability), game: value rows for `train_loop.py train --linear`.
out_pairs.npz: the rows that carry decision ids, in tools/rank_data.py's format (x, y, dec, opt, po), so
`train --pairs` adds ranking rows: within one searched decision, the candidate the two-turn search valued higher
should get the higher one-turn judgement.

usage: python tools/value_judge_data.py out/val_sv2.npz out/vj
"""
import sys

import numpy as np


def main(src, prefix):
    d = np.load(src)
    np.savez(prefix + "_values.npz", x=d["vx"], y=d["vy"], game=d["vgame"])
    if "vdec" in d:
        m = d["vdec"] >= 0
        dec = d["vgame"][m].astype(np.int64) * 1000000 + d["vdec"][m]
        np.savez(prefix + "_pairs.npz", x=d["vx"][m], y=d["vy"][m], dec=dec, opt=d["vopt"][m], po=d["vpo"][m])
        print(f"{len(d['vy'])} value rows, {int(m.sum())} with decision ids ({len(np.unique(dec))} decisions)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
