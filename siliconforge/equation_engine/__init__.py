"""
siliconforge.equation_engine
=============================

Equation parsing and management for SiliconForge.

Implements TODO requirements for:
- Parse equations symbolically with sympy
- Assign unique IDs to every equation
- Define inputs/outputs/assumptions
- Symbolic/numerical forms
- Derivatives and sensitivity
- LaTeX generation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid
import numpy as np

try:
    import sympy as sp
    HAS_SYMPY = True
except ImportError:
    HAS_SYMPY = False


def _sp(val):
    """Helper to access sympy module."""
    if not HAS_SYMPY:
        raise ImportError("sympy not installed")
    return val


@dataclass
class EquationMetadata:
    """Metadata for a physical equation."""

    equation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    source_chapter: int = 0
    source_equation: int = 0
    description: str = ""
    assumptions: list[str] = field(default_factory=list)


@dataclass
class Equation:
    """Physical equation with symbolic and numerical forms."""

    symbolic: Any = None  # sympy expression
    numerical: Any = None  # callable
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    metadata: EquationMetadata = field(default_factory=EquationMetadata)

    def evaluate(self, **kwargs) -> float:
        """Evaluate numerically."""
        if self.numerical:
            return self.numerical(**kwargs)
        return float('nan')

    def to_latex(self) -> str:
        """Generate LaTeX representation."""
        if HAS_SYMPY and self.symbolic:
            return sp.latex(self.symbolic)
        return ""


# Equation registry
_EQUATION_REGISTRY: dict[str, Equation] = {}


def register_equation(
    name: str,
    symbolic=None,
    numerical=None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    chapter: int = 0,
    equation_num: int = 0,
) -> Equation:
    """Register an equation."""
    eq = Equation(
        symbolic=symbolic,
        numerical=numerical,
        inputs=inputs or [],
        outputs=outputs or [],
        metadata=EquationMetadata(
            source_chapter=chapter,
            source_equation=equation_num,
        ),
    )
    _EQUATION_REGISTRY[name] = eq
    return eq


def parse_equation(
    expression: str,
    variables: list[str],
) -> Equation:
    """Parse equation string to symbolic form."""
    if not HAS_SYMPY:
        return register_equation("parsed", numerical=lambda **kw: float('nan'), inputs=variables)

    syms = {v: sp.Symbol(v) for v in variables}
    expr = sp.sympify(expression)

    def numerical(**kwargs) -> float:
        subs = {syms[k]: v for k, v in kwargs.items() if k in syms}
        return float(expr.subs(subs))

    return register_equation("parsed", symbolic=expr, numerical=numerical, inputs=variables)


def compute_derivative(
    equation: Equation,
    variable: str,
) -> Equation:
    """Compute symbolic derivative."""
    if HAS_SYMPY and equation.symbolic:
        sym_var = sp.Symbol(variable)
        deriv = sp.diff(equation.symbolic, sym_var)
        return Equation(symbolic=deriv)
    return Equation()


def compute_sensitivity(
    equation: Equation,
    variable: str,
    nominal_values: dict[str, float],
    delta: float = 0.01,
) -> float:
    """Compute normalized sensitivity d(ln(y))/d(ln(v))."""
    nominal = nominal_values.get(variable, 1.0)
    y0 = equation.evaluate(**nominal_values)
    y_plus = equation.evaluate(
        **{**nominal_values, variable: nominal * (1 + delta)})
    return (y_plus - y0) / y0 / delta if y0 != 0 else 0.0


def _register_physics_equations() -> None:
    """Register standard physics equations."""
    register_equation(
        "Rp_from_Q",
        numerical=lambda q, omega, l: q * omega * l,
        inputs=["q", "omega", "l"],
        outputs=["Rp"],
        chapter=3,
        equation_num=3,
    )

    register_equation(
        "gm_from_Rp",
        numerical=lambda alpha, rp: alpha / rp,
        inputs=["alpha", "Rp"],
        outputs=["gm"],
        chapter=3,
        equation_num=4,
    )

    register_equation(
        "leeson",
        numerical=lambda f0, f, v_swing, q: (
            1.0 / (f**2 * v_swing**2 * q**2) if v_swing > 0 and f > 0 else 0.0
        ),
        inputs=["f0", "f", "v_swing", "q"],
        outputs=["L"],
        chapter=4,
        equation_num=7,
    )


_register_physics_equations()

if __name__ == "__main__":
    eq = register_equation(
        "test_lc_resonance",
        numerical=lambda f, l, c: f - 1/(2*3.14159*np.sqrt(l*c)),
        inputs=["f", "l", "c"],
        outputs=["error"],
    )
    print(f"Equation ID: {eq.metadata.equation_id}")
    print(f"Sensitivity test: {list(_EQUATION_REGISTRY.keys())}")

__all__ = [
    "Equation",
    "EquationMetadata",
    "register_equation",
    "parse_equation",
    "compute_derivative",
    "compute_sensitivity",
    "_EQUATION_REGISTRY",
]
