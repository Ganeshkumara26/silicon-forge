"""
siliconforge.numerical.gmres
==============================

Matrix-free GMRES for PSS shooting-Newton.

Implements Arnoldi iteration without forming the Jacobian explicitly.
"""

from __future__ import annotations

from typing import Callable, Protocol

import numpy as np


class LinearOperator(Protocol):
    """Protocol for matrix-free linear operators."""

    def __matmul__(self, v: np.ndarray) -> np.ndarray: ...


def matrix_free_gmres(
    matvec: Callable[[np.ndarray], np.ndarray],
    b: np.ndarray,
    x0: np.ndarray | None = None,
    maxiter: int = 100,
    tol: float = 1e-6,
    restart: int = 30,
) -> tuple[np.ndarray, int, float]:
    """GMRES iterations without explicit matrix.

    Parameters
    ----------
    matvec : callable
        Function computing A*v for arbitrary v
    b : ndarray
        Right-hand side
    x0 : ndarray, optional
        Initial guess
    maxiter : int
        Maximum iterations
    tol : float
        Convergence tolerance
    restart : int
        Restart parameter (FOM)

    Returns
    -------
    x : ndarray
        Solution
    info : int
        0 if converged, 1 otherwise
    residual : float
        Final residual norm
    """
    n = len(b)
    x = np.zeros(n) if x0 is None else x0.copy()

    r = b - matvec(x)
    beta = np.linalg.norm(r)

    if beta < tol:
        return x, 0, beta

    for outer_iter in range(maxiter // restart + 1):
        # Arnoldi iteration for this restart cycle
        V = np.zeros((n, restart + 1))
        H = np.zeros((restart + 1, restart))
        g = np.zeros(restart + 1)

        r = b - matvec(x)
        beta = np.linalg.norm(r)
        g[0] = beta
        V[:, 0] = r / beta

        for iter in range(restart):
            w = matvec(V[:, iter])

            for j in range(iter + 1):
                H[j, iter] = np.dot(V[:, j], w)
                w -= H[j, iter] * V[:, j]

            H[iter + 1, iter] = np.linalg.norm(w)
            if H[iter + 1, iter] > 1e-12:
                V[:, iter + 1] = w / H[iter + 1, iter]

        # Solve least squares for full Hessenberg
        y, _, _, _ = np.linalg.lstsq(
            H[: restart + 1, :restart], g[: restart + 1], rcond=None)

        # Update solution
        for j in range(restart):
            x += y[j] * V[:, j]

        # Check residual
        residual = np.linalg.norm(b - matvec(x))
        if residual < tol:
            return x, 0, residual

    return x, 1, np.linalg.norm(b - matvec(x))


def arnoldi_iteration(
    matvec: Callable[[np.ndarray], np.ndarray],
    v_start: np.ndarray,
    k: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Perform k Arnoldi iterations.

    Returns orthonormal basis V and Hessenberg matrix H.
    """
    n = len(v_start)
    v = v_start / np.linalg.norm(v_start)

    V = np.zeros((n, k + 1))
    H = np.zeros((k + 1, k))

    V[:, 0] = v

    for j in range(k):
        w = matvec(V[:, j])

        for i in range(j + 1):
            H[i, j] = np.dot(V[:, i], w)
            w -= H[i, j] * V[:, i]

        H[j + 1, j] = np.linalg.norm(w)
        if H[j + 1, j] > 1e-12:
            V[:, j + 1] = w / H[j + 1, j]

    return V, H
