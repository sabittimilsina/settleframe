# SettleFrame

**Time-dependent moment redistribution in building frames due to consolidation settlement of footings**

**Try it in the browser: [settleframe-sabit.streamlit.app](https://settleframe-sabit.streamlit.app)** (nothing to install)

SettleFrame computes how the bending moments in a 2D building frame change over time as the
clay under its footings consolidates. The frame is analyzed by the **direct stiffness method**.
The clay under each footing is modeled with **1D consolidation** (Terzaghi), and the two are
coupled at every time step by **Newton–Raphson iteration**. Dead load and live load are separate
load cases. A water-table drawdown can also be applied part-way through the building's life.

Course project for CE 7405 Statically Indeterminate Structures, Louisiana State University,
Fall 2026. Author: [Sabit Timilsina](https://sabittimilsina.github.io).

![SettleFrame web app](docs/web_app.png)

### Example result

<img src="docs/problem.png" width="420" align="right" alt="Example frame and footing settlements">

A 3-bay, 2-story RC frame. Footing F2 sits on thicker clay that drains only at the top, so
after 30 years it has settled 16 mm while the other footings settle 6–12 mm.

| At 30 years | Coupled (soil–structure interaction) | Uncoupled (footing loads fixed) |
|---|---|---|
| Largest settlement (F2) | 16.1 mm | 30.3 mm |
| Max angular distortion | 1/663 | 1/237 (exceeds 1/500) |
| Largest moment from settlement | 134 kN·m | 403 kN·m |

In the coupled analysis the frame transfers about a third of F2's load to its neighbors, which
slows F2's settlement. Ignoring this interaction overestimates the settlement moments about
three times in this example.

**Verification.** 29 checks against hand calculations and Terzaghi's solution all pass
(`verify.py`). The same frame built in **OpenSees** with the 30-year settlements imposed gives the
same reactions and member-end moments for all 32 values compared (`opensees/`).

<br clear="right">

**Two ways to use it:** the desktop program (`run_app.py`, below) or the **web version**
(`streamlit_app.py`), which anyone can open from the link above. To put your own copy online,
follow `DEPLOY_WEB_APP.md`. To run the web version on your own computer:
`pip install streamlit pandas`, then `streamlit run streamlit_app.py`.

---

## 1. Install

You need Python 3.8 or newer with three packages: `numpy`, `matplotlib` and `tkinter`.

- **Anaconda** (recommended): all three are already included. Nothing to install.
- **python.org installer**: tkinter is included. Then run
  `pip install -r requirements.txt` in this folder.
- **Linux**: `sudo apt install python3-tk`, then `pip install -r requirements.txt`.

## 2. Run

Open a terminal (on Windows: *Anaconda Prompt*) in the `SettleFrame` folder and type:

```
python run_app.py
```

The window opens with the example frame already loaded. If you use Spyder, run it from a
terminal instead: Spyder's own console can conflict with the program's plotting window.

To check the solver against hand calculations:

```
python verify.py
```

It prints 29 checks with the program value, the reference value and PASS/FAIL. The output is
also saved in `verification_results.txt`.

---

## 3. Using the program

The window has four tabs, used in order. The toolbar at the top has **Load example**,
**Open inputs… / Save inputs…** (JSON files), **▶ Run analysis**, **Export figures…**,
**Export results (CSV)…** and **Help**.

### Tab 1 — Frame & loads

| Input | Units | Notes |
|---|---|---|
| Bay widths | m | Comma-separated, left to right, e.g. `6, 6, 6` |
| Story heights | m | Comma-separated, bottom to top, e.g. `4, 3.5` |
| Column bases | – | Fixed or Pinned (horizontal and vertical movement are always restrained) |
| E | GPa | Elastic modulus of concrete |
| Column / beam b × h | m | Rectangular sections; A = b·h, I = b·h³/12 |
| Column / beam I factor | × Ig | 1.0 = gross section; lower it to model cracked concrete (e.g. 0.70 columns, 0.35 beams) |
| Dead load D per floor | kN/m | Uniform load on the beams of each floor, first floor first, roof last. One value = same on all floors |
| Live load L per floor | kN/m | Same format as dead load |
| Sustained part of live load ψ | 0–1 | Only D + ψ·L is on the building long enough to consolidate the clay |
| γD, γL, γS | – | Factors for the design combination γD·D + γL·L + γS·S(t). Use 1, 1, 1 for service level |

Press **Update preview** to redraw the frame with the footing numbers F1, F2, ….

### Tab 2 — Footings & soil

One row per footing, left to right. The number of rows follows the number of bays
automatically. All depths are measured from the ground surface.

| Column | Units | Meaning |
|---|---|---|
| B, L | m | Footing plan size |
| Df | m | Depth of the footing base |
| Clay top | m | Depth of the top of the clay layer (must be ≥ Df) |
| Clay H | m | Clay thickness |
| Cc, Cr | – | Compression and recompression indices (from an oedometer test) |
| e0 | – | Initial void ratio |
| OCR | – | Overconsolidation ratio (1 = normally consolidated) |
| cv | m²/yr | Coefficient of consolidation |
| Drainage | – | *Top & bottom* (sand below the clay) or *Top only* (rock or stiff clay below) |
| Drawdown | ☑ | Tick the footings affected by the lowered water table |

**Copy F1 to all** copies the first row to the others. The soil profile below the table
shows the clay layers and the water table.

### Tab 3 — Groundwater & time

| Input | Units | Notes |
|---|---|---|
| γ, γsat | kN/m³ | Soil unit weights above / below the water table |
| Initial water table depth | m | |
| Drawdown | m | Drop of the water table (0 = none). It must stay above the clay |
| Drawdown happens at | years | Time after the start of construction |
| Analysis period | years | e.g. 30 |
| Construction period | years | Load is applied linearly over this time (0 = all at once) |
| Number of time steps | – | 120 is plenty; steps are spaced logarithmically |
| Clay sublayers | – | Finite-difference sublayers per clay layer (40–100) |

### Tab 4 — Results

Press **▶ Run analysis**. The example takes about 2 seconds. The program then opens the
Results tab.

**Controls (left panel)**

- **Coupled / Uncoupled.** *Coupled* includes soil–structure interaction: a footing that
  settles more sheds load to its neighbors, which slows its own settlement. *Uncoupled*
  keeps the footing loads from a rigid-support analysis. This is the usual simple approach
  and is useful for comparison.
- **Time slider.** Moves through the analysis period. **◀ ▶** step one at a time,
  **Before drawdown** jumps to just before the water table drops, and **End** jumps to the
  last step.
- **Frame diagram.** Choose *Settlement effect S(t)*, *Dead load D*, *Live load L* or the
  *Combination*. You can also show the magnified deformed shape and label moment values.
- **Summary.** Settlements, the largest differential settlement and angular distortion, and
  the largest settlement moment at the chosen time. It also gives the peak values over the
  whole period.

**Plot tabs**

| Tab | What it shows |
|---|---|
| Frame & moments | Moment diagram on the frame (drawn on the tension side) and each footing's settlement |
| Settlement vs time | Settlement of every footing; solid = coupled, dashed = uncoupled |
| Footing loads vs time | Sustained load on each footing; shows the load shed between footings |
| Angular distortion | (s_right − s_left)/bay width for each bay, with the 1/500 band shaded (Bjerrum's limit for buildings where cracking is not acceptable); 1/150 lines appear if reached |
| Moment change vs time | Moments from settlement at the four most affected member ends |
| Tables | Footing settlements and loads; member-end moments for D, L, S(t) and the combination |

Every plot has the matplotlib toolbar (zoom, pan, save).

**Exports**

- **Export figures…** saves every plot as a 300-dpi PNG in slide style: Times New Roman,
  21 pt tick labels, 23 pt bold axis titles, 20 pt legend, thick lines and inward ticks.
- **Export results (CSV)…** saves `time_history.csv` (settlement and load of every footing
  at every time, both analyses) and `member_moments_…csv` (member-end moments at the chosen
  time).

### Sign conventions

- Settlement is positive downward.
- Beam moments: positive = tension at the bottom (sagging).
- Column moments: positive = tension on the right face.
- Diagrams are drawn on the tension side.

---

## 4. Suggested live demo (example file)

The example has no water-table drawdown and no construction period, so the results are
easy to follow. Both can be added in the inputs.

1. **Load example** → Tab 1 shows a 3-bay, 2-story frame. Tab 2 shows that F2 sits on a
   thicker clay layer that drains only at its top.
2. **Run analysis** → the summary at 30 years (coupled): F2 settles 16.1 mm, the largest
   angular distortion is 1/663, and the largest moment from settlement is 134 kN·m.
3. Move the **time slider**: the settlement moments grow as the clay under F2 consolidates.
4. *Settlement vs time*: F1, F3 and F4 finish settling in about two years; F2 keeps settling
   for decades. *Footing loads*: in the coupled analysis F2 sheds about a third of its load
   (344 → 233 kN), mostly to F1. In the uncoupled analysis the loads stay constant.
5. Switch to **Uncoupled**: the largest settlement moment rises to 403 kN·m and the angular
   distortion to 1/237, which fails the 1/500 limit. Ignoring soil–structure interaction
   overestimates the settlement moments in this case.
6. Change **Cc** of F2 from 0.35 to 0.6 and run again: the moment rises to about 160 kN·m.
7. Show **Combination** with 1.2D + 1.6L + 1.0S(t) and compare with *Dead load D*.
8. Run `python verify.py` to show the checks.

### Verification with OpenSees

`opensees/opensees_check.py` builds the example frame in OpenSeesPy (`elasticBeamColumn`
elements, fixed bases) and imposes the 30-year coupled settlements with `sp` constraints. It
compares the support reactions and member-end moments for D, L, S and D + 0.3L + S with
SettleFrame's values; all 32 values match (`opensees/opensees_results.txt`).

```
pip install openseespy
python opensees/opensees_check.py
```

`staad/` holds a STAAD.Pro input file of the same frame for a further check.

---

## 5. How it works

**Frame (direct stiffness method).** Members are 2D Euler–Bernoulli frame elements with three
DOFs per node. Element stiffness matrices are rotated to global axes and assembled. Beam loads
enter as fixed-end forces. Supports are partitioned into free and restrained DOFs, and settlement
is a prescribed displacement at a restrained DOF.

**Load cases.** D and L are analyzed on rigid supports. S(t) is the frame response to the
footing settlements at time t. Because the frame is linear, results combine as
γD·D + γL·L + γS·S(t). The condensed vertical stiffness of the frame at the footings, C, comes
from imposing a unit settlement at each footing in turn.

**Clay (1D consolidation).** For each footing, the stress increase in the clay comes from the
2:1 load spread, Δσ = P / ((B + z)(L + z)). A drawdown adds Δσ' = Δh(γw + γ − γsat). The excess
pore pressure follows du/dt = cv·d²u/dz² + dΔσ/dt. This is solved with implicit (backward Euler)
finite differences, so any step is stable. Strain follows the e–log σ' relation (Cr up to the
preconsolidation pressure, Cc beyond), and settlement is the strain integrated over the layer.

**Coupling (Newton–Raphson).** At each time step the footing settlements s satisfy
s = g(P), with P = λ(t)·R0 − C·s. Here R0 is the sustained-load reaction on rigid supports,
λ(t) the construction ramp, and g the consolidation settlement at the end of the step. Newton
iteration uses the Jacobian J = I + diag(dg/dP)·C and converges in 2–4 iterations.

## 6. Assumptions and limits

- Linear-elastic frame, small displacements, gravity loads only, no creep or shrinkage of
  concrete (lower the I factors to represent cracking).
- One clay layer per footing; the soil above and below it drains freely and does not compress.
- 1D consolidation with constant cv; no secondary compression (creep of the clay); no
  interaction between neighboring footings' stress bulbs.
- The column load acts as a net pressure on the footing; footing self-weight is not added.
- The e–log σ' model has no hysteresis (unloading follows Cr back along the same line).
- The lowered water table must stay above the clay layer.
- A footing cannot take tension; the program warns if a footing load becomes negative.

## 7. Files

```
SettleFrame/
├── run_app.py                 start the desktop GUI
├── streamlit_app.py           web version (same solver)
├── DEPLOY_WEB_APP.md          how to put the web version online
├── make_qr.py, settleframe_qr.png   QR code for the web link
├── packages.txt, .streamlit/  settings for Streamlit Community Cloud
├── verify.py                  29 checks against hand calculations
├── verification_results.txt   output of verify.py
├── requirements.txt
├── opensees/                  OpenSees check of the example frame
├── staad/                     STAAD.Pro input file of the example frame
├── docs/                      images used in this README
├── examples/example_3bay_2story.json
└── settleframe/
    ├── frame2d.py             direct stiffness frame solver
    ├── consolidation.py       1D consolidation of one clay layer
    ├── model.py               inputs, checks, building the models
    ├── analysis.py            load cases and coupled time stepping
    ├── plotting.py            plots (screen and slide style)
    └── gui.py                 Tkinter user interface
```
