"""
siliconforge.numerical
======================

Matrix-free numerical methods for circuit simulation.

This module provides Arnoldi, GMRES, Sparse LU, and other numerical
methods for PSS/PNoise without explicit Jacobian formation.
"""

from __future__ import annotations

from siliconforge.numerical.gmres import (
    matrix_free_gmres,
    arnoldi_iteration,
    LinearOperator,
)
from siliconforge.numerical.sparse_lu import (
    sparse_lu_factorize,
    sparse_lu_solve,
    sparse_lu_apply,
    create_mna_conductance_matrix,
    SparseLUResult,
)
from siliconforge.numerical.implicit_ode import (
    backward_euler_step,
    integrate_implicit_bdf,
    integrate_stiff_trbdf2,
    detect_events,
    ImplicitOdeResult,
)

__all__ = [
    # Dense Matrix Operations
    # GMRES/Arnoldi
    "matrix_free_gmres",
    "arnoldi_iteration",
    "LinearOperator",
    # Sparse LU
    "sparse_lu_factorize",
    "sparse_lu_solve",
    "sparse_lu_apply",
    "create_mna_conductance_matrix",
    "SparseLUResult",
    # Implicit ODE
    "backward_euler_step",
    "integrate_implicit_bdf",
    "integrate_stiff_trbdf2",
    "detect_events",
    "ImplicitOdeResult",
]
