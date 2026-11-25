"""Independent check of the SettleFrame example frame with OpenSees (openseespy).
Run from the SettleFrame folder:  pip install openseespy   then   python opensees/opensees_check.py
Same model as staad/example_frame_check.std: 3 bays x 6 m, stories 4.0 + 3.5 m, fixed bases,
E = 25 GPa, columns 0.4 x 0.4, beams 0.3 x 0.6 (Euler-Bernoulli elastic elements).
Load 1 = D, load 2 = L, load 3 = support settlements (coupled, t = 30 yr), load 4 = D + 0.3L + S."""
import sys
from pathlib import Path

import numpy as np
import openseespy.opensees as ops

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # the SettleFrame folder
from settleframe.model import example_inputs
from settleframe.analysis import run_analysis

E = 25e6
Ac, Ic = 0.4 * 0.4, 0.4 * 0.4**3 / 12
Ab, Ib = 0.3 * 0.6, 0.3 * 0.6**3 / 12
X = [0, 6, 12, 18]; Y = [0, 4.0, 7.5]
SETTLE = [-0.00708, -0.01612, -0.01244, -0.00602]   # same rounded values as the STAAD file
MEMBERS = ([(1 + c, 5 + c) for c in range(4)] + [(5 + c, 9 + c) for c in range(4)]
           + [(5 + b, 6 + b) for b in range(3)] + [(9 + b, 10 + b) for b in range(3)])


def run(case):
    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)
    for l, y in enumerate(Y):
        for c, x in enumerate(X):
            ops.node(4 * l + c + 1, x, y)
    ops.geomTransf("Linear", 1)
    for k, (i, j) in enumerate(MEMBERS, start=1):
        A, I = (Ac, Ic) if k <= 8 else (Ab, Ib)
        ops.element("elasticBeamColumn", k, i, j, A, E, I, 1)
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    if case in ("D", "L"):
        w_floor, w_roof = (30.0, 20.0) if case == "D" else (12.0, 5.0)
        for k in range(9, 15):
            ops.eleLoad("-ele", k, "-type", "-beamUniform", -(w_floor if k <= 11 else w_roof))
        for n in range(1, 5):
            ops.fix(n, 1, 1, 1)
    else:   # imposed support settlement
        for n in range(1, 5):
            ops.fix(n, 1, 0, 1)
            ops.sp(n, 2, SETTLE[n - 1])
    ops.constraints("Transformation")
    ops.numberer("RCM")
    ops.system("BandGeneral")
    ops.test("NormDispIncr", 1e-12, 10)
    ops.algorithm("Linear")
    ops.integrator("LoadControl", 1.0)
    ops.analysis("Static")
    ops.analyze(1)
    ops.reactions()
    R = np.array([ops.nodeReaction(n, 2) for n in range(1, 5)])
    F = np.array([ops.eleResponse(k, "localForce") for k in range(1, 15)])
    return R, F


res = {c: run(c) for c in ("D", "L", "S")}
res["C"] = tuple(res["D"][i] + 0.3 * res["L"][i] + res["S"][i] for i in range(2))

# SettleFrame with the same (rounded) settlements
r = run_analysis(example_inputs())
uy = r.meta["footing_uy_dofs"]
sfS = r.settlement_case(-np.array(SETTLE))
sf = {"D": r.case_D, "L": r.case_L, "S": sfS}
sf["C"] = r.case_D + 0.3 * r.case_L + sfS

rows = []
names = {"D": "D", "L": "L", "S": "S", "C": "D+0.3L+S"}
for c in ("D", "L", "S", "C"):
    for j in range(4):
        rows.append((f"Reaction FY, joint {j + 1} ({names[c]}), kN", sf[c].reactions[uy[j]], res[c][0][j]))
for c in ("D", "S"):
    for m in (1, 5, 9, 11):
        for e, lab in ((2, "start"), (5, "end")):
            rows.append((f"M, member {m} {lab} ({names[c]}), kN-m", sf[c].end_forces[m - 1, e], res[c][1][m - 1, e]))
worst = 0
print(f"{'Quantity':44s} {'SettleFrame':>12s} {'OpenSees':>12s} {'Diff %':>8s}")
for name, a, b in rows:
    d = 100 * abs(a - b) / max(abs(b), 1e-9)
    worst = max(worst, d)
    print(f"{name:44s} {a:12.4f} {b:12.4f} {d:10.6f}")
print(f"\nLargest difference: {worst:.6f} %  ({len(rows)} values)")
