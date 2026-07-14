"""
siliconforge.numerical.sparse_lu
=================================

Sparse LU decomposition for circuit MNA matrices.

Implements the TODO requirement for Sparse LU solver in the Numerical
Solver Library. Uses scipy.sparse.linalg.splu for efficient factorization
of sparse modified nodal admittance matrices.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import splu, spsolve

from siliconforge.exceptions import SiliconForgeError


@dataclass
class SparseLUResult:
    """Result of sparse LU factorization."""

    L: csr_matrix  # Lower triangular factor
    U: csr_matrix  # Upper triangular factor
    perm_c: np.ndarray  # Column permutation
    perm_r: np.ndarray  # Row permutation
    n_nnz: int  # Number of non-zeros in LU factors


def sparse_lu_factorize(A: csr_matrix) -> SparseLUResult:
    """Compute sparse LU factorization with fill-reducing ordering.

    Parameters
    ----------
    A : csr_matrix
        Sparse matrix to factorize (typically MNA conductance matrix)

    Returns
    -------
    SparseLUResult
        Factorization results including L, U factors and permutations
    """
    if not isinstance(A, csr_matrix):
        A = csr_matrix(A)

    lu = splu(A)

    n = A.shape[0]
    return SparseLUResult(
        L=lu.L,
        U=lu.U,
        perm_c=lu.perm_c,
        perm_r=lu.perm_r,
        n_nnz=lu.L.nnz + lu.U.nnz - n,
    )


def sparse_lu_solve(A: csr_matrix, b: np.ndarray) -> np.ndarray:
    """Solve sparse linear system using LU factorization.

    Parameters
    ----------
    A : csr_matrix
        Coefficient matrix
    b : np.ndarray
        Right-hand side vector

    Returns
    -------
    np.ndarray
        Solution vector x such that A @ x = b
    """
    if not isinstance(A, csr_matrix):
        A = csr_matrix(A)

    return spsolve(A, b)


def sparse_lu_apply(A: csr_matrix, x: np.ndarray) -> np.ndarray:
    """Apply sparse matrix to vector (matrix-vector product).

    Parameters
    ----------
    A : csr_matrix
        Sparse matrix
    x : np.ndarray
        Vector to multiply

    Returns
    -------
    np.ndarray
        Result y = A @ x
    """
    if not isinstance(A, csr_matrix):
        A = csr_matrix(A)

    return A @ x


def create_mna_conductance_matrix(
    conductance_dict: dict[tuple[str, str], float],
    node_names: list[str],
) -> csr_matrix:
    """Create a sparse MNA conductance matrix from conductance dictionary.

    Parameters
    ----------
    conductance_dict : dict
        Dictionary mapping (node_from, node_to) -> conductance (Siemens)
        Uses 'gnd' for ground node references
    node_names : list
        Ordered list of node names (must include all nodes used in conductance_dict)

    Returns
    -------
    csr_matrix
        Sparse conductance matrix
    """
    n = len(node_names)
    node_idx = {name: i for i, name in enumerate(node_names)}

    rows = []
    cols = []
    data = []

    for (n_from, n_to), g in conductance_dict.items():
        i = node_idx[n_from]
        j = node_idx[n_to]

        if g == 0:
            continue

        # Off-diagonal entries (negative conductance)
        rows.extend([i, j])
        cols.extend([j, i])
        data.extend([-g, -g])

        # Diagonal entries (positive self-conductance)
        rows.extend([i, j])
        cols.extend([i, j])
        data.extend([g, g])

    # Remove duplicates by summing
    if rows:
        from scipy.sparse import coo_matrix

        A = coo_matrix((data, (rows, cols)), shape=(n, n))
        return A.tocsr()

    return csr_matrix((n, n))
