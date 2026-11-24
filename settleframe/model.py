"""Input data for SettleFrame: defaults, checking, saving/loading, and building the models."""
from __future__ import annotations

import copy
import json

import numpy as np

from .frame2d import Frame2D, Member
from .consolidation import ClayColumn

DRAINAGE_OPTIONS = ("Top & bottom", "Top only")

DEFAULT_FOOTING = {
    "B": 2.0, "L": 2.0, "Df": 1.5,          # footing size and depth (m)
    "clay_top": 3.0, "H": 4.0,              # clay layer depth and thickness (m)
    "Cc": 0.30, "Cr": 0.05, "e0": 0.90, "OCR": 1.5,
    "cv": 2.0,                              # m^2/year
    "drainage": "Top & bottom",
    "drawdown": False,                      # affected by the water-table drawdown?
}


def example_inputs() -> dict:
    """3-bay, 2-story concrete frame. Footing 2 sits over a thicker, more compressible clay layer that
    drains only at its top. No water-table drawdown (it can be added in the inputs)."""
    footings = [copy.deepcopy(DEFAULT_FOOTING) for _ in range(4)]
    footings[1].update({"H": 6.0, "Cc": 0.35, "OCR": 1.2, "cv": 1.0, "drainage": "Top only"})
    return {
        "frame": {
            "bays": [6.0, 6.0, 6.0],
            "stories": [4.0, 3.5],
            "E_GPa": 25.0,
            "col_b": 0.40, "col_h": 0.40,
            "beam_b": 0.30, "beam_h": 0.60,
            "col_Ifactor": 1.0, "beam_Ifactor": 1.0,   # I_eff / I_gross (e.g. 0.70 and 0.35 for cracked concrete)
            "base": "Fixed",
        },
        "loads": {
            "dead": [30.0, 20.0],     # kN/m on the beams of each floor, bottom floor first
            "live": [12.0, 5.0],
            "psi_sustained": 0.30,    # fraction of live load that is sustained (drives consolidation)
            "gamma_D": 1.2, "gamma_L": 1.6, "gamma_S": 1.0,
        },
        "soil": {
            "gamma": 18.0, "gamma_sat": 19.5,   # kN/m^3
            "wt_depth": 1.0,                    # initial water table depth (m)
            "drawdown": 0.0,                    # drop of the water table (m); 0 = none
            "drawdown_time": 5.0,               # years after the start of construction
        },
        "footings": footings,
        "time": {"t_end": 30.0, "t_construction": 0.0, "n_steps": 120, "n_sub": 60},
    }


# ----------------------------------------------------------------------------- I/O
def save_inputs(inp: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(inp, f, indent=2)


def load_inputs(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        inp = json.load(f)
    base = example_inputs()
    for key in ("frame", "loads", "soil", "time"):
        base[key].update(inp.get(key, {}))
    if "footings" in inp:
        base["footings"] = [dict(DEFAULT_FOOTING, **fd) for fd in inp["footings"]]
    return base


# ----------------------------------------------------------------------------- checking
def per_floor(values, n_stories, name):
    vals = [float(v) for v in values]
    if len(vals) == 1:
        vals = vals * n_stories
    if len(vals) != n_stories:
        raise ValueError(f"{name}: give one value per floor ({n_stories} floors), or a single value for all floors.")
    return vals


def check_inputs(inp: dict) -> list:
    """Return a list of warning strings; raise ValueError for inputs that cannot be analyzed."""
    warn = []
    fr, ld, so, tm = inp["frame"], inp["loads"], inp["soil"], inp["time"]
    if len(fr["bays"]) < 1 or len(fr["stories"]) < 1:
        raise ValueError("The frame needs at least one bay and one story.")
    if min(fr["bays"]) <= 0 or min(fr["stories"]) <= 0:
        raise ValueError("Bay widths and story heights must be positive.")
    for k in ("E_GPa", "col_b", "col_h", "beam_b", "beam_h", "col_Ifactor", "beam_Ifactor"):
        if float(fr.get(k, 1.0)) <= 0:
            raise ValueError(f"Section property '{k}' must be positive.")
    ns = len(fr["stories"])
    per_floor(ld["dead"], ns, "Dead load")
    per_floor(ld["live"], ns, "Live load")
    if not 0.0 <= float(ld["psi_sustained"]) <= 1.0:
        raise ValueError("The sustained fraction of live load must be between 0 and 1.")
    nf = len(fr["bays"]) + 1
    if len(inp["footings"]) != nf:
        raise ValueError(f"The frame has {nf} columns, so it needs {nf} footing rows (found {len(inp['footings'])}).")
    if so["gamma"] <= 0 or so["gamma_sat"] <= 0:
        raise ValueError("Unit weights must be positive.")
    drop = float(so["drawdown"])
    if drop < 0:
        raise ValueError("Drawdown must be zero or positive (a drop of the water table).")
    for k, fd in enumerate(inp["footings"], start=1):
        for key in ("B", "L", "H", "Cc", "e0", "cv"):
            if float(fd[key]) <= 0:
                raise ValueError(f"Footing {k}: '{key}' must be positive.")
        if float(fd["Cr"]) < 0 or float(fd["Df"]) < 0:
            raise ValueError(f"Footing {k}: Cr and Df cannot be negative.")
        if float(fd["OCR"]) < 1.0:
            raise ValueError(f"Footing {k}: OCR must be 1.0 or more.")
        if float(fd["clay_top"]) < float(fd["Df"]):
            raise ValueError(f"Footing {k}: the top of the clay must be at or below the footing base.")
        if fd.get("drawdown") and drop > 0 and so["wt_depth"] + drop > float(fd["clay_top"]) + 1e-9:
            raise ValueError(f"Footing {k}: the lowered water table would enter the clay layer. "
                             "This version assumes the water table stays above the clay.")
        if float(fd["Cr"]) > float(fd["Cc"]):
            warn.append(f"Footing {k}: Cr is larger than Cc, which is unusual.")
    if tm["t_end"] <= 0 or tm["n_steps"] < 10:
        raise ValueError("Analysis period must be positive and the number of steps at least 10.")
    if tm["t_construction"] < 0 or tm["t_construction"] >= tm["t_end"]:
        raise ValueError("Construction period must be zero or positive and shorter than the analysis period.")
    if drop > 0 and not any(fd.get("drawdown") for fd in inp["footings"]):
        warn.append("A drawdown is set but no footing is marked as affected, so it has no effect.")
    if drop > 0 and not (0 <= so["drawdown_time"] < tm["t_end"]):
        raise ValueError("Drawdown time must be within the analysis period.")
    return warn


# ----------------------------------------------------------------------------- model building
def build_frame(inp: dict):
    """Build the Frame2D model and a dictionary of bookkeeping information."""
    fr = inp["frame"]
    bays = [float(b) for b in fr["bays"]]
    stories = [float(h) for h in fr["stories"]]
    x = np.concatenate([[0.0], np.cumsum(bays)])
    y = np.concatenate([[0.0], np.cumsum(stories)])
    ncol, nlev = len(x), len(y)
    E = float(fr["E_GPa"]) * 1e6
    Ac = fr["col_b"] * fr["col_h"]
    Ic = fr["col_b"] * fr["col_h"] ** 3 / 12.0 * float(fr.get("col_Ifactor", 1.0))
    Ab = fr["beam_b"] * fr["beam_h"]
    Ib = fr["beam_b"] * fr["beam_h"] ** 3 / 12.0 * float(fr.get("beam_Ifactor", 1.0))

    def node(lev, col):
        return lev * ncol + col

    nodes = [(x[c], y[l]) for l in range(nlev) for c in range(ncol)]
    members, beam_level = [], []
    for l in range(1, nlev):
        for c in range(ncol):
            members.append(Member(node(l - 1, c), node(l, c), E, Ac, Ic, "column",
                                  f"Column {c + 1}, story {l}", ("bottom", "top")))
            beam_level.append(0)
    for l in range(1, nlev):
        for b in range(ncol - 1):
            members.append(Member(node(l, b), node(l, b + 1), E, Ab, Ib, "beam",
                                  f"Beam level {l}, bay {b + 1}", ("left", "right")))
            beam_level.append(l)
    fixed_rot = str(fr.get("base", "Fixed")).lower().startswith("fix")
    restraints = {node(0, c): (True, True, fixed_rot) for c in range(ncol)}
    frame = Frame2D(nodes, members, restraints)

    ns = len(stories)
    dead = per_floor(inp["loads"]["dead"], ns, "Dead load")
    live = per_floor(inp["loads"]["live"], ns, "Live load")
    wD = np.array([dead[l - 1] if l > 0 else 0.0 for l in beam_level])
    wL = np.array([live[l - 1] if l > 0 else 0.0 for l in beam_level])
    meta = {
        "x": x, "y": y, "ncol": ncol, "nlev": nlev,
        "footing_nodes": [node(0, c) for c in range(ncol)],
        "footing_uy_dofs": [3 * node(0, c) + 1 for c in range(ncol)],
        "wD": wD, "wL": wL, "beam_level": beam_level,
        "bays": bays, "stories": stories,
    }
    return frame, meta


def build_clay(inp: dict, k: int) -> ClayColumn:
    fd, so = inp["footings"][k], inp["soil"]
    drainage = "both" if fd["drainage"] == DRAINAGE_OPTIONS[0] else "top"
    return ClayColumn(fd["B"], fd["L"], fd["Df"], fd["clay_top"], fd["H"], fd["Cc"], fd["Cr"], fd["e0"],
                      fd["OCR"], fd["cv"], drainage, so["gamma"], so["gamma_sat"], so["wt_depth"],
                      n_sub=int(inp["time"].get("n_sub", 60)))
