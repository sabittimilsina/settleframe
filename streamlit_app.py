"""SettleFrame web app (Streamlit).

Run locally:   streamlit run streamlit_app.py
Online:        deploy this repository on Streamlit Community Cloud (main file: streamlit_app.py)

Uses the same solver as the desktop GUI (settleframe/ package).
"""
import copy
import io
import json

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd
import streamlit as st
from matplotlib.figure import Figure

from settleframe import plotting as pl
from settleframe.analysis import run_analysis
from settleframe.model import DEFAULT_FOOTING, DRAINAGE_OPTIONS, check_inputs, example_inputs

st.set_page_config(page_title="SettleFrame", page_icon="🏗️", layout="wide")
pl.apply_rc()

FOOT_COLS = ["B", "L", "Df", "clay_top", "H", "Cc", "Cr", "e0", "OCR", "cv", "drainage", "drawdown"]
FOOT_LABELS = {"B": "B (m)", "L": "L (m)", "Df": "Df (m)", "clay_top": "Clay top (m)", "H": "Clay H (m)",
               "Cc": "Cc", "Cr": "Cr", "e0": "e0", "OCR": "OCR", "cv": "cv (m²/yr)",
               "drainage": "Drainage", "drawdown": "Drawdown?"}
CASES = {"Settlement effect S(t)": "S", "Dead load D": "D", "Live load L": "L", "Combination": "Combo"}


# ------------------------------------------------------------------ state
if "inp" not in st.session_state:
    st.session_state.inp = example_inputs()
    st.session_state.ver = 0
    st.session_state.msg = ""


def lst(v):
    return ", ".join(f"{float(x):g}" for x in v)


def parse_list(txt, name):
    try:
        vals = [float(x) for x in str(txt).replace(";", ",").split(",") if x.strip()]
    except ValueError:
        raise ValueError(f"{name}: use comma-separated numbers, e.g. 6, 6, 6")
    if not vals:
        raise ValueError(f"{name} is empty.")
    return vals


@st.cache_resource(show_spinner=False, max_entries=20)
def analyze(inp_json: str):
    return run_analysis(json.loads(inp_json))


def fig(w=8, h=4.2):
    try:
        return Figure(figsize=(w, h), dpi=150, layout="constrained")
    except TypeError:
        return Figure(figsize=(w, h), dpi=150, constrained_layout=True)


def show(f, note=""):
    """Plot on the left (about 3/4 of the width), short explanation on the right.
    On a phone the two columns stack."""
    a, b = st.columns([3, 1])
    a.pyplot(f, width="stretch")
    if note:
        b.markdown(note)


# ------------------------------------------------------------------ header
st.markdown("## SettleFrame")
st.markdown("**Time-dependent moment redistribution in building frames due to consolidation settlement of "
            "footings.** Direct stiffness frame analysis coupled with 1D consolidation of the clay under each "
            "footing (Newton–Raphson at every time step). CE 7405, LSU, Fall 2026 · Sabit Timilsina")

inp = st.session_state.inp
v = st.session_state.ver

# ------------------------------------------------------------------ inputs
with st.expander("Inputs: the example frame is loaded. Open to change it, then press Run analysis.",
                 expanded=False):
    c1, c2 = st.columns([1, 5])
    if c1.button("Reset to example"):
        st.session_state.inp = example_inputs()
        st.session_state.ver += 1
        st.session_state.msg = "Example loaded."
        st.rerun()
    c2.caption("Example: 3 bays × 2 stories. F2 sits on thicker clay that drains only at the top; "
               "the water table drops 1.5 m under F3 and F4 at year 5.")

    with st.form(f"inputs_{v}"):
        t1, t2, t3 = st.tabs(["1 · Frame & loads", "2 · Footings & clay", "3 · Groundwater & time"])
        fr, ld, so, tm = inp["frame"], inp["loads"], inp["soil"], inp["time"]
        with t1:
            a, b, c = st.columns(3)
            bays = a.text_input("Bay widths (m), left to right", lst(fr["bays"]))
            stories = b.text_input("Story heights (m), bottom to top", lst(fr["stories"]))
            base = c.selectbox("Column bases", ["Fixed", "Pinned"], index=0 if fr["base"] == "Fixed" else 1)
            a, b, c, d = st.columns(4)
            E = a.number_input("E (GPa)", value=float(fr["E_GPa"]), min_value=1.0)
            cb = b.number_input("Column b (m)", value=float(fr["col_b"]), min_value=0.05, format="%.2f")
            ch = c.number_input("Column h (m)", value=float(fr["col_h"]), min_value=0.05, format="%.2f")
            cI = d.number_input("Column I factor (× Ig)", value=float(fr["col_Ifactor"]), min_value=0.05,
                                max_value=1.5, format="%.2f")
            a, b, c, d = st.columns(4)
            bb = a.number_input("Beam b (m)", value=float(fr["beam_b"]), min_value=0.05, format="%.2f")
            bh = b.number_input("Beam h (m)", value=float(fr["beam_h"]), min_value=0.05, format="%.2f")
            bI = c.number_input("Beam I factor (× Ig)", value=float(fr["beam_Ifactor"]), min_value=0.05,
                                max_value=1.5, format="%.2f")
            a, b, c = st.columns(3)
            dead = a.text_input("Dead load D per floor (kN/m)", lst(ld["dead"]))
            live = b.text_input("Live load L per floor (kN/m)", lst(ld["live"]))
            psi = c.number_input("Sustained part of live load ψ", value=float(ld["psi_sustained"]),
                                 min_value=0.0, max_value=1.0, format="%.2f")
            a, b, c = st.columns(3)
            gD = a.number_input("γD", value=float(ld["gamma_D"]), format="%.2f")
            gL = b.number_input("γL", value=float(ld["gamma_L"]), format="%.2f")
            gS = c.number_input("γS", value=float(ld["gamma_S"]), format="%.2f")
            st.caption("Floors are listed from the first floor up to the roof; one value applies to all floors. "
                       "Consolidation is driven by D + ψ·L. Design moments = γD·D + γL·L + γS·S(t).")
        with t2:
            df = pd.DataFrame(inp["footings"])[FOOT_COLS]
            df.index = [f"F{k + 1}" for k in range(len(df))]
            num = {k: st.column_config.NumberColumn(FOOT_LABELS[k], format="%.3g", min_value=0.0)
                   for k in FOOT_COLS if k not in ("drainage", "drawdown")}
            edited = st.data_editor(
                df, num_rows="fixed", width="stretch",
                column_config={**num,
                               "drainage": st.column_config.SelectboxColumn("Drainage", options=list(DRAINAGE_OPTIONS),
                                                                            required=True),
                               "drawdown": st.column_config.CheckboxColumn("Drawdown?")})
            st.caption("One row per footing, left to right. Depths are below the ground surface. The clay layer "
                       "consolidates; soil above and below it drains freely. If you change the number of bays, "
                       "the table is resized when you press Run.")
        with t3:
            a, b, c = st.columns(3)
            gam = a.number_input("γ above water table (kN/m³)", value=float(so["gamma"]))
            gsat = b.number_input("γsat below water table (kN/m³)", value=float(so["gamma_sat"]))
            wt = c.number_input("Initial water table depth (m)", value=float(so["wt_depth"]), min_value=0.0)
            a, b, c = st.columns(3)
            dd = a.number_input("Water-table drop (m), 0 = none", value=float(so["drawdown"]), min_value=0.0)
            tw = b.number_input("Drop happens at (years)", value=float(so["drawdown_time"]), min_value=0.0)
            tend = c.number_input("Analysis period (years)", value=float(tm["t_end"]), min_value=1.0)
            a, b, c = st.columns(3)
            tc = a.number_input("Construction period (years)", value=float(tm["t_construction"]), min_value=0.0)
            nst = b.number_input("Time steps", value=int(tm["n_steps"]), min_value=20, max_value=400, step=10)
            nsub = c.number_input("Clay sublayers", value=int(tm["n_sub"]), min_value=10, max_value=120, step=10)
        run = st.form_submit_button("▶ Run analysis", type="primary")

    if run:
        try:
            new = copy.deepcopy(inp)
            new["frame"].update(bays=parse_list(bays, "Bay widths"), stories=parse_list(stories, "Story heights"),
                                base=base, E_GPa=E, col_b=cb, col_h=ch, col_Ifactor=cI,
                                beam_b=bb, beam_h=bh, beam_Ifactor=bI)
            new["loads"].update(dead=parse_list(dead, "Dead load"), live=parse_list(live, "Live load"),
                                psi_sustained=psi, gamma_D=gD, gamma_L=gL, gamma_S=gS)
            new["soil"].update(gamma=gam, gamma_sat=gsat, wt_depth=wt, drawdown=dd, drawdown_time=tw)
            new["time"].update(t_end=tend, t_construction=tc, n_steps=int(nst), n_sub=int(nsub))
            foots = []
            for _, row in edited.iterrows():
                fd = {k: (row[k] if k in ("drainage", "drawdown") else float(row[k])) for k in FOOT_COLS}
                fd["drawdown"] = bool(fd["drawdown"])
                foots.append(fd)
            nf = len(new["frame"]["bays"]) + 1
            msg = ""
            if len(foots) != nf:
                while len(foots) < nf:
                    foots.append(dict(foots[-1]) if foots else dict(DEFAULT_FOOTING))
                foots = foots[:nf]
                msg = f"Footing table resized to {nf} footings to match the frame; check the new rows. "
            new["footings"] = foots
            check_inputs(new)
            st.session_state.inp = new
            st.session_state.ver += 1
            st.session_state.msg = msg + "Analysis updated."
            st.rerun()
        except ValueError as e:
            st.error(str(e))

if st.session_state.msg:
    st.info(st.session_state.msg)

# ------------------------------------------------------------------ analysis
try:
    with st.spinner("Running the coupled analysis…"):
        res = analyze(json.dumps(st.session_state.inp, sort_keys=True))
except Exception as e:  # noqa: BLE001
    st.error(f"Analysis failed: {e}")
    st.stop()

for w in res.warnings:
    st.warning(w)

# ------------------------------------------------------------------ result controls
t = res.t
c1, c2, c3 = st.columns([1.1, 2.4, 1.3])
mode = c1.radio("Analysis", ["Coupled", "Uncoupled"], horizontal=True,
                help="Coupled: a footing that settles more sheds load to its neighbors (soil–structure "
                     "interaction). Uncoupled: footing loads stay at their rigid-support values.")
it = c2.select_slider("Time (years)", options=list(range(len(t))), value=len(t) - 1,
                      format_func=lambda k: f"{t[k]:.3g}")
case = CASES[c3.selectbox("Frame diagram", list(CASES))]
logx = True

h = res.hist[mode]
s_now = 1000 * h.s[it]
beta = res.angular_distortion(mode)
Mh = res.end_moment_history(mode)
Ms_now = np.abs(Mh[it])
kk, ee = np.unravel_index(np.argmax(Ms_now), Ms_now.shape)
rigid = res.rigid_loads(it)
dP = 100 * (h.P[it] - rigid) / np.where(np.abs(rigid) > 1e-9, rigid, 1.0)
kshed = int(np.argmin(dP))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Largest settlement", f"{s_now.max():.1f} mm", help=f"Footing F{int(np.argmax(s_now)) + 1}")
bmax = float(np.abs(beta[it]).max())
m2.metric("Max angular distortion", "≈ 0" if bmax < 1e-5 else f"1/{1 / bmax:.0f}",
          help="Differential settlement / bay width. 1/500 is a common limit for buildings.")
m3.metric("Largest moment from settlement", f"{Ms_now[kk, ee]:.0f} kN·m",
          help=f"{res.frame.members[kk].label}, {res.frame.members[kk].end_names[ee]}")
if mode == "Coupled":
    m4.metric(f"Load change at F{kshed + 1}", f"{dP[kshed]:+.0f} %",
              help="Sustained footing load compared with the rigid-support value")
else:
    m4.metric("Footing loads", "Not updated",
              help="The uncoupled analysis keeps the rigid-support footing loads.")

tabs = st.tabs(["Frame & moments", "Settlement vs time", "Footing loads vs time", "Angular distortion",
                "Moment change vs time", "Tables", "Method & verification"])

with tabs[0]:
    f = fig(8, 5.4)
    pl.plot_frame(f.add_subplot(111), res, case, mode, it, pl.GUI_STYLE, deformed=True, values=True)
    show(f, "Moments are drawn on the **tension side** (kN·m).\n\n"
            "Dashed line: deformed shape (magnified).\n\n"
            "Numbers under the footings: settlement at the selected time.\n\n"
            "Pick the case in **Frame diagram** above and move the **time slider**.")
with tabs[1]:
    f = fig()
    pl.plot_settlement(f.add_subplot(111), res, pl.GUI_STYLE, it, logx)
    show(f, "**Solid:** coupled. **Dashed:** uncoupled.\n\n"
            "Black dashed line: selected time. Blue dotted line: water-table drop.\n\n"
            "Thicker clay, or clay that drains only at the top, settles more slowly.")
with tabs[2]:
    f = fig()
    pl.plot_loads(f.add_subplot(111), res, pl.GUI_STYLE, it, logx)
    show(f, "Sustained footing loads.\n\nIn the **coupled** analysis a footing that settles more "
            "**sheds load** to its neighbors through the frame. The uncoupled analysis keeps the "
            "rigid-support loads.")
with tabs[3]:
    f = fig()
    pl.plot_distortion(f.add_subplot(111), res, mode, pl.GUI_STYLE, it, logx)
    show(f, "Angular distortion β = differential settlement / bay width, for each bay.\n\n"
            "Dashed line: **1/500**, a common limit for frame buildings (Bjerrum 1963).")
with tabs[4]:
    f = fig()
    pl.plot_moment_history(f.add_subplot(111), res, mode, pl.GUI_STYLE, it, logx)
    show(f, "Moments caused by settlement at the four most affected member ends.\n\n"
            "They grow as the clay consolidates and jump when the water table drops.")
with tabs[5]:
    st.markdown(f"**Footings at t = {t[it]:.3g} years ({mode.lower()})**")
    st.dataframe(pd.DataFrame({
        "Footing": [f"F{k + 1}" for k in range(res.nf)],
        "Settlement (mm)": np.round(s_now, 2),
        "Sustained load (kN)": np.round(h.P[it], 1),
        "Rigid-support load (kN)": np.round(rigid, 1),
        "Change (%)": np.round(dP, 1),
        "Final drained settlement (mm)": np.round(1000 * h.s_final, 2),
    }), hide_index=True, width="stretch")
    cases = [res.case(c, mode, it).end_moments() for c in ("D", "L", "S", "Combo")]
    rows = []
    for k, m in enumerate(res.frame.members):
        for e in (0, 1):
            rows.append([m.label, m.end_names[e]] + [round(float(c[k, e]), 1) for c in cases])
    st.markdown("**Member-end moments (kN·m).** Beams: + = tension at bottom. Columns: + = tension on the right face.")
    st.dataframe(pd.DataFrame(rows, columns=["Member", "End", "D", "L", "S(t)", "Combination"]),
                 hide_index=True, width="stretch", height=420)
    buf = io.StringIO()
    hist = {"time_yr": t}
    for md in ("Coupled", "Uncoupled"):
        for k in range(res.nf):
            hist[f"s_F{k + 1}_{md.lower()}_mm"] = 1000 * res.hist[md].s[:, k]
        for k in range(res.nf):
            hist[f"P_F{k + 1}_{md.lower()}_kN"] = res.hist[md].P[:, k]
    pd.DataFrame(hist).to_csv(buf, index=False)
    c1, c2 = st.columns(2)
    c1.download_button("Download time history (CSV)", buf.getvalue(), "settleframe_time_history.csv", "text/csv")
    c2.download_button("Download inputs (JSON)", json.dumps(st.session_state.inp, indent=2),
                       "settleframe_inputs.json", "application/json")
with tabs[6]:
    st.markdown(r"""
**Frame.** 2D Euler–Bernoulli frame elements (3 DOF per node) assembled by the direct stiffness method.
Dead load *D* and live load *L* are solved on rigid supports; the settlement case *S(t)* is the frame
response to the footing settlements, imposed as known support displacements. A unit settlement at each
footing gives the matrix **C** (change in footing load per unit settlement).

**Clay.** Under each footing, the load spreads by the 2:1 method. Excess pore pressure dissipates by
Terzaghi's 1D consolidation, solved step by step in time; settlement follows the e–log σ′ relation
(Cc, Cr, OCR). A lowered water table adds effective stress to the clay under the affected footings.

**Coupling.** At each time step, Newton–Raphson finds settlements **s** that satisfy
**s** = **g**(**P**₀ − **C s**): the clay settlement under the current footing loads equals the settlement
used to compute those loads. The uncoupled analysis keeps the rigid-support loads (**C** = 0).

**Verification.** 29 automatic checks pass (fixed–fixed and two-span beams with settlement, a portal frame
by slope-deflection, Terzaghi's degree of consolidation, final settlement by hand, long-term coupled
equilibrium); the largest difference is 0.24 %. The example frame is also checked against STAAD.Pro.

**Assumptions.** Linear elastic frame, gravity loads only; one clay layer per footing between
free-draining sand; constant cv; no secondary compression; footings do not interact.
""")
