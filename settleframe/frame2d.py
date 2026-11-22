"""Linear-elastic 2D frame analysis by the direct stiffness method.

Units used throughout SettleFrame: kN, m, kPa (= kN/m^2), kN*m.

Each node has three degrees of freedom (DOFs):
    ux (m, +right), uy (m, +up), rz (rad, counter-clockwise +).

Member end forces are reported in local axes for each element:
    [N_i, V_i, M_i, N_j, V_j, M_j]
where local x runs from node i to node j and local y is 90 deg counter-clockwise
from local x. End moments are counter-clockwise positive.

Internal bending moment along a member uses the "sagging positive" convention
(tension on the local -y face). For a horizontal beam drawn left to right this is
the usual convention: positive at midspan under gravity load, negative over supports.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Member:
    i: int            # start node
    j: int            # end node
    E: float          # elastic modulus (kPa)
    A: float          # area (m^2)
    I: float          # second moment of area (m^4)
    kind: str = "beam"   # "beam" or "column"
    label: str = ""
    end_names: tuple = ("i-end", "j-end")


def local_stiffness(E: float, A: float, I: float, L: float) -> np.ndarray:
    """6x6 stiffness matrix of a 2D Euler-Bernoulli frame element in local axes."""
    a = E * A / L
    b = 12.0 * E * I / L**3
    c = 6.0 * E * I / L**2
    d = 4.0 * E * I / L
    e = 2.0 * E * I / L
    return np.array([
        [a, 0, 0, -a, 0, 0],
        [0, b, c, 0, -b, c],
        [0, c, d, 0, -c, e],
        [-a, 0, 0, a, 0, 0],
        [0, -b, -c, 0, b, -c],
        [0, c, e, 0, -c, d],
    ], dtype=float)


def transformation(c: float, s: float) -> np.ndarray:
    """Global-to-local transformation matrix T (d_local = T @ d_global)."""
    R = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    T = np.zeros((6, 6))
    T[:3, :3] = R
    T[3:, 3:] = R
    return T


class FrameResult:
    """Results of one load case. Results combine linearly, e.g. 1.2*D + 1.6*L + S."""

    def __init__(self, frame: "Frame2D", d, reactions, end_forces, q_local):
        self.frame = frame
        self.d = np.asarray(d, float)                    # global displacements (ndof,)
        self.reactions = np.asarray(reactions, float)    # global reactions (ndof,), zero at free DOFs
        self.end_forces = np.asarray(end_forces, float)  # (n_members, 6) local end forces
        self.q_local = np.asarray(q_local, float)        # (n_members, 2) distributed load (qx, qy) local

    # ---- linear combination -------------------------------------------------
    def _combine(self, other, a=1.0, b=1.0):
        return FrameResult(self.frame, a * self.d + b * other.d, a * self.reactions + b * other.reactions,
                           a * self.end_forces + b * other.end_forces, a * self.q_local + b * other.q_local)

    def __add__(self, other):
        if isinstance(other, (int, float)) and other == 0:
            return self
        return self._combine(other)

    __radd__ = __add__

    def __mul__(self, k: float):
        return FrameResult(self.frame, k * self.d, k * self.reactions, k * self.end_forces, k * self.q_local)

    __rmul__ = __mul__

    # ---- internal forces ----------------------------------------------------
    def moment_along(self, k: int, x) -> np.ndarray:
        """Internal bending moment (sagging +) at distance x (m) from the i-end of member k."""
        f = self.end_forces[k]
        qy = self.q_local[k, 1]
        x = np.asarray(x, float)
        return -f[2] + f[1] * x + 0.5 * qy * x**2

    def member_moment_diagram(self, k: int, n: int = 41):
        L = self.frame.geom[k][0]
        x = np.linspace(0.0, L, n)
        return x, self.moment_along(k, x)

    def end_moments(self) -> np.ndarray:
        """Internal moments (sagging +) at both ends of every member, shape (n_members, 2)."""
        out = np.zeros((len(self.frame.members), 2))
        for k in range(len(self.frame.members)):
            L = self.frame.geom[k][0]
            out[k, 0] = self.moment_along(k, 0.0)
            out[k, 1] = self.moment_along(k, L)
        return out

    def max_abs_moment(self) -> float:
        m = 0.0
        for k in range(len(self.frame.members)):
            _, M = self.member_moment_diagram(k)
            m = max(m, float(np.max(np.abs(M))))
        return m

    def displaced_shape(self, k: int, scale: float, n: int = 31):
        """Exact cubic (Hermite) displaced shape of member k, magnified by `scale`."""
        L, c, s, _, T, dofs = self.frame.geom[k]
        dl = T @ self.d[dofs]
        u1, v1, t1, u2, v2, t2 = dl
        xi = np.linspace(0.0, 1.0, n)
        N1 = 1 - 3 * xi**2 + 2 * xi**3
        N2 = L * (xi - 2 * xi**2 + xi**3)
        N3 = 3 * xi**2 - 2 * xi**3
        N4 = L * (-xi**2 + xi**3)
        v = N1 * v1 + N2 * t1 + N3 * v2 + N4 * t2
        u = u1 * (1 - xi) + u2 * xi
        e = np.array([c, s])
        nrm = np.array([-s, c])
        p0 = self.frame.nodes[self.frame.members[k].i]
        base = p0[None, :] + (xi * L)[:, None] * e[None, :]
        return base + scale * (u[:, None] * e[None, :] + v[:, None] * nrm[None, :])


class Frame2D:
    """Plane frame assembled by the direct stiffness method.

    nodes      : (n, 2) array of node coordinates (m)
    members    : list of Member
    restraints : dict {node: (restrain_ux, restrain_uy, restrain_rz)}
    """

    def __init__(self, nodes, members, restraints):
        self.nodes = np.asarray(nodes, float)
        self.members = list(members)
        self.restraints = dict(restraints)
        self.ndof = 3 * len(self.nodes)

        fixed = []
        for n, flags in self.restraints.items():
            for k, r in enumerate(flags):
                if r:
                    fixed.append(3 * n + k)
        self.fixed_dofs = sorted(fixed)
        self.free_dofs = [q for q in range(self.ndof) if q not in set(self.fixed_dofs)]

        self.geom = []
        K = np.zeros((self.ndof, self.ndof))
        for m in self.members:
            xi, yi = self.nodes[m.i]
            xj, yj = self.nodes[m.j]
            L = float(np.hypot(xj - xi, yj - yi))
            if L <= 0:
                raise ValueError(f"Member {m.label or (m.i, m.j)} has zero length.")
            c, s = (xj - xi) / L, (yj - yi) / L
            k_loc = local_stiffness(m.E, m.A, m.I, L)
            T = transformation(c, s)
            dofs = [3 * m.i, 3 * m.i + 1, 3 * m.i + 2, 3 * m.j, 3 * m.j + 1, 3 * m.j + 2]
            K[np.ix_(dofs, dofs)] += T.T @ k_loc @ T
            self.geom.append((L, c, s, k_loc, T, dofs))
        self.K = K
        f, s_ = self.free_dofs, self.fixed_dofs
        self.Kff = K[np.ix_(f, f)]
        self.Kfs = K[np.ix_(f, s_)]
        # stability check: a mechanism makes Kff singular
        if len(f) and np.linalg.cond(self.Kff) > 1e14:
            raise ValueError("The frame is unstable (stiffness matrix is singular). Check supports and members.")

    def solve(self, w_gravity=None, nodal_loads=None, prescribed=None) -> FrameResult:
        """Solve one load case.

        w_gravity   : array (n_members,) of uniformly distributed gravity load (kN/m, acting
                      downward, per unit member length). None = no member loads.
        nodal_loads : dict {node: (Fx, Fy, Mz)} in global axes.
        prescribed  : dict {dof: value} of known support displacements (e.g. settlement).
        """
        nm = len(self.members)
        w = np.zeros(nm) if w_gravity is None else np.asarray(w_gravity, float)
        F = np.zeros(self.ndof)
        q_local = np.zeros((nm, 2))
        fef = np.zeros((nm, 6))
        for k, (L, c, s, _, T, dofs) in enumerate(self.geom):
            if w[k] == 0.0:
                continue
            # gravity load (0, -w) resolved into local axes
            qx, qy = -w[k] * s, -w[k] * c
            q_local[k] = (qx, qy)
            enl = np.array([qx * L / 2, qy * L / 2, qy * L**2 / 12, qx * L / 2, qy * L / 2, -qy * L**2 / 12])
            fef[k] = -enl                      # fixed-end forces
            F[dofs] += T.T @ enl               # equivalent nodal loads
        if nodal_loads:
            for n, (fx, fy, mz) in nodal_loads.items():
                F[3 * n:3 * n + 3] += (fx, fy, mz)

        d = np.zeros(self.ndof)
        if prescribed:
            for dof, v in prescribed.items():
                if dof not in self.fixed_dofs:
                    raise ValueError(f"Prescribed DOF {dof} is not a restrained DOF.")
                d[dof] = v
        f, s_ = self.free_dofs, self.fixed_dofs
        if len(f):
            rhs = F[f] - self.Kfs @ d[s_]
            d[f] = np.linalg.solve(self.Kff, rhs)

        R = self.K @ d - F
        R[f] = 0.0
        end_forces = np.zeros((nm, 6))
        for k, (L, c, s, k_loc, T, dofs) in enumerate(self.geom):
            end_forces[k] = k_loc @ (T @ d[dofs]) + fef[k]
        return FrameResult(self, d, R, end_forces, q_local)
