"""Tkinter graphical user interface for SettleFrame."""
from __future__ import annotations

import csv
import os
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from . import plotting as pl
from .analysis import run_analysis
from .model import (DEFAULT_FOOTING, DRAINAGE_OPTIONS, check_inputs, example_inputs, load_inputs,
                    save_inputs)

FOOT_COLS = [
    ("B", "B (m)", 6), ("L", "L (m)", 6), ("Df", "Df (m)", 6),
    ("clay_top", "Clay top (m)", 8), ("H", "Clay H (m)", 8),
    ("Cc", "Cc", 6), ("Cr", "Cr", 6), ("e0", "e0", 6), ("OCR", "OCR", 6),
    ("cv", "cv (m²/yr)", 8), ("drainage", "Drainage", 13), ("drawdown", "Drawdown", 8),
]

CASES = [("Settlement effect S(t)", "S"), ("Dead load D", "D"), ("Live load L", "L"), ("Combination", "Combo")]

HELP_TEXT = """SettleFrame — quick guide

1  Frame & loads
   Enter bay widths and story heights as comma-separated lists (m).
   Dead and live loads are uniform loads on the beams of each floor (kN/m),
   listed from the first floor up to the roof (one value = same on all floors).
   The sustained fraction of live load (psi) sets how much live load is
   present long enough to consolidate the clay: consolidation is driven by
   D + psi·L. The combination factors build the design case
   gD·D + gL·L + gS·S(t).

2  Footings & soil
   One row per footing, left to right (F1, F2, ...). Depths are measured
   from the ground surface. The clay layer is the compressible layer under
   the footing; soil above and below it drains freely. Tick "Drawdown" for
   footings affected by a lowered water table.

3  Groundwater & time
   Unit weights, the initial water table, an optional drawdown (drop in m
   and the time it happens), the analysis period and the construction period
   over which the load is applied.

4  Run analysis, then use the Results tab
   Move the time slider to see the frame at any time. "Coupled" includes
   soil–structure interaction (a settling footing sheds load to its
   neighbors); "Uncoupled" keeps the rigid-support footing loads.
   Export figures saves slide-ready PNGs; Export CSV saves the numbers.

Sign convention for moments in the tables
   Beams: positive = tension at the bottom (sagging).
   Columns: positive = tension on the right face.
   Diagrams are drawn on the tension side, so signs are not needed there.
   Settlements are positive downward.
"""


class ScrollFrame(ttk.Frame):
    """A frame with a vertical scrollbar."""

    def __init__(self, parent, width=500, **kw):
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, width=width)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _e):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))

    def _unbind_wheel(self, _e):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(seq)

    def _on_wheel(self, e):
        step = -1 if e.delta > 0 else 1
        self.canvas.yview_scroll(step * 2, "units")


def new_figure(figsize):
    """Figure with constrained layout (works with old and new matplotlib versions)."""
    try:
        return Figure(figsize=figsize, dpi=100, layout="constrained")
    except TypeError:
        return Figure(figsize=figsize, dpi=100, constrained_layout=True)


class PlotPanel(ttk.Frame):
    """Matplotlib figure with the standard navigation toolbar."""

    def __init__(self, parent, figsize=(8, 6)):
        super().__init__(parent)
        self.fig = new_figure(figsize)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        tb = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        tb.update()
        tb.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    def draw(self):
        self.canvas.draw_idle()


class SettleFrameApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SettleFrame — frame moments from consolidation settlement of footings")
        self.geometry("1440x900")
        self.minsize(1100, 700)
        pl.apply_rc()
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Accent.TButton", foreground="white", background=pl.PURPLE, font=("TkDefaultFont", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#5B2E99")])
        style.configure("Head.TLabel", font=("TkDefaultFont", 9, "bold"))
        style.configure("Note.TLabel", foreground="#555555")

        self.vars = {}             # ("frame","bays") -> StringVar
        self.footing_rows = []     # list of dicts: key -> Variable
        self.results = None
        self.it = 0

        self._build_toolbar()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self._build_tab_frame()
        self._build_tab_footings()
        self._build_tab_ground()
        self._build_tab_results()
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.status = tk.StringVar(value="Load the example or enter your own inputs, then press Run analysis.")
        ttk.Label(self, textvariable=self.status, anchor="w", relief="sunken", padding=(6, 2)).pack(fill="x")

        self.set_inputs(example_inputs())
        self.update_previews()

    # ================================================================ toolbar
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(6, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="Load example", command=self.load_example).pack(side="left")
        ttk.Button(bar, text="Open inputs…", command=self.open_inputs).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Save inputs…", command=self.save_inputs).pack(side="left", padx=(4, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bar, text="▶  Run analysis", style="Accent.TButton", command=self.run).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bar, text="Export figures…", command=self.export_figures).pack(side="left")
        ttk.Button(bar, text="Export results (CSV)…", command=self.export_csv).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Help", command=self.show_help).pack(side="right")

    # ================================================================ input widgets
    def _entry(self, parent, row, label, path, unit="", width=16, tip=""):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(6, 6), pady=2)
        var = tk.StringVar()
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=1, sticky="we", pady=2)
        ttk.Label(parent, text=unit, style="Note.TLabel").grid(row=row, column=2, sticky="w", padx=(4, 6))
        if tip:
            ttk.Label(parent, text=tip, style="Note.TLabel", wraplength=360).grid(
                row=row + 1, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 4))
        self.vars[path] = var
        return var

    def _build_tab_frame(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="  1  Frame & loads  ")
        left = ScrollFrame(tab, width=500)
        left.pack(side="left", fill="y", padx=(4, 0), pady=4)
        f = left.inner

        g = ttk.LabelFrame(f, text="Geometry", padding=6)
        g.pack(fill="x", padx=4, pady=4)
        self._entry(g, 0, "Bay widths", ("frame", "bays"), "m", tip="Comma-separated, left to right, e.g. 6, 6, 6")
        self._entry(g, 2, "Story heights", ("frame", "stories"), "m", tip="Comma-separated, bottom to top, e.g. 4, 3.5")
        ttk.Label(g, text="Column bases").grid(row=4, column=0, sticky="w", padx=6)
        v = tk.StringVar()
        ttk.Combobox(g, textvariable=v, values=("Fixed", "Pinned"), state="readonly", width=13).grid(
            row=4, column=1, sticky="w", pady=2)
        self.vars[("frame", "base")] = v

        s = ttk.LabelFrame(f, text="Sections (rectangular, concrete)", padding=6)
        s.pack(fill="x", padx=4, pady=4)
        self._entry(s, 0, "Elastic modulus E", ("frame", "E_GPa"), "GPa")
        self._entry(s, 1, "Column width b", ("frame", "col_b"), "m")
        self._entry(s, 2, "Column depth h", ("frame", "col_h"), "m")
        self._entry(s, 3, "Beam width b", ("frame", "beam_b"), "m")
        self._entry(s, 4, "Beam depth h", ("frame", "beam_h"), "m")
        self._entry(s, 5, "Column I factor", ("frame", "col_Ifactor"), "× Ig")
        self._entry(s, 6, "Beam I factor", ("frame", "beam_Ifactor"), "× Ig",
                    tip="1.0 = gross section. Lower values model cracked concrete (e.g. 0.70 columns, 0.35 beams).")

        lo = ttk.LabelFrame(f, text="Load cases (uniform load on the beams)", padding=6)
        lo.pack(fill="x", padx=4, pady=4)
        self._entry(lo, 0, "Dead load D per floor", ("loads", "dead"), "kN/m",
                    tip="Bottom floor first, roof last. One value = same on every floor.")
        self._entry(lo, 2, "Live load L per floor", ("loads", "live"), "kN/m")
        self._entry(lo, 3, "Sustained part of live load ψ", ("loads", "psi_sustained"), "0–1",
                    tip="Consolidation is driven by the sustained load D + ψ·L.")

        c = ttk.LabelFrame(f, text="Design combination  γD·D + γL·L + γS·S(t)", padding=6)
        c.pack(fill="x", padx=4, pady=4)
        self._entry(c, 0, "γD (dead)", ("loads", "gamma_D"))
        self._entry(c, 1, "γL (live)", ("loads", "gamma_L"))
        self._entry(c, 2, "γS (settlement)", ("loads", "gamma_S"),
                    tip="Set all three to 1.0 for a service-level check.")
        ttk.Button(f, text="Update preview", command=self.update_previews).pack(anchor="w", padx=8, pady=6)

        self.preview = PlotPanel(tab, figsize=(8, 6))
        self.preview.pack(side="left", fill="both", expand=True, padx=4, pady=4)

    def _build_tab_footings(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="  2  Footings & soil  ")
        top = ttk.Frame(tab, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="One row per footing, left to right. Depths are below the ground surface. "
                            "The clay layer consolidates; soil above and below it drains freely.",
                  style="Note.TLabel").pack(side="left")
        ttk.Button(top, text="Update soil profile", command=self.update_previews).pack(side="right")
        ttk.Button(top, text="Copy F1 to all", command=self.copy_first_footing).pack(side="right", padx=4)

        self.foot_grid = ttk.Frame(tab, padding=(6, 0))
        self.foot_grid.pack(fill="x")
        self.soil_plot = PlotPanel(tab, figsize=(10, 4.5))
        self.soil_plot.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_footing_rows(self, rows):
        for w in self.foot_grid.winfo_children():
            w.destroy()
        ttk.Label(self.foot_grid, text="Footing", style="Head.TLabel").grid(row=0, column=0, padx=3, pady=2)
        for c, (key, head, width) in enumerate(FOOT_COLS, start=1):
            ttk.Label(self.foot_grid, text=head, style="Head.TLabel").grid(row=0, column=c, padx=3, pady=2)
        self.footing_rows = []
        for r, fd in enumerate(rows, start=1):
            ttk.Label(self.foot_grid, text=f"F{r}", style="Head.TLabel").grid(row=r, column=0, padx=3)
            row = {}
            for c, (key, head, width) in enumerate(FOOT_COLS, start=1):
                if key == "drainage":
                    v = tk.StringVar(value=fd.get(key, DRAINAGE_OPTIONS[0]))
                    ttk.Combobox(self.foot_grid, textvariable=v, values=DRAINAGE_OPTIONS, state="readonly",
                                 width=width).grid(row=r, column=c, padx=2, pady=1)
                elif key == "drawdown":
                    v = tk.BooleanVar(value=bool(fd.get(key, False)))
                    ttk.Checkbutton(self.foot_grid, variable=v).grid(row=r, column=c, padx=2)
                else:
                    v = tk.StringVar(value=f"{float(fd.get(key, DEFAULT_FOOTING[key])):g}")
                    ttk.Entry(self.foot_grid, textvariable=v, width=width, justify="right").grid(
                        row=r, column=c, padx=2, pady=1)
                row[key] = v
            self.footing_rows.append(row)

    def _build_tab_ground(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="  3  Groundwater & time  ")
        f = ttk.Frame(tab, padding=8)
        f.pack(fill="both", expand=True)
        u = ttk.LabelFrame(f, text="Soil unit weights", padding=6)
        u.grid(row=0, column=0, sticky="nwe", padx=4, pady=4)
        self._entry(u, 0, "Unit weight above water table γ", ("soil", "gamma"), "kN/m³")
        self._entry(u, 1, "Saturated unit weight γsat", ("soil", "gamma_sat"), "kN/m³")
        w = ttk.LabelFrame(f, text="Groundwater", padding=6)
        w.grid(row=1, column=0, sticky="nwe", padx=4, pady=4)
        self._entry(w, 0, "Initial water table depth", ("soil", "wt_depth"), "m")
        self._entry(w, 1, "Drawdown (drop of water table)", ("soil", "drawdown"), "m",
                    tip="0 = no drawdown. Mark the affected footings in tab 2. The lowered water table "
                        "must stay above the clay layer.")
        self._entry(w, 3, "Drawdown happens at", ("soil", "drawdown_time"), "years")
        t = ttk.LabelFrame(f, text="Time and numerical settings", padding=6)
        t.grid(row=0, column=1, rowspan=2, sticky="nwe", padx=4, pady=4)
        self._entry(t, 0, "Analysis period", ("time", "t_end"), "years")
        self._entry(t, 1, "Construction period", ("time", "t_construction"), "years",
                    tip="The sustained load is applied linearly over this period (0 = all at once).")
        self._entry(t, 3, "Number of time steps", ("time", "n_steps"), "",
                    tip="Steps are spaced logarithmically in time; extra steps are added after the drawdown.")
        self._entry(t, 5, "Clay sublayers", ("time", "n_sub"), "",
                    tip="Finite-difference sublayers per clay layer (40–100 is plenty).")
        ttk.Label(f, text="Only the sustained load (D + ψ·L) and the drawdown consolidate the clay. "
                          "The drawdown adds a uniform effective-stress increase to the clay under the "
                          "footings marked in tab 2, starting at the drawdown time.",
                  style="Note.TLabel", wraplength=820, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=8)

    def _build_tab_results(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="  4  Results  ")
        self.results_tab = tab
        side = ttk.Frame(tab, padding=6, width=300)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        box = ttk.LabelFrame(side, text="Results shown for", padding=6)
        box.pack(fill="x", pady=4)
        self.mode = tk.StringVar(value="Coupled")
        ttk.Radiobutton(box, text="Coupled (soil–structure interaction)", value="Coupled", variable=self.mode,
                        command=self.refresh_results).pack(anchor="w")
        ttk.Radiobutton(box, text="Uncoupled (rigid-support loads)", value="Uncoupled",
                        variable=self.mode, command=self.refresh_results).pack(anchor="w")

        box = ttk.LabelFrame(side, text="Time", padding=6)
        box.pack(fill="x", pady=4)
        self.t_label = tk.StringVar(value="t = –")
        ttk.Label(box, textvariable=self.t_label, font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.t_scale = ttk.Scale(box, from_=0, to=1, orient="horizontal", command=self._on_scale)
        self.t_scale.pack(fill="x", pady=4)
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Button(row, text="◀", width=3, command=lambda: self._step_time(-1)).pack(side="left")
        ttk.Button(row, text="▶", width=3, command=lambda: self._step_time(1)).pack(side="left", padx=2)
        ttk.Button(row, text="Before drawdown", command=self._goto_drawdown).pack(side="left", padx=2)
        ttk.Button(row, text="End", width=5, command=lambda: self._goto(len(self.results.t) - 1)
                   if self.results else None).pack(side="left")
        self.logx = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="Log time axis", variable=self.logx, command=self.refresh_results).pack(anchor="w")

        box = ttk.LabelFrame(side, text="Frame diagram", padding=6)
        box.pack(fill="x", pady=4)
        self.case_name = tk.StringVar(value=CASES[0][0])
        ttk.Combobox(box, textvariable=self.case_name, values=[c[0] for c in CASES], state="readonly").pack(fill="x")
        self.case_name.trace_add("write", lambda *a: self.refresh_results())
        self.show_def = tk.BooleanVar(value=True)
        self.show_val = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="Show deformed shape (magnified)", variable=self.show_def,
                        command=self.refresh_results).pack(anchor="w")
        ttk.Checkbutton(box, text="Label moment values (kN·m)", variable=self.show_val,
                        command=self.refresh_results).pack(anchor="w")

        box = ttk.LabelFrame(side, text="Summary", padding=4)
        box.pack(fill="both", expand=True, pady=4)
        self.summary = tk.Text(box, wrap="word", height=12, width=34, font=("TkFixedFont", 9), relief="flat",
                               background="#FAFAFA")
        self.summary.pack(fill="both", expand=True)

        self.rnb = ttk.Notebook(tab)
        self.rnb.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.p_frame = PlotPanel(self.rnb)
        self.p_settle = PlotPanel(self.rnb)
        self.p_loads = PlotPanel(self.rnb)
        self.p_beta = PlotPanel(self.rnb)
        self.p_mom = PlotPanel(self.rnb)
        for p, name in ((self.p_frame, "Frame & moments"), (self.p_settle, "Settlement vs time"),
                        (self.p_loads, "Footing loads vs time"), (self.p_beta, "Angular distortion"),
                        (self.p_mom, "Moment change vs time")):
            self.rnb.add(p, text=f"  {name}  ")
        tables = ttk.Frame(self.rnb)
        self.rnb.add(tables, text="  Tables  ")
        self.tbl_foot = self._make_table(tables, ("Footing", "Settlement (mm)", "Load now (kN)",
                                                  "Rigid-support load (kN)", "Change (%)",
                                                  "Final drained settlement (mm)"), height=6, expand=False)
        self.tbl_mem = self._make_table(tables, ("Member", "End", "D (kN·m)", "L (kN·m)", "S(t) (kN·m)",
                                                 "Combination (kN·m)"), height=18)

    def _make_table(self, parent, cols, height, expand=True):
        fr = ttk.Frame(parent)
        fr.pack(fill="both" if expand else "x", expand=expand, padx=4, pady=4)
        tv = ttk.Treeview(fr, columns=cols, show="headings", height=height)
        for c in cols:
            tv.heading(c, text=c)
            wid = 230 if c == "Member" else (90 if c in ("End", "Footing") else 160)
            tv.column(c, width=wid, minwidth=60, anchor="w" if c in ("Member", "End", "Footing") else "e")
        vsb = ttk.Scrollbar(fr, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vsb.set)
        tv.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return tv

    # ================================================================ inputs <-> widgets
    def set_inputs(self, inp):
        for (grp, key), var in self.vars.items():
            val = inp[grp].get(key, "")
            if isinstance(val, (list, tuple)):
                var.set(", ".join(f"{float(v):g}" for v in val))
            elif isinstance(val, float):
                var.set(f"{val:g}")
            else:
                var.set(str(val))
        self._build_footing_rows(inp["footings"])

    def _num(self, path, kind=float):
        txt = self.vars[path].get().strip()
        try:
            return kind(float(txt)) if kind is int else kind(txt)
        except ValueError:
            raise ValueError(f"'{txt}' is not a valid number for {path[1]}.")

    def _list(self, path):
        txt = self.vars[path].get().replace(";", ",")
        try:
            vals = [float(v) for v in txt.split(",") if v.strip()]
        except ValueError:
            raise ValueError(f"Could not read the list '{txt}' for {path[1]}. Use comma-separated numbers.")
        if not vals:
            raise ValueError(f"The list for {path[1]} is empty.")
        return vals

    def read_inputs(self) -> dict:
        inp = example_inputs()
        fr = inp["frame"]
        fr["bays"] = self._list(("frame", "bays"))
        fr["stories"] = self._list(("frame", "stories"))
        fr["base"] = self.vars[("frame", "base")].get()
        for k in ("E_GPa", "col_b", "col_h", "beam_b", "beam_h", "col_Ifactor", "beam_Ifactor"):
            fr[k] = self._num(("frame", k))
        ld = inp["loads"]
        ld["dead"] = self._list(("loads", "dead"))
        ld["live"] = self._list(("loads", "live"))
        for k in ("psi_sustained", "gamma_D", "gamma_L", "gamma_S"):
            ld[k] = self._num(("loads", k))
        for k in ("gamma", "gamma_sat", "wt_depth", "drawdown", "drawdown_time"):
            inp["soil"][k] = self._num(("soil", k))
        tm = inp["time"]
        tm["t_end"] = self._num(("time", "t_end"))
        tm["t_construction"] = self._num(("time", "t_construction"))
        tm["n_steps"] = self._num(("time", "n_steps"), int)
        tm["n_sub"] = self._num(("time", "n_sub"), int)
        foots = []
        for r, row in enumerate(self.footing_rows, start=1):
            fd = {}
            for key, head, _ in FOOT_COLS:
                v = row[key].get()
                if key in ("drainage", "drawdown"):
                    fd[key] = v
                else:
                    try:
                        fd[key] = float(v)
                    except ValueError:
                        raise ValueError(f"Footing F{r}: '{v}' is not a valid number for {head}.")
            foots.append(fd)
        inp["footings"] = foots
        return inp

    def sync_footing_rows(self):
        """Make the number of footing rows match the number of columns in the frame."""
        try:
            n = len(self._list(("frame", "bays"))) + 1
        except ValueError:
            return
        if n == len(self.footing_rows):
            return
        current = []
        for row in self.footing_rows:
            fd = {}
            for key, *_ in FOOT_COLS:
                v = row[key].get()
                if key in ("drainage", "drawdown"):
                    fd[key] = v
                else:
                    try:
                        fd[key] = float(v)
                    except ValueError:
                        fd[key] = DEFAULT_FOOTING[key]
            current.append(fd)
        if not current:
            current = [dict(DEFAULT_FOOTING)]
        while len(current) < n:
            current.append(dict(current[-1]))
        self._build_footing_rows(current[:n])
        self.status.set(f"Footing table changed to {n} footings to match the frame.")

    def copy_first_footing(self):
        """Copy every value of footing F1 to the other footings."""
        if not self.footing_rows:
            return
        first = {key: var.get() for key, var in self.footing_rows[0].items()}
        for row in self.footing_rows[1:]:
            for key, var in row.items():
                var.set(first[key])
        self.update_previews()
        self.status.set("Copied F1 to all footings.")

    # ================================================================ actions
    def _on_tab_changed(self, _evt=None):
        if self.nb.index("current") == 1:
            self.sync_footing_rows()
            self.update_previews()

    def update_previews(self):
        self.sync_footing_rows()
        try:
            inp = self.read_inputs()
        except ValueError as e:
            self.status.set(str(e))
            return
        try:
            pl.plot_frame_preview(self.preview.ax, inp)
            self.preview.draw()
        except Exception as e:  # preview only; errors are reported on Run
            self.status.set(f"Preview not updated: {e}")
        try:
            pl.plot_soil_profile(self.soil_plot.ax, inp)
            self.soil_plot.draw()
        except Exception as e:
            self.status.set(f"Soil profile not updated: {e}")

    def load_example(self):
        self.set_inputs(example_inputs())
        self.update_previews()
        self.status.set("Example loaded: 3-bay, 2-story frame; F2 over thicker clay; F3–F4 affected by drawdown.")

    def open_inputs(self):
        path = filedialog.askopenfilename(filetypes=[("SettleFrame inputs", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.set_inputs(load_inputs(path))
            self.update_previews()
            self.status.set(f"Opened {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Open inputs", f"Could not open the file:\n{e}")

    def save_inputs(self):
        try:
            inp = self.read_inputs()
        except ValueError as e:
            messagebox.showerror("Save inputs", str(e))
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("SettleFrame inputs", "*.json")])
        if path:
            save_inputs(inp, path)
            self.status.set(f"Saved {os.path.basename(path)}")

    def run(self):
        self.sync_footing_rows()
        try:
            inp = self.read_inputs()
            warnings = check_inputs(inp)
        except ValueError as e:
            messagebox.showerror("Check inputs", str(e))
            return
        self.config(cursor="watch")
        self.status.set("Running analysis…")
        self.update_idletasks()
        try:
            self.results = run_analysis(inp)
        except Exception as e:
            self.config(cursor="")
            messagebox.showerror("Analysis failed", f"{e}\n\n{traceback.format_exc(limit=2)}")
            self.status.set("Analysis failed.")
            return
        self.config(cursor="")
        r = self.results
        self.t_scale.configure(from_=0, to=len(r.t) - 1)
        self._goto(len(r.t) - 1, refresh=False)
        self.nb.select(self.results_tab)
        self.refresh_results()
        it_c = int(r.hist["Coupled"].iters.max())
        msg = f"Analysis finished: {len(r.t) - 1} time steps, at most {it_c} Newton iterations per step."
        if warnings or r.warnings:
            msg += "  Warnings: " + " ".join(sorted(set(warnings + r.warnings)))
        self.status.set(msg)

    # ---- time control
    def _on_scale(self, val):
        if not self.results:
            return
        it = int(round(float(val)))
        if it != self.it:
            self.it = it
            self.refresh_results()

    def _goto(self, it, refresh=True):
        if not self.results:
            return
        self.it = int(np.clip(it, 0, len(self.results.t) - 1))
        self.t_scale.set(self.it)
        if refresh:
            self.refresh_results()

    def _step_time(self, d):
        if self.results:
            self._goto(self.it + d)

    def _goto_drawdown(self):
        if not self.results:
            return
        tw = float(self.results.inputs["soil"]["drawdown_time"])
        k = int(np.searchsorted(self.results.t, tw)) - 1
        self._goto(max(k, 0))

    # ---- results display
    def _case_key(self):
        return dict(CASES)[self.case_name.get()]

    def refresh_results(self):
        r = self.results
        if r is None:
            return
        it, mode, logx = self.it, self.mode.get(), self.logx.get()
        self.t_label.set(f"t = {r.t[it]:.3g} years   (step {it} of {len(r.t) - 1})")
        pl.plot_frame(self.p_frame.ax, r, self._case_key(), mode, it, pl.GUI_STYLE, self.show_def.get(),
                      self.show_val.get())
        self.p_frame.draw()
        pl.plot_settlement(self.p_settle.ax, r, pl.GUI_STYLE, it, logx)
        self.p_settle.draw()
        pl.plot_loads(self.p_loads.ax, r, pl.GUI_STYLE, it, logx)
        self.p_loads.draw()
        pl.plot_distortion(self.p_beta.ax, r, mode, pl.GUI_STYLE, it, logx)
        self.p_beta.draw()
        pl.plot_moment_history(self.p_mom.ax, r, mode, pl.GUI_STYLE, it, logx)
        self.p_mom.draw()
        self._fill_tables()
        self._fill_summary()

    def _fill_tables(self):
        r, it, mode = self.results, self.it, self.mode.get()
        h = r.hist[mode]
        for tv in (self.tbl_foot, self.tbl_mem):
            tv.delete(*tv.get_children())
        rigid = r.rigid_loads(it)
        for k in range(r.nf):
            ch = 100 * (h.P[it, k] - rigid[k]) / rigid[k] if abs(rigid[k]) > 1e-9 else 0.0
            self.tbl_foot.insert("", "end", values=(f"F{k + 1}", f"{1000 * h.s[it, k]:.2f}", f"{h.P[it, k]:.1f}",
                                                    f"{rigid[k]:.1f}", f"{ch:+.1f}", f"{1000 * h.s_final[k]:.2f}"))
        cases = [r.case("D", mode, it).end_moments(), r.case("L", mode, it).end_moments(),
                 r.case("S", mode, it).end_moments(), r.case("Combo", mode, it).end_moments()]
        for k, m in enumerate(r.frame.members):
            for e in (0, 1):
                self.tbl_mem.insert("", "end", values=(m.label, m.end_names[e]) + tuple(f"{c[k, e]:.1f}" for c in cases))

    def _fill_summary(self):
        r, it, mode = self.results, self.it, self.mode.get()
        h = r.hist[mode]
        s = 1000 * h.s[it]
        beta = r.angular_distortion(mode)
        b_now = np.abs(beta[it])
        Mh = r.end_moment_history(mode)
        Ms_now = np.abs(Mh[it])
        kk, ee = np.unravel_index(np.argmax(Ms_now), Ms_now.shape)
        Mpk = np.abs(Mh).max(axis=(1, 2))
        ipk = int(np.argmax(Mpk))
        bpk = np.abs(beta).max(axis=1)
        ib = int(np.argmax(bpk))
        MD = r.case_D.max_abs_moment()

        def inv(b):
            return "–" if b < 1e-12 else f"1/{1 / b:.0f}"

        lines = [
            f"{mode} analysis",
            f"At t = {r.t[it]:.3g} yr:",
            f"  settlements (mm): " + ", ".join(f"{v:.1f}" for v in s),
            f"  max differential: {np.max(np.abs(np.diff(s))):.1f} mm",
            f"  max angular distortion: {inv(b_now.max())}",
            f"  max |moment from settlement|:",
            f"    {Ms_now[kk, ee]:.0f} kN·m",
            f"    {r.frame.members[kk].label}, {r.frame.members[kk].end_names[ee]}",
            "",
            "Over the whole period:",
            f"  peak |moment from settlement|: {Mpk[ipk]:.0f} kN·m at t = {r.t[ipk]:.3g} yr",
            f"  peak angular distortion: {inv(bpk[ib])} at t = {r.t[ib]:.3g} yr",
            f"  max |dead-load moment|: {MD:.0f} kN·m",
            f"  Newton iterations/step: ≤ {int(h.iters.max())}",
        ]
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", "\n".join(lines))
        self.summary.configure(state="disabled")

    # ---- exports
    def export_figures(self):
        if not self.results:
            messagebox.showinfo("Export figures", "Run the analysis first.")
            return
        folder = filedialog.askdirectory(title="Folder for the figures")
        if not folder:
            return
        files = pl.export_figures(self.results, folder, self.mode.get(), self.it, self._case_key(),
                                  self.logx.get(), self.show_def.get(), self.show_val.get())
        pl.apply_rc()
        self.status.set(f"Saved {len(files)} figures (slide style, 300 dpi) to {folder}")

    def export_csv(self):
        if not self.results:
            messagebox.showinfo("Export results", "Run the analysis first.")
            return
        folder = filedialog.askdirectory(title="Folder for the CSV files")
        if not folder:
            return
        r, it, mode = self.results, self.it, self.mode.get()
        nf = r.nf
        with open(os.path.join(folder, "time_history.csv"), "w", newline="") as f:
            w = csv.writer(f)
            head = ["time_yr"]
            for m in ("coupled", "uncoupled"):
                head += [f"s_F{k + 1}_{m}_mm" for k in range(nf)] + [f"P_F{k + 1}_{m}_kN" for k in range(nf)]
            w.writerow(head)
            for n, t in enumerate(r.t):
                row = [f"{t:.6g}"]
                for m in ("Coupled", "Uncoupled"):
                    row += [f"{1000 * v:.4f}" for v in r.hist[m].s[n]] + [f"{v:.3f}" for v in r.hist[m].P[n]]
                w.writerow(row)
        with open(os.path.join(folder, f"member_moments_{mode.lower()}_t{r.t[it]:.3g}yr.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["member", "end", "D_kNm", "L_kNm", "S_kNm", "combination_kNm"])
            cases = [r.case(c, mode, it).end_moments() for c in ("D", "L", "S", "Combo")]
            for k, m in enumerate(r.frame.members):
                for e in (0, 1):
                    w.writerow([m.label, m.end_names[e]] + [f"{c[k, e]:.3f}" for c in cases])
        self.status.set(f"Saved time_history.csv and member moments at t = {r.t[it]:.3g} yr to {folder}")

    def show_help(self):
        win = tk.Toplevel(self)
        win.title("SettleFrame help")
        txt = tk.Text(win, wrap="word", width=80, height=34, font=("TkFixedFont", 10))
        txt.insert("1.0", HELP_TEXT)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, padx=8, pady=8)


def main():
    app = SettleFrameApp()
    app.mainloop()


if __name__ == "__main__":
    main()
