"""Verification of SettleFrame against hand calculations and closed-form solutions.

Run:  python verify.py
Each check prints the program value, the reference value, the difference and PASS/FAIL.
"""
import copy

import numpy as np

from settleframe.frame2d import Frame2D, Member
from settleframe.consolidation import ClayColumn, terzaghi_U, geostatic_effective_stress
from settleframe.model import example_inputs, build_clay
from settleframe.analysis import run_analysis

ROWS = []


def check(name, value, reference, tol=0.01):
    err = abs(value - reference) / max(abs(reference), 1e-12)
    ok = err <= tol
    ROWS.append((name, value, reference, err, ok))


E, I, A_RIGID = 25e6, 0.0054, 1e3   # kPa, m^4, very large area (axially rigid, as in hand methods)

# ---------------------------------------------------------------- 1. fixed-fixed beam, UDL
L, w = 6.0, 30.0
fr = Frame2D([(0, 0), (L, 0)], [Member(0, 1, E, A_RIGID, I)], {0: (1, 1, 1), 1: (1, 1, 1)})
res = fr.solve(w_gravity=[w])
check("Fixed-fixed beam, UDL: end moment (kN·m)", res.moment_along(0, 0.0), -w * L**2 / 12)
check("Fixed-fixed beam, UDL: midspan moment (kN·m)", res.moment_along(0, L / 2), w * L**2 / 24)

# ---------------------------------------------------------------- 2. fixed-fixed beam, end settles
D = 0.02
res = fr.solve(prescribed={4: -D})
check("Fixed-fixed beam, end settles: |end moment| (kN·m)", abs(res.moment_along(0, 0.0)), 6 * E * I * D / L**2)

# ---------------------------------------------------------------- 3. two-span beam, middle support settles
fr2 = Frame2D([(0, 0), (L, 0), (2 * L, 0)], [Member(0, 1, E, A_RIGID, I), Member(1, 2, E, A_RIGID, I)],
              {0: (1, 1, 0), 1: (0, 1, 0), 2: (0, 1, 0)})
res = fr2.solve(prescribed={4: -D})
check("Two-span beam, middle support settles: |M_B| (kN·m)", abs(res.moment_along(0, L)), 3 * E * I * D / L**2)

# ---------------------------------------------------------------- 4/5. portal frame by slope-deflection
h, Lb, Ic, Ib = 4.0, 6.0, 0.00213, 0.0054
nodes = [(0, 0), (0, h), (Lb, h), (Lb, 0)]
mem = [Member(0, 1, E, A_RIGID, Ic, "column"), Member(1, 2, E, A_RIGID, Ib), Member(3, 2, E, A_RIGID, Ic, "column")]
portal = Frame2D(nodes, mem, {0: (1, 1, 1), 3: (1, 1, 1)})

# (4) UDL on the beam, symmetric (no sway): theta_B (4EIc/h + 2EIb/L) = wL^2/12
thB = (w * Lb**2 / 12) / (4 * E * Ic / h + 2 * E * Ib / Lb)
M_BA = 4 * E * Ic / h * thB
res = portal.solve(w_gravity=[0, w, 0])
check("Portal frame, beam UDL: corner moment (kN·m)", abs(res.end_forces[0, 5]), M_BA)
check("Portal frame, beam UDL: base moment (kN·m)", abs(res.end_forces[0, 2]), M_BA / 2)

# (5) right base settles D: slope-deflection with sway (clockwise +)
#     unknowns x = [theta_B, theta_C, delta_h]; chord rotations: columns delta_h/h, beam D/Lb
kc, kb = 2 * E * Ic / h, 2 * E * Ib / Lb
def sd_moments(x):
    tB, tC, dh = x
    pc, pb = dh / h, D / Lb
    M_AB = kc * (tB - 3 * pc); M_BA = kc * (2 * tB - 3 * pc)
    M_BC = kb * (2 * tB + tC - 3 * pb); M_CB = kb * (2 * tC + tB - 3 * pb)
    M_DC = kc * (tC - 3 * pc); M_CD = kc * (2 * tC - 3 * pc)
    return M_AB, M_BA, M_BC, M_CB, M_DC, M_CD
def sd_eqs(x):
    M_AB, M_BA, M_BC, M_CB, M_DC, M_CD = sd_moments(x)
    return np.array([M_BA + M_BC, M_CB + M_CD, (M_AB + M_BA) / h + (M_DC + M_CD) / h])
J = np.column_stack([sd_eqs(e) - sd_eqs(np.zeros(3)) for e in np.eye(3)])
x = np.linalg.solve(J, -sd_eqs(np.zeros(3)))
M_AB, M_BA, M_BC, M_CB, M_DC, M_CD = sd_moments(x)
res = portal.solve(prescribed={3 * 3 + 1: -D})
check("Portal frame, one base settles: beam moment at B (kN·m)", abs(res.end_forces[1, 2]), abs(M_BC))
check("Portal frame, one base settles: beam moment at C (kN·m)", abs(res.end_forces[1, 5]), abs(M_CB))
check("Portal frame, one base settles: base moment at D (kN·m)", abs(res.end_forces[2, 2]), abs(M_DC))

# ---------------------------------------------------------------- 6. consolidation rate vs Terzaghi
# Degree of consolidation from the average excess pore pressure, U = 1 - u_avg / delta_sigma,
# compared with Terzaghi's series solution for a uniform, instantly applied load.
for drainage, label in (("both", "drained top & bottom"), ("top", "drained top only")):
    col = ClayColumn(B=1000, L=1000, Df=0, z_top=3.0, H=4.0, Cc=0.3, Cr=0.05, e0=0.9, OCR=1.0, cv=2.0,
                     drainage=drainage, gamma=18, gamma_sat=19.5, wt_depth=1.0, n_sub=100)
    P = 20.0 * 1000**2         # about 20 kPa, nearly uniform with depth under a very wide load
    Hdr = col.drainage_path
    targets = np.array([0.05, 0.1, 0.2, 0.5, 1.0])
    t_targets = targets * Hdr**2 / col.cv
    grid = np.unique(np.concatenate([[0.0], np.logspace(-7, np.log10(t_targets[-1]), 800), t_targets]))
    out = {}
    for k in range(1, len(grid)):
        col.commit(P, 0.0, grid[k] - grid[k - 1])
        dsig_avg = float(np.sum(0.5 * (col.dsig[:-1] + col.dsig[1:]) * col.dz) / col.H)
        out[grid[k]] = 1.0 - col.average_excess_pressure() / dsig_avg
    for Tv, tt in zip(targets, t_targets):
        check(f"Consolidation ({label}): U at Tv = {Tv}", out[tt], terzaghi_U(Tv)[0], tol=0.02)

# ---------------------------------------------------------------- 7. final settlement vs hand formula
for OCR, label in ((1.0, "normally consolidated"), (2.0, "overconsolidated, crosses sigma'p")):
    col = ClayColumn(B=1000, L=1000, Df=0, z_top=5.0, H=0.2, Cc=0.3, Cr=0.05, e0=0.9, OCR=OCR, cv=2.0,
                     drainage="both", gamma=18, gamma_sat=19.5, wt_depth=1.0, n_sub=20)
    dsig = 50.0
    P = dsig * (1000 + 5.0) * (1000 + 5.0)    # 2:1 spread at mid-depth (z below footing = 5.1 m approx.)
    s_prog = col.final_settlement(P)
    zmid = 5.1
    s0 = geostatic_effective_stress(zmid, 18, 19.5, 1.0)
    ds = P / ((1000 + zmid) ** 2)
    sp = OCR * s0
    if s0 + ds <= sp:
        s_hand = 0.05 * 0.2 / 1.9 * np.log10((s0 + ds) / s0)
    else:
        s_hand = 0.2 / 1.9 * (0.05 * np.log10(sp / s0) + 0.3 * np.log10((s0 + ds) / sp))
    check(f"Final consolidation settlement, {label} (mm)", 1000 * s_prog, 1000 * s_hand, tol=0.01)

# ---------------------------------------------------------------- 8. equilibrium and coupling (example frame)
inp = example_inputs()
r = run_analysis(inp)
wD, wL = r.meta["wD"], r.meta["wL"]
total_D = sum(wD[k] * r.frame.geom[k][0] for k in range(len(wD)))
total_L = sum(wL[k] * r.frame.geom[k][0] for k in range(len(wL)))
uy = r.meta["footing_uy_dofs"]
check("Example frame: sum of dead-load reactions = total dead load (kN)", r.case_D.reactions[uy].sum(), total_D, 1e-6)
check("Example frame: sum of live-load reactions = total live load (kN)", r.case_L.reactions[uy].sum(), total_L, 1e-6)
sust = total_D + inp["loads"]["psi_sustained"] * total_L
h_c = r.hist["Coupled"]
check("Coupled history: sum of footing loads at end = sustained load (kN)", h_c.P[-1].sum(), sust, 1e-6)
S_end = r.settlement_case(h_c.s[-1])
check("Settlement case: sum of vertical reactions = 0 (kN, abs.)", abs(S_end.reactions[uy].sum()) + 1.0, 1.0, 1e-6)

# long-term coupled result vs drained (u = 0) equilibrium found by a separate iteration
inp2 = copy.deepcopy(inp)
inp2["soil"]["drawdown"] = 0.0
inp2["time"]["t_end"] = 2000.0
r2 = run_analysis(inp2)
cols = [build_clay(inp2, k) for k in range(r2.nf)]
s = np.zeros(r2.nf)
for _ in range(2000):                       # damped fixed-point iteration on the drained state
    P = r2.R0v - r2.C @ s
    g = np.array([cols[k].final_settlement(P[k]) for k in range(r2.nf)])
    s = s + 0.02 * (g - s)
for k in range(r2.nf):
    check(f"Long-term coupled settlement, footing {k + 1} vs drained equilibrium (mm)",
          1000 * r2.hist["Coupled"].s[-1, k], 1000 * s[k], tol=0.01)

# ---------------------------------------------------------------- report
w1 = max(len(n) for n, *_ in ROWS)
print(f"{'Check':<{w1}}  {'Program':>12}  {'Reference':>12}  {'Diff.':>7}  Result")
for name, v, ref, err, ok in ROWS:
    print(f"{name:<{w1}}  {v:12.4f}  {ref:12.4f}  {100 * err:6.2f}%  {'PASS' if ok else 'FAIL'}")
n_ok = sum(r[-1] for r in ROWS)
print(f"\n{n_ok} of {len(ROWS)} checks passed.")
