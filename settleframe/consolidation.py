"""One-dimensional consolidation of the clay layer under one footing.

The clay layer is divided into sublayers. Excess pore water pressure u(z, t) follows
Terzaghi's 1D consolidation equation with a time-varying applied stress:

    du/dt = cv * d2u/dz2 + d(delta_sigma)/dt

solved by implicit (backward Euler) finite differences, so any time step is stable.
Effective stress is  sigma' = sigma'_0 + delta_sigma - u,  and the vertical strain of
each sublayer follows the e-log(sigma') relation (Cr below the preconsolidation
pressure, Cc above it). Settlement is the strain integrated over the layer.

Stress increase from the footing load uses the 2:1 (2 vertical : 1 horizontal) spread.
A lowered water table adds a uniform effective-stress increase to the clay.

Units: kN, m, kPa, years (cv in m^2/year).
"""
from __future__ import annotations

import numpy as np

GAMMA_W = 9.81  # unit weight of water (kN/m^3)


def terzaghi_U(Tv) -> np.ndarray:
    """Average degree of consolidation for a uniform initial excess pore pressure
    (Terzaghi series solution). Tv = cv * t / Hdr^2, where Hdr is the drainage path."""
    Tv = np.atleast_1d(np.asarray(Tv, float))
    U = np.zeros_like(Tv)
    m = np.arange(0, 400)
    M = np.pi * (2 * m + 1) / 2.0
    for k, T in enumerate(Tv):
        if T <= 0:
            U[k] = 0.0
        else:
            U[k] = 1.0 - np.sum(2.0 / M**2 * np.exp(-M**2 * T))
    return U


def geostatic_effective_stress(z, gamma, gamma_sat, wt_depth):
    """Initial vertical effective stress (kPa) at depth z (m) below the ground surface."""
    z = np.asarray(z, float)
    above = np.minimum(z, wt_depth)
    below = np.maximum(z - wt_depth, 0.0)
    total = gamma * above + gamma_sat * below
    return total - GAMMA_W * below


def drawdown_stress(drop, gamma, gamma_sat):
    """Effective-stress increase (kPa) in the clay when the water table drops by `drop` (m),
    with the new water table still above the clay: the pore pressure falls by gamma_w*drop and
    the drained soil above loses its buoyancy (total stress changes by (gamma - gamma_sat)*drop)."""
    return drop * (GAMMA_W + gamma - gamma_sat)


class ClayColumn:
    """Clay layer under one footing, with its consolidation state.

    Parameters
    ----------
    B, L      : footing plan dimensions (m)
    Df        : depth of footing base below ground surface (m)
    z_top     : depth of the top of the clay layer below ground surface (m), z_top >= Df
    H         : clay thickness (m)
    Cc, Cr    : compression and recompression indices
    e0        : initial void ratio
    OCR       : overconsolidation ratio (sigma'_p / sigma'_0), >= 1
    cv        : coefficient of consolidation (m^2/year)
    drainage  : "both" (drains at top and bottom) or "top" (impermeable base)
    gamma, gamma_sat : soil unit weights above / below the water table (kN/m^3)
    wt_depth  : initial water table depth (m)
    n_sub     : number of sublayers used in the finite-difference solution
    """

    def __init__(self, B, L, Df, z_top, H, Cc, Cr, e0, OCR, cv, drainage,
                 gamma, gamma_sat, wt_depth, n_sub=40):
        self.B, self.L, self.Df = float(B), float(L), float(Df)
        self.z_top, self.H = float(z_top), float(H)
        self.Cc, self.Cr, self.e0, self.OCR = float(Cc), float(Cr), float(e0), float(OCR)
        self.cv = float(cv)
        self.drainage = "both" if str(drainage).lower().startswith(("both", "top &", "top and")) else "top"
        self.n = int(n_sub)
        self.z = np.linspace(self.z_top, self.z_top + self.H, self.n + 1)   # node depths
        self.dz = self.H / self.n
        self.sig0 = geostatic_effective_stress(self.z, gamma, gamma_sat, wt_depth)
        if np.any(self.sig0 <= 0):
            raise ValueError("Initial effective stress in the clay must be positive (clay top must be below ground).")
        self.sigp = self.OCR * self.sig0
        zb = self.z - self.Df                       # depth below footing base
        self.infl = 1.0 / ((self.B + zb) * (self.L + zb))   # 2:1 method: delta_sigma = P * infl
        self.reset()

    # ---- state ---------------------------------------------------------------
    def reset(self):
        self.u = np.zeros(self.n + 1)       # excess pore water pressure (kPa)
        self.dsig = np.zeros(self.n + 1)    # applied stress increase (kPa)

    def applied_stress(self, P, dsig_w=0.0):
        """Stress increase in the clay from footing load P (kN) plus a drawdown increase (kPa)."""
        return P * self.infl + dsig_w

    # ---- constitutive relation -----------------------------------------------
    def strain(self, sig_eff):
        """Vertical strain (compression +) from sigma'_0 to sig_eff, e-log(sigma') model."""
        se = np.maximum(sig_eff, 1e-3)
        s0, sp = self.sig0, self.sigp
        eps = np.where(
            se <= sp,
            self.Cr * np.log10(se / s0),
            self.Cr * np.log10(sp / s0) + self.Cc * np.log10(se / sp),
        )
        return eps / (1.0 + self.e0)

    def settlement_of(self, u, dsig) -> float:
        eps = self.strain(self.sig0 + dsig - u)
        return float(np.sum(0.5 * (eps[:-1] + eps[1:]) * self.dz))

    def final_settlement(self, P, dsig_w=0.0) -> float:
        """Settlement after all excess pore pressure has drained (u = 0)."""
        return self.settlement_of(np.zeros(self.n + 1), self.applied_stress(P, dsig_w))

    # ---- time stepping -------------------------------------------------------
    def _system_inverse(self, dt):
        """Inverse of the backward-Euler matrix for step dt (cached: Newton iterations reuse it)."""
        if getattr(self, "_dt_cached", None) == dt:
            return self._Ainv
        n = self.n
        r = self.cv * dt / self.dz**2
        A = np.zeros((n + 1, n + 1))
        j = np.arange(1, n)
        A[j, j - 1] = -r
        A[j, j] = 1 + 2 * r
        A[j, j + 1] = -r
        A[0, 0] = 1.0                    # top drains: u = 0
        if self.drainage == "both":
            A[n, n] = 1.0                # bottom drains: u = 0
        else:                            # impermeable base: du/dz = 0 (mirror node)
            A[n, n - 1] = -2 * r
            A[n, n] = 1 + 2 * r
        self._Ainv = np.linalg.inv(A)
        self._dt_cached = dt
        return self._Ainv

    def _step_u(self, dt, dsig_new):
        """Backward-Euler step of the excess pore pressure."""
        b = self.u + (dsig_new - self.dsig)
        b[0] = 0.0
        if self.drainage == "both":
            b[-1] = 0.0
        return self._system_inverse(dt) @ b

    def average_excess_pressure(self) -> float:
        """Depth-averaged excess pore water pressure (kPa)."""
        return float(np.sum(0.5 * (self.u[:-1] + self.u[1:]) * self.dz) / self.H)

    def trial(self, P, dsig_w, dt) -> float:
        """Settlement at the end of a time step of length dt (years) under footing load P,
        without changing the stored state."""
        dsig_new = self.applied_stress(P, dsig_w)
        u_new = self._step_u(dt, dsig_new)
        return self.settlement_of(u_new, dsig_new)

    def commit(self, P, dsig_w, dt) -> float:
        dsig_new = self.applied_stress(P, dsig_w)
        self.u = self._step_u(dt, dsig_new)
        self.dsig = dsig_new
        return self.settlement_of(self.u, self.dsig)

    @property
    def drainage_path(self) -> float:
        return self.H / 2.0 if self.drainage == "both" else self.H
