"""Plots shared by the GUI and the figure export.

Two styles: GUI_STYLE for the on-screen window, and SLIDE_STYLE for exported figures
(Times New Roman, 21 pt tick labels, 23 pt bold axis titles, ~20 pt legend,
2.9 pt data lines, 1.9 pt frame, inward ticks).
"""
from __future__ import annotations

import os

import matplotlib
import numpy as np
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon, Rectangle

PURPLE = "#461D7C"
GOLD = "#D99A00"
PALETTE = ["#461D7C", "#D99A00", "#1F77B4", "#C0392B", "#2E8B57", "#7F7F7F", "#8E44AD", "#D35400",
           "#17BECF", "#6B4226"]
SERIF = ["Times New Roman", "Liberation Serif", "Nimbus Roman", "DejaVu Serif"]

GUI_STYLE = {"tick": 9, "label": 10.5, "legend": 8.5, "title": 10.5, "text": 8.5, "lw": 1.8, "frame": 1.0,
             "ticklen": 4}
SLIDE_STYLE = {"tick": 21, "label": 23, "legend": 20, "title": 23, "text": 17, "lw": 2.9, "frame": 1.9,
               "ticklen": 8}

CASE_NAMES = {
    "S": "Settlement effect S(t)",
    "D": "Dead load D",
    "L": "Live load L",
    "Combo": "Combination",
}


def apply_rc():
    matplotlib.rcParams.update({"font.family": "serif", "font.serif": SERIF, "mathtext.fontset": "stix",
                                "axes.unicode_minus": False})


def style_axes(ax, st):
    for sp in ax.spines.values():
        sp.set_linewidth(st["frame"])
    ax.tick_params(direction="in", which="both", labelsize=st["tick"], width=st["frame"], top=True, right=True)
    ax.tick_params(which="major", length=st["ticklen"])
    ax.tick_params(which="minor", length=st["ticklen"] * 0.55)
    ax.xaxis.label.set_fontsize(st["label"])
    ax.yaxis.label.set_fontsize(st["label"])
    ax.xaxis.label.set_fontweight("bold")
    ax.yaxis.label.set_fontweight("bold")


def _time_axis(ax, res, logx):
    t = res.t
    if logx:
        ax.set_xscale("log")
        ax.set_xlim(max(t[1], 1e-3), t[-1])
    else:
        ax.set_xlim(0, t[-1])
    ax.set_xlabel("Time (years)")


def _time_slice(res, logx):
    return slice(1, None) if logx else slice(0, None)


def _markers(ax, res, it, st):
    so = res.inputs["soil"]
    if float(so["drawdown"]) > 0 and any(fd.get("drawdown") for fd in res.inputs["footings"]):
        ax.axvline(float(so["drawdown_time"]), color="#1F77B4", lw=st["frame"], ls=":", zorder=1)
    if it is not None and it > 0:
        ax.axvline(res.t[it], color="black", lw=st["frame"] * 0.8, ls="--", zorder=1)


# ------------------------------------------------------------------ frame diagram
def plot_frame(ax, res, case, mode, it, st=GUI_STYLE, deformed=True, values=True):
    ax.clear()
    frame, meta = res.frame, res.meta
    x, y = meta["x"], meta["y"]
    size = max(x[-1], y[-1])
    fh = 0.06 * size
    ground = -fh

    # ground, footings
    ax.add_patch(Rectangle((x[0] - 0.12 * size, ground - 0.10 * size), x[-1] + 0.24 * size, 0.10 * size,
                           facecolor="#EDEDED", edgecolor="none", hatch="///", zorder=0))
    ax.plot([x[0] - 0.12 * size, x[-1] + 0.12 * size], [ground, ground], color="#555555", lw=st["frame"], zorder=1)
    s_now = res.hist[mode].s[it]
    for k, (xc, fd) in enumerate(zip(x, res.inputs["footings"])):
        B = float(fd["B"])
        ax.add_patch(Rectangle((xc - B / 2, ground), B, fh, facecolor="#BDBDBD", edgecolor="#333333",
                               lw=st["frame"] * 0.8, zorder=3))
        ax.text(xc, ground - 0.13 * size, f"F{k + 1}\n{1000 * s_now[k]:.1f} mm", ha="center", va="top",
                fontsize=st["text"], color="#222222")

    fr = res.case(case, mode, it)
    for k, m in enumerate(frame.members):
        p, q = frame.nodes[m.i], frame.nodes[m.j]
        ax.plot([p[0], q[0]], [p[1], q[1]], color="#8C8C8C", lw=st["lw"] * 0.9, zorder=2, solid_capstyle="round")

    Mmax = fr.max_abs_moment()
    labels = []
    if Mmax > 1e-9:
        sc = 0.11 * size / Mmax
        for k, m in enumerate(frame.members):
            L, c, s, *_ = frame.geom[k]
            xs, M = fr.member_moment_diagram(k, 61)
            e = np.array([c, s])
            nrm = np.array([-s, c])
            base = frame.nodes[m.i][None, :] + xs[:, None] * e[None, :]
            off = base + (-M * sc)[:, None] * nrm[None, :]
            ax.add_patch(Polygon(np.vstack([base, off[::-1]]), closed=True, facecolor=PURPLE, alpha=0.22,
                                 edgecolor="none", zorder=4))
            ax.plot(off[:, 0], off[:, 1], color=PURPLE, lw=st["lw"] * 0.75, zorder=5)
            for idx in {0, len(xs) - 1, int(np.argmax(np.abs(M)))}:
                labels.append((abs(M[idx]), M[idx], off[idx]))
    if values and labels:
        labels.sort(key=lambda a: -a[0])
        placed = []
        for a, Mv, pos in labels:
            if a < 0.25 * Mmax or a < 0.5 or len(placed) >= 12:
                break
            if any(np.hypot(*(pos - p)) < 0.07 * size for p in placed):
                continue
            placed.append(pos)
            ax.text(pos[0], pos[1], f"{Mv:.0f}", fontsize=st["text"], color=PURPLE, ha="center", va="center",
                    zorder=7, bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))

    if deformed:
        dmax = 0.0
        for k in range(len(frame.members)):
            pts = fr.displaced_shape(k, 1.0) - fr.displaced_shape(k, 0.0)
            dmax = max(dmax, float(np.max(np.hypot(pts[:, 0], pts[:, 1]))))
        if dmax > 1e-12:
            scd = 0.06 * size / dmax
            for k in range(len(frame.members)):
                p = fr.displaced_shape(k, scd)
                ax.plot(p[:, 0], p[:, 1], color="#222222", lw=st["lw"] * 0.6, ls="--", zorder=6)

    ld = res.inputs["loads"]
    if case == "Combo":
        name = f"{ld['gamma_D']:g}D + {ld['gamma_L']:g}L + {ld['gamma_S']:g}S(t)"
    else:
        name = CASE_NAMES[case]
    when = "" if case in ("D", "L") else f"   |   t = {res.t[it]:.2f} yr   |   {mode}"
    ax.set_title(f"{name}{when}\nmax |M| = {Mmax:.0f} kN·m  (drawn on the tension side)",
                 fontsize=st["title"])
    ax.set_aspect("equal")
    ax.set_xlim(x[0] - 0.15 * size, x[-1] + 0.15 * size)
    ax.set_ylim(ground - 0.30 * size, y[-1] + 0.20 * size)
    ax.axis("off")


# ------------------------------------------------------------------ time histories
def _style_legend(ax, st, handles=None, labels=None, **kw):
    if handles is None:
        leg = ax.legend(fontsize=st["legend"], frameon=False, **kw)
    else:
        leg = ax.legend(handles, labels, fontsize=st["legend"], frameon=False, **kw)
    return leg


def plot_settlement(ax, res, st=GUI_STYLE, it=None, logx=True):
    ax.clear()
    sl = _time_slice(res, logx)
    t = res.t[sl]
    for k in range(res.nf):
        c = PALETTE[k % len(PALETTE)]
        ax.plot(t, 1000 * res.hist["Coupled"].s[sl, k], color=c, lw=st["lw"], label=f"F{k + 1}")
        ax.plot(t, 1000 * res.hist["Uncoupled"].s[sl, k], color=c, lw=st["lw"] * 0.6, ls="--")
    _markers(ax, res, it, st)
    _time_axis(ax, res, logx)
    ax.set_ylabel("Footing settlement (mm)")
    ax.set_ylim(bottom=0)
    ax.invert_yaxis()
    h, l = ax.get_legend_handles_labels()
    h += [Line2D([], [], color="black", lw=st["lw"]), Line2D([], [], color="black", lw=st["lw"] * 0.6, ls="--")]
    l += ["Coupled", "Uncoupled"]
    _style_legend(ax, st, h, l, loc="lower left", ncol=2)
    style_axes(ax, st)


def plot_loads(ax, res, st=GUI_STYLE, it=None, logx=True):
    ax.clear()
    sl = _time_slice(res, logx)
    t = res.t[sl]
    for k in range(res.nf):
        c = PALETTE[k % len(PALETTE)]
        ax.plot(t, res.hist["Coupled"].P[sl, k], color=c, lw=st["lw"], label=f"F{k + 1}")
        ax.plot(t, res.hist["Uncoupled"].P[sl, k], color=c, lw=st["lw"] * 0.6, ls="--")
    _markers(ax, res, it, st)
    _time_axis(ax, res, logx)
    ax.set_ylabel("Sustained footing load (kN)")
    ax.set_ylim(bottom=min(0.0, float(res.hist["Coupled"].P.min()) * 1.1))
    h, l = ax.get_legend_handles_labels()
    h += [Line2D([], [], color="black", lw=st["lw"]), Line2D([], [], color="black", lw=st["lw"] * 0.6, ls="--")]
    l += ["Coupled", "Uncoupled (rigid supports)"]
    _style_legend(ax, st, h, l, loc="best", ncol=2)
    style_axes(ax, st)


def plot_distortion(ax, res, mode, st=GUI_STYLE, it=None, logx=True):
    ax.clear()
    sl = _time_slice(res, logx)
    t = res.t[sl]
    beta = 1000 * res.angular_distortion(mode)[sl]
    lim = 1000 / 500
    ax.axhspan(-lim, lim, color="#E8F3E8", zorder=0, label="|β| < 1/500")
    for k in range(beta.shape[1]):
        ax.plot(t, beta[:, k], color=PALETTE[k % len(PALETTE)], lw=st["lw"], label=f"Bay {k + 1} (F{k + 1}–F{k + 2})")
    big = max(float(np.max(np.abs(beta))) * 1.15, lim * 1.3)
    if big > 1000 / 150:
        for sgn in (1, -1):
            ax.axhline(sgn * 1000 / 150, color="#C0392B", lw=st["frame"], ls="--")
        ax.text(t[0], 1000 / 150, " 1/150", color="#C0392B", va="bottom", fontsize=st["text"])
    ax.axhline(0, color="#555555", lw=st["frame"] * 0.6)
    _markers(ax, res, it, st)
    _time_axis(ax, res, logx)
    ax.set_ylim(-big, big)
    ax.set_ylabel(r"Angular distortion $\beta$ ($\times10^{-3}$)")
    _style_legend(ax, st, loc="best")
    style_axes(ax, st)
    ax.set_title(f"{mode}: β = (s right − s left) / bay width", fontsize=st["title"])


def top_member_ends(res, mode, n=4):
    M = res.end_moment_history(mode)               # (nt, nm, 2)
    peak = np.max(np.abs(M), axis=0)               # (nm, 2)
    order = np.argsort(peak.ravel())[::-1][:n]
    out = []
    for flat in order:
        k, e = divmod(int(flat), 2)
        m = res.frame.members[k]
        out.append((k, e, f"{m.label}, {m.end_names[e]}"))
    return out


def plot_moment_history(ax, res, mode, st=GUI_STYLE, it=None, logx=True, n=4):
    ax.clear()
    sl = _time_slice(res, logx)
    t = res.t[sl]
    other = "Uncoupled" if mode == "Coupled" else "Coupled"
    Mm = res.end_moment_history(mode)[sl]
    Mo = res.end_moment_history(other)[sl]
    for q, (k, e, name) in enumerate(top_member_ends(res, mode, n)):
        c = PALETTE[q % len(PALETTE)]
        ax.plot(t, Mm[:, k, e], color=c, lw=st["lw"], label=name)
        ax.plot(t, Mo[:, k, e], color=c, lw=st["lw"] * 0.6, ls="--")
    ax.axhline(0, color="#555555", lw=st["frame"] * 0.6)
    _markers(ax, res, it, st)
    _time_axis(ax, res, logx)
    ax.set_ylabel("Moment from settlement (kN·m)")
    h, l = ax.get_legend_handles_labels()
    h += [Line2D([], [], color="black", lw=st["lw"]), Line2D([], [], color="black", lw=st["lw"] * 0.6, ls="--")]
    l += [mode, other]
    _style_legend(ax, st, h, l, loc="best")
    style_axes(ax, st)


# ------------------------------------------------------------------ input previews
def plot_frame_preview(ax, inp, st=GUI_STYLE):
    from .model import per_floor
    ax.clear()
    fr = inp["frame"]
    x = np.concatenate([[0.0], np.cumsum(fr["bays"])])
    y = np.concatenate([[0.0], np.cumsum(fr["stories"])])
    size = max(x[-1], y[-1])
    ns = len(fr["stories"])
    try:
        dead = per_floor(inp["loads"]["dead"], ns, "Dead load")
        live = per_floor(inp["loads"]["live"], ns, "Live load")
    except ValueError:
        dead = live = None
    for xc in x:
        ax.plot([xc, xc], [0, y[-1]], color="#333333", lw=st["lw"])
    for l in range(1, len(y)):
        ax.plot([x[0], x[-1]], [y[l], y[l]], color="#333333", lw=st["lw"] * 1.3)
        if dead is not None:
            ax.text(x[-1] + 0.04 * size, y[l], f"D = {dead[l - 1]:g}\nL = {live[l - 1]:g} kN/m",
                    va="center", fontsize=st["text"], color=PURPLE)
        for b in range(len(x) - 1):
            xs = np.linspace(x[b] + 0.1, x[b + 1] - 0.1, 6)
            for xa in xs:
                ax.annotate("", xy=(xa, y[l] + 0.02 * size), xytext=(xa, y[l] + 0.09 * size),
                            arrowprops=dict(arrowstyle="-|>", color=GOLD, lw=0.8, mutation_scale=6))
    fh = 0.05 * size
    for k, xc in enumerate(x):
        ax.add_patch(Rectangle((xc - 0.08 * size, -fh), 0.16 * size, fh, facecolor="#BDBDBD", edgecolor="#333333"))
        ax.text(xc, -fh - 0.03 * size, f"F{k + 1}", ha="center", va="top", fontsize=st["text"] + 1, weight="bold")
    for b in range(len(x) - 1):
        ax.text((x[b] + x[b + 1]) / 2, -0.17 * size, f"{x[b + 1] - x[b]:g} m", ha="center", fontsize=st["text"])
    for l in range(1, len(y)):
        ax.text(x[0] - 0.04 * size, (y[l - 1] + y[l]) / 2, f"{y[l] - y[l - 1]:g} m", ha="right", va="center",
                fontsize=st["text"])
    base = str(fr.get("base", "Fixed"))
    ax.set_title(f"{len(x) - 1} bays × {ns} stories, {base.lower()} column bases", fontsize=st["title"])
    ax.set_aspect("equal")
    ax.set_xlim(x[0] - 0.2 * size, x[-1] + 0.3 * size)
    ax.set_ylim(-0.25 * size, y[-1] + 0.15 * size)
    ax.axis("off")


def plot_soil_profile(ax, inp, st=GUI_STYLE):
    ax.clear()
    so = inp["soil"]
    fds = inp["footings"]
    n = len(fds)
    zmax = max(float(fd["clay_top"]) + float(fd["H"]) for fd in fds) * 1.12
    w = 0.62
    ax.axhline(0, color="#333333", lw=st["frame"])
    ax.add_patch(Rectangle((-0.5, 0), n, zmax, facecolor="#F4EFE1", edgecolor="none", zorder=0))
    for k, fd in enumerate(fds):
        top, H, Df = float(fd["clay_top"]), float(fd["H"]), float(fd["Df"])
        ax.add_patch(Rectangle((k - w / 2, top), w, H, facecolor="#B9A27A", edgecolor="#6B5B3E", zorder=2))
        ax.add_patch(Rectangle((k - 0.22, Df - 0.5), 0.44, 0.5, facecolor="#9E9E9E", edgecolor="#333333", zorder=3))
        ax.plot([k, k], [0, Df - 0.5], color="#333333", lw=st["lw"], zorder=3)
        drn = "top & bottom" if fd["drainage"].startswith("Top &") else "top only"
        ax.text(k, top + H / 2, f"H = {H:g} m\nCc = {float(fd['Cc']):g}\nOCR = {float(fd['OCR']):g}\n"
                f"cv = {float(fd['cv']):g}\ndrains {drn}",
                ha="center", va="center", fontsize=st["text"] * 0.95, zorder=4)
        ax.text(k, -0.25, f"F{k + 1}", ha="center", va="bottom", fontsize=st["text"] + 1, weight="bold")
        if fd.get("drawdown") and float(so["drawdown"]) > 0:
            z2 = float(so["wt_depth"]) + float(so["drawdown"])
            ax.plot([k - 0.5, k + 0.5], [z2, z2], color="#1F77B4", lw=st["lw"], ls="--", zorder=5)
    ax.plot([-0.5, n - 0.5], [so["wt_depth"], so["wt_depth"]], color="#1F77B4", lw=st["lw"], zorder=5,
            label="Initial water table")
    if float(so["drawdown"]) > 0 and any(fd.get("drawdown") for fd in fds):
        ax.plot([], [], color="#1F77B4", lw=st["lw"], ls="--",
                label=f"Lowered water table (after {float(so['drawdown_time']):g} yr)")
    ax.add_patch(Rectangle((0, 0), 0, 0, facecolor="#B9A27A", edgecolor="#6B5B3E", label="Clay (consolidates)"))
    ax.add_patch(Rectangle((0, 0), 0, 0, facecolor="#F4EFE1", edgecolor="#999999", label="Sand (drains freely)"))
    ax.set_xlim(-0.5, n - 0.5)
    ax.set_ylim(zmax, -0.9)
    ax.set_xticks([])
    ax.set_ylabel("Depth below ground (m)")
    ax.legend(fontsize=st["legend"], loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.12))
    style_axes(ax, st)


# ------------------------------------------------------------------ export
def _figure(figsize):
    try:
        return Figure(figsize=figsize, layout="constrained")
    except TypeError:
        return Figure(figsize=figsize, constrained_layout=True)


def export_figures(res, folder, mode, it, case, logx=True, deformed=True, values=True):
    """Save every result plot as a 300-dpi PNG in slide style. Returns the list of files."""
    apply_rc()
    st = SLIDE_STYLE
    files = []

    def save(fig, name):
        path = os.path.join(folder, name)
        fig.savefig(path, dpi=300, facecolor="white")
        files.append(path)

    fig = _figure((13, 9))
    plot_frame(fig.add_subplot(111), res, case, mode, it, st, deformed, values)
    save(fig, f"frame_{case}_{mode.lower()}_t{res.t[it]:.2f}yr.png")
    for name, fn in (("settlement_vs_time.png", lambda ax: plot_settlement(ax, res, st, it, logx)),
                     ("footing_loads_vs_time.png", lambda ax: plot_loads(ax, res, st, it, logx)),
                     (f"angular_distortion_{mode.lower()}.png", lambda ax: plot_distortion(ax, res, mode, st, it, logx)),
                     (f"moment_change_{mode.lower()}.png", lambda ax: plot_moment_history(ax, res, mode, st, it, logx))):
        fig = _figure((11, 7.5))
        fn(fig.add_subplot(111))
        save(fig, name)
    return files
