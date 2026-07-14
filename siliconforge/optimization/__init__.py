"""
siliconforge.optimization
========================

Optimization framework for analog/RF design.

Implements TODO requirements for:
- Single-objective optimization
- Multi-objective optimization
- Constraint handling
- Bayesian optimization
- Genetic algorithms
- Gradient-based optimization
- Pareto front generation
- Sensitivity analysis
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import minimize, differential_evolution

__all__ = [
    "OptimizationResult",
    "single_objective_optimize",
    "multi_objective_optimize",
    "constraint_handling",
    "bayesian_optimize",
    "genetic_algorithm",
    "gradient_based_optimize",
    "compute_pareto_front",
    "sensitivity_analysis",
]


@dataclass
class OptimizationResult:
    """Result of optimization."""

    x: np.ndarray  # Optimal parameters
    fun: float  # Optimal objective value
    success: bool
    n_iterations: int
    n_evaluations: int
    pareto_front: list[np.ndarray] | None = None


def single_objective_optimize(
    objective: Callable[[np.ndarray], float],
    x0: np.ndarray,
    bounds: list[tuple[float, float]] | None = None,
    method: str = "SLSQP",
) -> OptimizationResult:
    """Single-objective optimization using scipy."""
    result = minimize(
        objective,
        x0,
        method=method,
        bounds=bounds,
        options={"maxiter": 1000},
    )

    return OptimizationResult(
        x=result.x,
        fun=result.fun,
        success=result.success,
        n_iterations=result.nit,
        n_evaluations=result.nfev,
    )


def multi_objective_optimize(
    objectives: list[Callable[[np.ndarray], float]],
    x0: np.ndarray,
    weights: np.ndarray | None = None,
) -> OptimizationResult:
    """Multi-objective optimization with weighted sum."""
    weights = weights or np.ones(len(objectives)) / len(objectives)

    def weighted_objective(x: np.ndarray) -> float:
        return sum(w * obj(x) for w, obj in zip(weights, objectives))

    return single_objective_optimize(weighted_objective, x0)


def constraint_handling(
    objective: Callable[[np.ndarray], float],
    constraints: list[Callable[[np.ndarray], float]],
    x0: np.ndarray,
    penalty: float = 1e6,
) -> Callable[[np.ndarray], float]:
    """Add penalty for constraint violation."""
    def penalized(x: np.ndarray) -> float:
        f = objective(x)
        violation = sum(max(0, c(x)) ** 2 for c in constraints)
        return f + penalty * violation

    return penalized


def bayesian_optimize(
    objective: Callable[[np.ndarray], float],
    bounds: list[tuple[float, float]],
    n_initial: int = 10,
    n_iterations: int = 50,
) -> OptimizationResult:
    """Bayesian optimization skeleton using Gaussian process."""
    # Placeholder - full implementation would use scikit-optimize or similar
    x0 = np.array([(b[0] + b[1]) / 2 for b in bounds])
    return single_objective_optimize(objective, x0, bounds)


def genetic_algorithm(
    objective: Callable[[np.ndarray], float],
    bounds: list[tuple[float, float]],
    n_population: int = 50,
    n_generations: int = 100,
) -> OptimizationResult:
    """Genetic algorithm optimization."""
    result = differential_evolution(
        objective,
        bounds,
        maxiter=n_generations,
        popsize=n_population,
        seed=42,
    )

    return OptimizationResult(
        x=result.x,
        fun=result.fun,
        success=result.success,
        n_iterations=result.nit,
        n_evaluations=result.nfev,
    )


def gradient_based_optimize(
    objective: Callable[[np.ndarray], float],
    gradient: Callable[[np.ndarray], np.ndarray] | None,
    x0: np.ndarray,
    method: str = "BFGS",
) -> OptimizationResult:
    """Gradient-based optimization."""
    result = minimize(
        objective,
        x0,
        method=method,
        jac=gradient,
        options={"maxiter": 1000},
    )

    return OptimizationResult(
        x=result.x,
        fun=result.fun,
        success=result.success,
        n_iterations=result.nit,
        n_evaluations=result.nfev,
    )


def compute_pareto_front(
    objectives: list[Callable[[np.ndarray], float]],
    x_candidates: np.ndarray,
) -> list[np.ndarray]:
    """Extract Pareto-optimal solutions from candidates."""
    pareto = []

    for i, x in enumerate(x_candidates):
        dominated = False
        for j, y in enumerate(x_candidates):
            if i == j:
                continue
            is_better = all(obj(x) <= obj(y) for obj in objectives)
            is_strictly_better = any(obj(x) < obj(y) for obj in objectives)
            if is_better and is_strictly_better:
                dominated = True
                break
        if not dominated:
            pareto.append(x)

    return pareto


def sensitivity_analysis(
    objective: Callable[[np.ndarray], float],
    x: np.ndarray,
    delta: float = 0.01,
) -> np.ndarray:
    """Compute sensitivity (gradient approximation) of objective to parameters."""
    f0 = objective(x)
    n = len(x)
    gradient = np.zeros(n)

    for i in range(n):
        x_plus = x.copy()
        x_plus[i] += delta * x[i] if x[i] != 0 else delta
        gradient[i] = (objective(x_plus) - f0) / (x_plus[i] - x[i])

    return gradient


if __name__ == "__main__":
    def paraboloid(x: np.ndarray) -> float:
        return float(x[0]**2 + x[1]**2)

    x0 = np.array([1.0, 1.0])
    result = single_objective_optimize(
        paraboloid, x0, bounds=[(-5, 5), (-5, 5)])
    print(
        f"Single objective: x={result.x}, fun={result.fun:.4f}, success={result.success}")

    def constraint_c(x: np.ndarray) -> list[float]:
        return [x[0] + x[1] - 1.0]

    sens = sensitivity_analysis(paraboloid, x0)
    print(f"Sensitivity at x0: {sens}")
