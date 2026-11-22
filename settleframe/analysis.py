"""Time-dependent analysis: frame + consolidating clay under each footing.

Load cases (frame on rigid supports):
    D : dead load on the beams
    L : live load on the beams
    S(t) : effect of the footing settlements at time t (imposed support displacements)

Only the sustained load  D + psi*L  drives consolidation. At each time step the footing
settlements s are found by Newton-Raphson iteration of

    r(s) = s - g(P(s)) = 0,      P(s) = lambda(t) * R0 - C s

where R0 are the sustained-load footing reactions on rigid supports, C is the condensed
vertical stiffness of the frame at the footings (reaction change per unit settlement),
lambda(t) ramps the load during construction, and g(P) is the consolidation settlement of
each clay layer at the end of the step under load P. The Jacobian is

    J = I + diag(dg/dP) C.

"Coupled" includes the frame stiffness C (soil-structure interaction): a footing that
settles more sheds load to its neighbors. "Uncoupled" sets C = 0, so each footing keeps
its rigid-support load.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .consolidation import drawdown_stress
from .model import build_clay, build_frame, check_inputs


@dataclass
class History:
    s: np.ndarray        # (nt, nf) footing settlement, m (downward +)
    P: np.ndarray        # (nt, nf) sustained footing load, kN
    iters: np.ndarray    # (nt,) Newton iterations per step
    s_final: np.ndarray  # (nf,) drained (u = 0) settlement under the final loads, m


class Results:
    def __init__(self, inp, frame, meta, t, coupled, uncoupled, case_D, case_L, unit_cases, C, R0v, warnings):
        self.inputs = inp
        self.frame = frame
        self.meta = meta
        self.t = t
        self.hist = {"Coupled": coupled, "Uncoupled": uncoupled}
        self.case_D = case_D
        self.case_L = case_L
        self.unit_cases = unit_cases      # frame response to 1 m settlement of each footing
        self.C = C
        self.R0v = R0v
        self.warnings = warnings
        # member-end moments due to 1 m settlement of each footing: (n_members*2, nf)
        self.M_unit = np.column_stack([uc.end_moments().ravel() for uc in unit_cases])

    @property
    def nf(self):
        return len(self.meta["footing_nodes"])

    def settlement_case(self, s_vec):
        """Frame response S to the footing settlements s_vec (m, downward +)."""
        return sum(float(si) * uc for si, uc in zip(s_vec, self.unit_cases))

    def case(self, name, mode, it):
        s = self.hist[mode].s[it]
        ld = self.inputs["loads"]
        if name == "D":
            return self.case_D
        if name == "L":
            return self.case_L
        if name == "S":
            return self.settlement_case(s)
        if name == "Combo":
            return ld["gamma_D"] * self.case_D + ld["gamma_L"] * self.case_L + ld["gamma_S"] * self.settlement_case(s)
        raise KeyError(name)

    def end_moment_history(self, mode):
        """Member-end moments from settlement, shape (nt, n_members, 2), kN*m."""
        s = self.hist[mode].s
        M = (self.M_unit @ s.T).T
        return M.reshape(len(self.t), len(self.frame.members), 2)

    def angular_distortion(self, mode):
        """(nt, n_bays) differential settlement between adjacent footings / bay width."""
        s = self.hist[mode].s
        return (s[:, 1:] - s[:, :-1]) / np.asarray(self.meta["bays"])[None, :]

    def rigid_loads(self, it):
        return self.load_factor(self.t[it]) * self.R0v

    def load_factor(self, t):
        tc = float(self.inputs["time"]["t_construction"])
        return 1.0 if tc <= 0 else min(t / tc, 1.0)


def time_grid(t_end, t_c, t_w=None, n=120):
    pts = [0.0]
    pts += list(np.logspace(-4, np.log10(t_end), n))
    if t_c > 0:
        pts += list(np.linspace(0.0, t_c, 21)[1:])
    if t_w is not None and 0 <= t_w < t_end:
        pts += [t_w] + list(t_w + np.logspace(-4, np.log10(t_end - t_w), max(n // 2, 10)))
    t = np.unique(np.round(np.array(pts), 10))
    t = t[t <= t_end + 1e-12]
    keep = [0]
    for k in range(1, len(t)):
        if t[k] - t[keep[-1]] > 1e-9:
            keep.append(k)
    return t[keep]


def _run_history(inp, t, R0v, C, coupled, tol=1e-8, max_iter=40):
    nf = len(R0v)
    cols = [build_clay(inp, k) for k in range(nf)]
    so = inp["soil"]
    drop = float(so["drawdown"])
    t_w = float(so["drawdown_time"])
    dsw = drawdown_stress(drop, so["gamma"], so["gamma_sat"]) if drop > 0 else 0.0
    affected = np.array([bool(fd.get("drawdown")) for fd in inp["footings"]])
    tc = float(inp["time"]["t_construction"])

    nt = len(t)
    S = np.zeros((nt, nf))
    P = np.zeros((nt, nf))
    iters = np.zeros(nt, int)
    Cm = C if coupled else np.zeros_like(C)
    s = np.zeros(nf)
    for n in range(1, nt):
        dt = t[n] - t[n - 1]
        lam = 1.0 if tc <= 0 else min(t[n] / tc, 1.0)
        # a load change is applied at the start of the step it falls in
        w = np.where(affected & (drop > 0) & (t[n - 1] >= t_w - 1e-12), dsw, 0.0)
        Rb = lam * R0v
        for it in range(1, max_iter + 1):
            Pn = Rb - Cm @ s
            g = np.array([cols[k].trial(Pn[k], w[k], dt) for k in range(nf)])
            r = s - g
            if np.max(np.abs(r)) < tol:
                break
            h = 1e-4 * np.maximum(np.abs(Pn), 1.0)
            dg = np.array([(cols[k].trial(Pn[k] + h[k], w[k], dt) - g[k]) / h[k] for k in range(nf)])
            J = np.eye(nf) + dg[:, None] * Cm
            s = s - np.linalg.solve(J, r)
        else:
            raise RuntimeError(f"Newton iteration did not converge at t = {t[n]:.4g} years. "
                               "Try more time steps.")
        Pn = Rb - Cm @ s
        s = np.array([cols[k].commit(Pn[k], w[k], dt) for k in range(nf)])
        S[n], P[n], iters[n] = s, Pn, it
    w_end = np.where(affected & (drop > 0), dsw, 0.0)
    s_final = np.array([cols[k].final_settlement(P[-1, k], w_end[k]) for k in range(nf)])
    return History(S, P, iters, s_final)


def run_analysis(inp: dict) -> Results:
    warnings = check_inputs(inp)
    frame, meta = build_frame(inp)
    nf = len(meta["footing_nodes"])
    uy = meta["footing_uy_dofs"]

    case_D = frame.solve(w_gravity=meta["wD"])
    case_L = frame.solve(w_gravity=meta["wL"])
    psi = float(inp["loads"]["psi_sustained"])
    R0v = (case_D.reactions + psi * case_L.reactions)[uy]
    if np.any(R0v <= 0):
        warnings.append("At least one footing has no downward sustained load on rigid supports.")

    unit_cases, C = [], np.zeros((nf, nf))
    for j in range(nf):
        uc = frame.solve(prescribed={uy[j]: -1.0})       # 1 m downward settlement of footing j
        unit_cases.append(uc)
        C[:, j] = -uc.reactions[uy]                      # reaction change per unit settlement

    tm, so = inp["time"], inp["soil"]
    t_w = float(so["drawdown_time"]) if float(so["drawdown"]) > 0 else None
    t = time_grid(float(tm["t_end"]), float(tm["t_construction"]), t_w, int(tm["n_steps"]))
    coupled = _run_history(inp, t, R0v, C, coupled=True)
    uncoupled = _run_history(inp, t, R0v, C, coupled=False)
    if np.any(coupled.P < -1e-6):
        warnings.append("In the coupled analysis a footing load becomes negative (uplift); a real footing "
                        "cannot pull on the soil, so results after that point are not reliable.")
    return Results(inp, frame, meta, t, coupled, uncoupled, case_D, case_L, unit_cases, C, R0v, warnings)
