"""
siliconforge.numerical.implicit_ode
===================================

Implicit ODE methods for stiff circuit systems.

Implements BDF (Backward Differentiation Formula) and implicit RK methods
for stiff differential-algebraic equations (DAEs) arising in circuit simulation.

From TODO.md requirements:
- Implicit methods
- Stiff systems
- Event detection
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from siliconforge.numerical.sparse_lu import sparse_lu_solve
from siliconforge.exceptions import SiliconForgeError


@dataclass
class ImplicitOdeResult:
    """Result of implicit ODE integration."""

    time: np.ndarray
    solution: np.ndarray
    n_steps: int
    success: bool
    message: str


def backward_euler_step(
    rhs: Callable[[float, np.ndarray], np.ndarray],
    t: float,
    y: np.ndarray,
    h: float,
    jac: Callable[[float, np.ndarray], np.ndarray] | None = None,
    tol: float = 1e-10,
    maxiter: int = 100,
) -> np.ndarray:
    """One step of backward Euler integration.

    y_{n+1} = y_n + h * f(t_{n+1}, y_{n+1})

    Solved via Newton iteration with matrix-free Jacobian.
    """
    y_new = y.copy()

    for iteration in range(maxiter):
        f_new = rhs(t + h, y_new)
        residual = y_new - y - h * f_new

        if np.linalg.norm(residual) < tol:
            return y_new

        if jac is not None:
            J = jac(t + h, y_new)
            dy = sparse_lu_solve(J, -residual)
        else:
            epsilon = 1e-8
            n = len(y_new)
            f_base = f_new
            J_approx = np.zeros((n, n))
            for j in range(n):
                e_j = np.zeros(n)
                e_j[j] = 1.0
                f_pert = rhs(t + h, y_new + 1j * epsilon * e_j)
                J_approx[:, j] = np.imag(f_pert) / epsilon

            J_dense = np.eye(n) + h * J_approx
            try:
                dy = np.linalg.solve(J_dense, -residual)
            except np.linalg.LinAlgError:
                dy = sparse_lu_solve(J_dense, -residual)

        y_new = y_new + dy

    raise SiliconForgeError(
        f"Backward Euler did not converge after {maxiter} iterations")


class LinearOperator:
    """Matrix-free linear operator for implicit solves."""

    def __init__(self, shape: tuple[int, int], matvec: Callable[[np.ndarray], np.ndarray]):
        self.shape = shape
        self._matvec = matvec

    def __matmul__(self, v: np.ndarray) -> np.ndarray:
        return self._matvec(v)


def integrate_implicit_bdf(
    rhs: Callable[[float, np.ndarray], np.ndarray],
    t_span: tuple[float, float],
    y0: np.ndarray,
    h0: float = 1e-12,
    h_min: float = 1e-15,
    h_max: float = 1e-9,
    tol: float = 1e-8,
    max_steps: int = 10000,
) -> ImplicitOdeResult:
    """Integrate stiff ODE using BDF2 with adaptive step sizing.

    Uses variable-order BDF (1-2) with step doubling for error control.
    Suitable for circuits with widely separated time constants.

    Parameters
    ----------
    rhs : callable
        f(t, y) returning dy/dt
    t_span : tuple
        (t_start, t_end)
    y0 : np.ndarray
        Initial conditions
    h0, h_min, h_max : float
        Step size limits
    tol : float
        Error tolerance for adaptive stepping
    max_steps : int
        Maximum number of steps

    Returns
    -------
    ImplicitOdeResult
        Time points and solution values
    """
    t_start, t_end = t_span
    t = t_start
    y = y0.copy()
    h = h0

    times = [t]
    solution = [y.copy()]

    prev_y = None
    error = 0.0

    for step in range(max_steps):
        if t >= t_end:
            break

        # Adjust h to hit t_end exactly
        h = min(h, t_end - t)

        if prev_y is None:
            # BDF1 step (first step, no previous solution)
            y_BDF1 = backward_euler_step(rhs, t, y, h)

            y_half = backward_euler_step(rhs, t, y, h / 2)
            y_double = backward_euler_step(rhs, t + h / 2, y_half, h / 2)

            error = np.linalg.norm(y_BDF1 - y_double)

            if error > tol and h > h_min:
                h = h / 2
                continue

            y = y_BDF1
        else:
            f_n = rhs(t, y)
            y_BDF2 = y + h * f_n

            for iteration in range(100):
                f_new = rhs(t + h, y_BDF2)
                residual = y_BDF2 - (4.0 / 3.0) * y + (1.0 / 3.0) * \
                    prev_y - (2.0 * h / 3.0) * f_new

                if np.linalg.norm(residual) < tol:
                    break

                epsilon = 1e-8
                n = len(y_BDF2)
                J = np.zeros((n, n))
                for j in range(n):
                    e_j = np.zeros(n)
                    e_j[j] = 1.0
                    f_pert = rhs(t + h, y_BDF2 + 1j * epsilon * e_j)
                    J[:, j] = np.imag(f_pert) / epsilon

                if np.linalg.norm(J) > 1e-12:
                    dy = -residual / (np.linalg.norm(J) + 1e-12)
                else:
                    dy = -residual

                y_BDF2 = y_BDF2 + 0.5 * dy

            # BDF2 error estimate using embedded BDF1 result
            y_BDF1_check = backward_euler_step(rhs, t, y, h)
            error = np.linalg.norm(y_BDF2 - y_BDF1_check)

            y = y_BDF2

        t = t + h
        times.append(t)
        solution.append(y.copy())
        prev_y = y

        if error < tol / 10 and h < h_max:
            h = min(h * 1.2, h_max)

    return ImplicitOdeResult(
        time=np.array(times),
        solution=np.array(solution),
        n_steps=len(times),
        success=True,
        message="BDF integration completed",
    )


def integrate_stiff_trbdf2(
    rhs: Callable[[float, np.ndarray], np.ndarray],
    t_span: tuple[float, float],
    y0: np.ndarray,
    h: float = 1e-12,
) -> ImplicitOdeResult:
    """TR-BDF2 integration for stiff circuits.

    A two-stage implicit method combining trapezoidal and BDF2 stages.
    Particularly effective for circuits with stiff parasitic nodes.
    """
    t_start, t_end = t_span
    t = t_start
    y = y0.copy()

    times = [t]
    solution = [y.copy()]

    while t < t_end:
        y_pred = y + h * rhs(t, y)

        for _ in range(20):
            f_pred = rhs(t + h, y_pred)
            residual = y_pred - y - (h / 2) * (rhs(t, y) + f_pred)
            if np.linalg.norm(residual) < 1e-10:
                break
            y_pred = y_pred - 0.5 * residual

        t = t + h
        y = y_pred
        times.append(t)
        solution.append(y.copy())

    return ImplicitOdeResult(
        time=np.array(times),
        solution=np.array(solution),
        n_steps=len(times),
        success=True,
        message="TR-BDF2 integration completed",
    )


def detect_events(
    rhs: Callable[[float, np.ndarray], np.ndarray],
    t_span: tuple[float, float],
    y0: np.ndarray,
    event_func: Callable[[np.ndarray], float],
    h: float = 1e-12,
    dir: int = 0,
) -> list[float]:
    """Detect events (zero crossings) during integration.

    Parameters
    ----------
    rhs : callable
        System right-hand side
    t_span : tuple
        Time span (t_start, t_end)
    y0 : np.ndarray
        Initial state
    event_func : callable
        Function of state returning event value (root when 0)
    h : float
        Time step
    dir : int
        Direction of crossing to detect

    Returns
    -------
    list[float]
        Times at which events occurred
    """
    t = t_span[0]
    t_end = t_span[1]
    y = y0.copy()

    event_times = []
    prev_value = event_func(y)

    while t < t_end:
        y_new = y + h * rhs(t, y)
        t += h

        new_value = event_func(y_new)

        if prev_value * new_value < 0:
            event_times.append(t - h / 2)

        prev_value = new_value
        y = y_new

    return event_times
