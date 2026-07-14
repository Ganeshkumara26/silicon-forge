"""
siliconforge.solvers.pss_shooting
==================================

Periodic Steady State (PSS) Shooting-Newton solver for autonomous oscillators.

Implements the guidebook's Section 4.5 shooting-Newton algorithm:
1. State transition function: phi(T, x0) -> x(T)
2. Residual for limit cycle: F(x0) = x(T) - x0
3. Matrix-free GMRES for Jacobian-vector products

This is Module 2 in the architecture.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.sparse.linalg import gmres, LinearOperator

from siliconforge.backends.base import CircuitState, Simulator

logger = logging.getLogger(__name__)


@dataclass
class PSSResult:
    """Result of PSS shooting-Newton convergence."""

    converged: bool
    x0: np.ndarray  # Initial state that gives period-T return
    xT: np.ndarray  # Final state (should equal x0 for converged)
    n_iterations: int
    n_gmres_calls: int
    residual_norm: float
    period_s: float


def _state_transition(sim: Simulator, element_names: list[str], x0: np.ndarray, period: float) -> CircuitState:
    """Evaluate state transition phi(T, x0) -> x(T).

    Inject initial condition x0 into simulator, run one period of transient,
    return final state.
    """
    state = CircuitState(
        values={name: float(x0[i]) for i, name in enumerate(element_names)})
    sim.inject_state(state)
    result = sim.transient(tstep=period / 100, tstop=period, use_ic=True)
    return result.final_state


def shoot_newton(
    sim: Simulator,
    period: float,
    max_iterations: int = 100,
    residual_tol: float = 1e-10,
    gmres_tol: float = 1e-8,
    gmres_maxiter: int = 20,
    damping: float = 0.5,
) -> PSSResult:
    """Solve PSS via shooting-Newton with matrix-free GMRES.

    Finds x0 such that x(T, x0) = x0 (limit cycle condition).

    Parameters
    ----------
    sim : Simulator
        The loaded circuit simulator
    period : float
        Expected oscillation period (seconds)
    max_iterations : int
        Maximum Newton iterations
    residual_tol : float
        Convergence tolerance for |x(T) - x0|
    gmres_tol : float
        Tolerance for GMRES linear solve
    gmres_maxiter : int
        Maximum GMRES iterations per Newton step
    damping : float
        Newton update damping factor (0 < damping <= 1)

    Returns
    -------
    PSSResult
        Converged state or diagnostic info
    """
    if not (0 < damping <= 1.0):
        raise ValueError(f"damping must be in (0, 1]; got {damping}")
    if gmres_maxiter < 1:
        raise ValueError(f"gmres_maxiter must be >= 1; got {gmres_maxiter}")
    elements_dict = sim.reactive_elements
    element_names = list(elements_dict.keys())
    n_states = len(element_names)

    if n_states == 0:
        raise ValueError("No reactive elements in circuit")

    # Initial guess: small sinusoidal perturbation to break equilibrium symmetry
    t = np.linspace(0, period, n_states, endpoint=False)
    freq0 = 1.0 / period if period > 0 else 1e9
    x0 = 0.1 * np.sin(2 * np.pi * freq0 * t)

    n_gmres_calls = 0

    for iteration in range(max_iterations):
        # Evaluate residual F(x0) = x(T) - x0
        xT_state = _state_transition(sim, element_names, x0, period)
        xT = np.array([xT_state.values.get(name, 0.0)
                      for name in element_names])
        residual = xT - x0
        residual_norm = np.linalg.norm(residual)

        logger.debug(
            f"PSS iteration {iteration}: residual_norm = {residual_norm:.2e}")

        if residual_norm < residual_tol:
            xT_state = _state_transition(sim, element_names, x0, period)
            xT = np.array([xT_state.values.get(name, 0.0)
                          for name in element_names])
            assert np.allclose(
                xT, x0, atol=residual_tol), "Post-convergence state mismatch"
            return PSSResult(
                converged=True,
                x0=x0,
                xT=xT,
                n_iterations=iteration + 1,
                n_gmres_calls=n_gmres_calls,
                residual_norm=residual_norm,
                period_s=period,
            )

        # Jacobian-vector product via finite difference
        epsilon = 1e-6 * max(1.0, np.linalg.norm(x0))

        def jv(v: np.ndarray) -> np.ndarray:
            nonlocal n_gmres_calls
            n_gmres_calls += 1

            # F(x0 + eps*v) - F(x0)
            x_perturbed = x0 + epsilon * v
            xT_perturbed_state = _state_transition(
                sim, element_names, x_perturbed, period)
            xT_perturbed = np.array(
                [xT_perturbed_state.values.get(name, 0.0) for name in element_names])
            residual_perturbed = xT_perturbed - x_perturbed

            # dF/dx * v = (F(x + eps*v) - F(x)) / eps
            return (residual_perturbed - residual) / epsilon

        J = LinearOperator((n_states, n_states), matvec=lambda v: jv(v))

        # Solve J * dx = -residual
        dx, info = gmres(J, -residual, tol=gmres_tol, maxiter=gmres_maxiter)

        if info != 0:
            logger.warning(
                f"GMRES failed to converge at iteration {iteration}")

        # Damped update
        x0 = x0 + damping * dx

    final_state = _state_transition(sim, element_names, x0, period)
    xT_final = np.array([final_state.values.get(name, 0.0)
                        for name in element_names])
    residual_norm = np.linalg.norm(xT_final - x0)

    return PSSResult(
        converged=False,
        x0=x0,
        xT=xT_final,
        n_iterations=max_iterations,
        n_gmres_calls=n_gmres_calls,
        residual_norm=residual_norm,
        period_s=period,
    )


def find_limit_cycle_period(
    sim: Simulator,
    f_guess_hz: float,
    f_search_range_hz: float = 0.1,
) -> float:
    """Find oscillation period via bifurcation searching.

    For an autonomous oscillator, the period is where the map
    has an eigenvalue at +1 (stable limit cycle).

    We search for the period where |x(T) - x0| crosses zero.
    The state-transition evaluator must use use_ic=True on sim.transient().
    """
    elements_dict = sim.reactive_elements
    element_names = list(elements_dict.keys())
    f_center = f_guess_hz
    period_low = 1.0 / (f_center + f_search_range_hz)
    period_high = 1.0 / (f_center - f_search_range_hz)

    def residual_magnitude(period: float) -> float:
        x0_guess = np.array([0.0] * len(element_names))
        xT_state = _state_transition(sim, element_names, x0_guess, period)
        xT = np.array([xT_state.values.get(name, 0.0)
                      for name in element_names])
        return np.linalg.norm(xT - x0_guess)

    residual_low = residual_magnitude(period_low)
    residual_high = residual_magnitude(period_high)

    for _ in range(40):
        period_mid = (period_low + period_high) / 2.0
        residual_mid = residual_magnitude(period_mid)
        if residual_mid < 1e-3:
            return period_mid
        if residual_low > residual_high:
            period_low = period_mid
            residual_low = residual_mid
        else:
            period_high = period_mid
            residual_high = residual_mid

    return (period_low + period_high) / 2.0

