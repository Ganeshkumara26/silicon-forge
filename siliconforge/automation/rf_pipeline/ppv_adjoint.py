#!/usr/bin/env python3
"""ppv_adjoint.py -- True Floquet Adjoint PPV Solver (v2.0)

Implements the mathematically rigorous 4-stage PPV extraction pipeline:
  1. Steady-State Engine (high-precision limit cycle via BDF)
  2. Time-Varying Jacobian J(t) (analytical for built-in models)
  3. Backward Adjoint Integration (periodic BVP via shooting)
  4. Biorthogonal Normalization (v1^T * x_dot = 1)

Supports built-in oscillator models (Ideal LC, Van der Pol) for validation,
and can consume SPICE-extracted trajectory data for real circuits.
"""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import CubicSpline
from scipy.linalg import expm, solve
import json
import argparse
import sys
import os

# ===========================================================================
# Built-in Oscillator Models (State Equations + Analytical Jacobians)
# ===========================================================================


class IdealLC:
    """Ideal lossless LC tank oscillator.
    State: x = [V, I]  (capacitor voltage, inductor current)
    x_dot = f(x) = [I/C, -V/L]
    Analytical PPV for voltage node: v1_V(t) = sin(w0*t) / (C * A * w0)
    """

    def __init__(self, L=1e-9, C=1e-12, A=1.0):
        self.L = L
        self.C = C
        self.A = A
        self.w0 = 1.0 / np.sqrt(L * C)
        self.T0 = 2 * np.pi / self.w0
        self.name = f"Ideal LC Tank (L={L*1e9:.1f}nH, C={C*1e12:.1f}pF)"

    def f(self, t, x):
        V, I = x
        return np.array([I / self.C, -V / self.L])

    def jacobian(self, t, x):
        return np.array([
            [0,          1.0 / self.C],
            [-1.0 / self.L, 0]
        ])

    def x0(self):
        return np.array([self.A, 0.0])

    def analytical_ppv(self, t_array):
        """Returns the exact analytical PPV for the voltage node."""
        v1_V = np.sin(self.w0 * t_array) / (self.C * self.A * self.w0)
        v1_I = -np.cos(self.w0 * t_array) / (self.A * self.w0)
        return np.column_stack([v1_V, v1_I])


class VanDerPol:
    """Van der Pol oscillator with nonlinear damping.
    State: x = [x1, x2]
    x1_dot = x2
    x2_dot = mu * (1 - x1^2) * x2 - x1
    """

    def __init__(self, mu=1.0):
        self.mu = mu
        self.name = f"Van der Pol (mu={mu})"
        self.T0 = None  # Must be found numerically

    def f(self, t, x):
        x1, x2 = x
        return np.array([
            x2,
            self.mu * (1 - x1**2) * x2 - x1
        ])

    def jacobian(self, t, x):
        x1, x2 = x
        return np.array([
            [0,                              1],
            [-2 * self.mu * x1 * x2 - 1,     self.mu * (1 - x1**2)]
        ])

    def x0(self):
        return np.array([2.0, 0.0])


# ===========================================================================
# Stage 1: Steady-State Engine
# ===========================================================================

def find_steady_state(model, num_periods=50, N_per_period=1000):
    """Integrate the ODE for many periods to reach steady state,
    then extract exactly one clean period using zero-crossing detection."""

    print(f"[PPV-ADJ] Stage 1: Finding steady-state for {model.name}")

    # Initial guess for period
    if model.T0 is not None:
        T_guess = model.T0
    else:
        T_guess = 2 * np.pi  # Default guess for normalized systems

    T_total = num_periods * T_guess
    dt = T_guess / N_per_period
    t_span = (0, T_total)
    t_eval = np.arange(0, T_total, dt)

    sol = solve_ivp(model.f, t_span, model.x0(), method='BDF',
                    t_eval=t_eval, rtol=1e-10, atol=1e-12,
                    dense_output=True, jac=model.jacobian)

    if not sol.success:
        print(f"[ERROR] ODE integration failed: {sol.message}")
        return None, None, None

    t = sol.t
    x = sol.y  # shape: (n_states, n_times)

    # Find zero crossings of x[0] (voltage/x1) in the last portion
    v = x[0]
    crossings = []
    start_idx = len(v) * 3 // 4  # Use last 25% only (well settled)
    for i in range(start_idx, len(v) - 1):
        if v[i] <= 0 and v[i+1] > 0:
            # Cubic spline local interpolation
            lo = max(0, i - 3)
            hi = min(len(v), i + 5)
            cs = CubicSpline(t[lo:hi], v[lo:hi])
            roots = cs.roots()
            valid = roots[(roots >= t[i]) & (roots <= t[i+1])]
            if len(valid) > 0:
                crossings.append(float(valid[0]))

    if len(crossings) < 2:
        print("[ERROR] Could not detect oscillations.")
        return None, None, None

    # Period from last two crossings
    T0 = crossings[-1] - crossings[-2]
    t_start = crossings[-2]

    # Extract exactly one period using the dense output
    t_period = np.linspace(t_start, t_start + T0, N_per_period + 1)
    x_period = sol.sol(t_period)  # shape: (n_states, N+1)

    # Verify periodicity
    err = np.linalg.norm(x_period[:, 0] - x_period[:, -1])
    print(f"[PPV-ADJ]   T0 = {T0:.10e} s")
    print(f"[PPV-ADJ]   Periodicity error: ||x(0) - x(T)|| = {err:.3e}")

    # Update model period if it was unknown
    if model.T0 is None:
        model.T0 = T0

    # Return t_period without the duplicate endpoint
    return t_period[:-1], x_period[:, :-1], T0


# ===========================================================================
# Stage 2: Time-Varying Jacobian J(t)
# ===========================================================================

def compute_jacobian_trajectory(model, t_array, x_array):
    """Evaluate J(t) = df/dx at every point along the trajectory."""
    N = len(t_array)
    n = x_array.shape[0]
    J_traj = np.zeros((N, n, n))

    for i in range(N):
        J_traj[i] = model.jacobian(t_array[i], x_array[:, i])

    return J_traj


# ===========================================================================
# Stage 3: Backward Adjoint Integration
# ===========================================================================

def solve_adjoint_bvp(t_array, J_traj, x_dot, T0):
    """Solve the adjoint equation dv1/dt = -J^T(t) * v1(t) 
    with periodic boundary conditions v1(0) = v1(T).

    Uses the monodromy matrix approach:
    1. Compute the state transition matrix Phi(T,0) by integrating 
       the adjoint system forward with identity initial conditions.
    2. The periodic solution is the eigenvector of Phi^T corresponding 
       to eigenvalue 1.
    """
    N = len(t_array)
    n = J_traj.shape[1]
    dt = T0 / N

    print(
        f"[PPV-ADJ] Stage 3: Solving adjoint system ({n}x{n}, {N} grid points, backward integration)")

    # We integrate backward in time from t_N down to t_0 to keep the integration stable.
    # Adjoint eq: dv/dt = -J^T(t) * v
    # Trapezoidal backward step:
    # (I - dt/2 * J^T(t_{i-1})) * v(t_{i-1}) = (I + dt/2 * J^T(t_i)) * v(t_i)

    Phi_back = np.eye(n)  # State transition matrix backward

    for i in range(N - 1, 0, -1):
        A_i = J_traj[i].T
        A_im1 = J_traj[i - 1].T

        M_left = np.eye(n) - 0.5 * dt * A_im1
        M_right = np.eye(n) + 0.5 * dt * A_i

        Phi_back = solve(M_left, M_right @ Phi_back)

    # The periodic solution satisfies: Phi_back * v1(T) = v1(0) = v1(T)
    eigenvalues, eigenvectors = np.linalg.eig(Phi_back)

    print(
        f"[PPV-ADJ]   Floquet multipliers (backward adjoint): {np.abs(eigenvalues)}")

    # Find the eigenvector corresponding to eigenvalue 1
    # For a stable oscillator, one is exactly 1, others are < 1
    # For an LC tank, both are 1. We must pick the one that gives non-zero biorthogonality.
    best_idx = 0
    max_alpha = -1

    for idx in range(n):
        if np.abs(np.abs(eigenvalues[idx]) - 1.0) < 1e-2:
            v_cand = np.real(eigenvectors[:, idx])
            alpha_cand = np.abs(np.dot(v_cand, x_dot[:, -1]))
            if alpha_cand > max_alpha:
                max_alpha = alpha_cand
                best_idx = idx

    v1_T = np.real(eigenvectors[:, best_idx])

    print(f"[PPV-ADJ]   Selected multiplier: {eigenvalues[best_idx]:.8f}")

    # Now propagate v1(T) BACKWARD through the entire period to get v1(t)
    v1_traj = np.zeros((N, n))
    v1_traj[-1] = v1_T
    v1_traj[0] = v1_T

    for i in range(N - 1, 0, -1):
        A_i = J_traj[i].T
        A_im1 = J_traj[i - 1].T

        M_left = np.eye(n) - 0.5 * dt * A_im1
        M_right = np.eye(n) + 0.5 * dt * A_i

        v1_traj[i - 1] = solve(M_left, M_right @ v1_traj[i])

    return v1_traj, eigenvalues


# ===========================================================================
# Stage 4: Biorthogonal Normalization
# ===========================================================================

def normalize_ppv(v1_traj, x_array, t_array, T0):
    """Normalize the PPV such that v1^T(t) * x_dot(t) = 1 for all t."""
    N = len(t_array)
    n = x_array.shape[0]
    dt = T0 / N

    # Compute x_dot using central differences (4th order)
    x_dot = np.zeros_like(x_array)
    for j in range(n):
        x_dot[j] = np.gradient(x_array[j], t_array)

    # Compute the inner product alpha(t) = v1^T(t) * x_dot(t)
    alpha = np.zeros(N)
    for i in range(N):
        alpha[i] = np.dot(v1_traj[i], x_dot[:, i])

    # The mean alpha is our normalization constant
    alpha_mean = np.mean(alpha)
    alpha_std = np.std(alpha)

    print(f"[PPV-ADJ] Stage 4: Biorthogonal Normalization")
    print(f"[PPV-ADJ]   alpha_mean = {alpha_mean:.8e}")
    print(f"[PPV-ADJ]   alpha_std  = {alpha_std:.3e}")
    print(
        f"[PPV-ADJ]   alpha_std/alpha_mean = {alpha_std/abs(alpha_mean+1e-30):.6e}")

    # Normalize
    v1_normalized = v1_traj / alpha_mean

    # Verify normalization
    alpha_check = np.zeros(N)
    for i in range(N):
        alpha_check[i] = np.dot(v1_normalized[i], x_dot[:, i])

    print(
        f"[PPV-ADJ]   After normalization: mean(alpha) = {np.mean(alpha_check):.8f}, std(alpha) = {np.std(alpha_check):.3e}")

    return v1_normalized, x_dot, alpha_check


# ===========================================================================
# Main Entry Point
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Floquet Adjoint PPV Solver")
    parser.add_argument("--model", type=str, choices=["lc", "vdp"], default="lc",
                        help="Built-in model: lc (Ideal LC Tank), vdp (Van der Pol)")
    parser.add_argument("--mu", type=float, default=1.0,
                        help="Van der Pol nonlinearity parameter")
    parser.add_argument("--L", type=float, default=1e-9,
                        help="Inductance (H) for LC model")
    parser.add_argument("--C", type=float, default=1e-12,
                        help="Capacitance (F) for LC model")
    parser.add_argument("--A", type=float, default=1.0,
                        help="Amplitude (V) for LC model")
    parser.add_argument("--N", type=int, default=1000,
                        help="Points per period")
    parser.add_argument(
        "--output", type=str, default="ppv_adjoint_result.json", help="Output JSON file")
    args = parser.parse_args()

    # Select model
    if args.model == "lc":
        model = IdealLC(L=args.L, C=args.C, A=args.A)
    elif args.model == "vdp":
        model = VanDerPol(mu=args.mu)

    print(f"\n{'='*60}")
    print(f" FLOQUET ADJOINT PPV SOLVER v2.0")
    print(f" Model: {model.name}")
    print(f"{'='*60}\n")

    # Stage 1: Find steady state
    t_ss, x_ss, T0 = find_steady_state(
        model, num_periods=50, N_per_period=args.N)
    if t_ss is None:
        return 1

    # Stage 2: Compute Jacobian trajectory
    print(
        f"\n[PPV-ADJ] Stage 2: Computing J(t) along trajectory ({args.N} points)")
    J_traj = compute_jacobian_trajectory(model, t_ss, x_ss)

    # Stage 3: Solve adjoint BVP
    x_dot_approx = np.zeros_like(x_ss)
    for j in range(x_ss.shape[0]):
        x_dot_approx[j] = np.gradient(x_ss[j], t_ss)

    v1_raw, floquet_multipliers = solve_adjoint_bvp(
        t_ss, J_traj, x_dot_approx, T0)

    # Stage 4: Biorthogonal normalization
    v1_norm, x_dot, alpha = normalize_ppv(v1_raw, x_ss, t_ss, T0)

    # Validation against analytical solution (LC only)
    if isinstance(model, IdealLC):
        print(
            f"\n[VALIDATION] Comparing against analytical PPV for Ideal LC Tank...")
        ppv_analytical = model.analytical_ppv(t_ss - t_ss[0])

        # Normalize analytical PPV the same way
        alpha_analytical = np.array(
            [np.dot(ppv_analytical[i], x_dot[:, i]) for i in range(len(t_ss))])
        ppv_analytical_norm = ppv_analytical / np.mean(alpha_analytical)

        l2_error = np.sqrt(np.mean((v1_norm - ppv_analytical_norm)**2))
        linf_error = np.max(np.abs(v1_norm - ppv_analytical_norm))

        print(f"[VALIDATION]   L2 error:   {l2_error:.6e}")
        print(f"[VALIDATION]   Linf error: {linf_error:.6e}")

        if l2_error < 1e-4:
            print(f"[VALIDATION]   [PASS]: PPV matches analytical solution!")
        else:
            print(f"[VALIDATION]   [FAIL]: PPV deviates from analytical solution.")

    # Periodicity test
    periodicity_err = np.linalg.norm(v1_norm[0] - v1_norm[-1])
    print(
        f"\n[TEST] Periodicity: ||v1(0) - v1(T)|| = {periodicity_err:.3e}", end="")
    print("  [PASS]" if periodicity_err < 1e-6 else "  [FAIL]")

    # Biorthogonality test
    bio_std = np.std(alpha)
    print(f"[TEST] Biorthogonality: std(alpha) = {bio_std:.3e}", end="")
    print("  [PASS]" if bio_std < 1e-4 else "  [FAIL]")

    # Export results
    result = {
        "model": model.name,
        "T0": T0,
        "f0": 1.0 / T0,
        "N_points": len(t_ss),
        "floquet_multipliers": [float(np.abs(m)) for m in floquet_multipliers],
        "periodicity_error": float(periodicity_err),
        "biorthogonality_std": float(bio_std),
        "ppv_voltage": v1_norm[:, 0].tolist(),
        "trajectory_voltage": x_ss[0].tolist(),
        "time": (t_ss - t_ss[0]).tolist()
    }

    with open(args.output, "w") as f:
        json.dump(result, f, indent=4)

    print(f"\n[PPV-ADJ] Saved results to {args.output}")

    # Generate plot
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        t_norm = (t_ss - t_ss[0]) / T0 * 2 * np.pi

        # 1. Steady-state trajectory
        axes[0, 0].plot(t_norm, x_ss[0], 'b-', linewidth=1.5, label="x₁(t)")
        axes[0, 0].plot(t_norm, x_ss[1], 'r-', linewidth=1.5, label="x₂(t)")
        axes[0, 0].set_title("Steady-State Trajectory")
        axes[0, 0].set_xlabel("Phase (rad)")
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        # 2. PPV (normalized)
        axes[0, 1].plot(t_norm, v1_norm[:, 0], 'b-',
                        linewidth=2, label="v₁ (voltage)")
        axes[0, 1].plot(t_norm, v1_norm[:, 1], 'r-',
                        linewidth=2, label="v₁ (current)")
        if isinstance(model, IdealLC):
            axes[0, 1].plot(t_norm, ppv_analytical_norm[:, 0],
                            'k--', linewidth=1, label="Analytical")
        axes[0, 1].set_title("Normalized PPV (Adjoint Eigenvector)")
        axes[0, 1].set_xlabel("Phase (rad)")
        axes[0, 1].legend()
        axes[0, 1].grid(True, alpha=0.3)

        # 3. Biorthogonality check
        alpha_norm = np.array([np.dot(v1_norm[i], x_dot[:, i])
                              for i in range(len(t_ss))])
        axes[1, 0].plot(t_norm, alpha_norm, 'g-', linewidth=1.5)
        axes[1, 0].axhline(y=1.0, color='k', linestyle='--', alpha=0.5)
        axes[1, 0].set_title(f"Biorthogonality: v1^T * x_dot (should = 1.0)")
        axes[1, 0].set_xlabel("Phase (rad)")
        axes[1, 0].set_ylim([0.95, 1.05])
        axes[1, 0].grid(True, alpha=0.3)

        # 4. Limit cycle (phase portrait)
        axes[1, 1].plot(x_ss[0], x_ss[1], 'b-', linewidth=1.5)
        axes[1, 1].set_title("Limit Cycle (Phase Portrait)")
        axes[1, 1].set_xlabel("x₁")
        axes[1, 1].set_ylabel("x₂")
        axes[1, 1].set_aspect('equal')
        axes[1, 1].grid(True, alpha=0.3)

        plt.suptitle(
            f"Floquet Adjoint PPV: {model.name}", fontsize=14, fontweight='bold')
        plt.tight_layout()

        plot_path = os.path.join(os.environ.get("USERPROFILE", "C:\\"), ".gemini", "antigravity-ide",
                                 "brain", "90300897-07a5-4b42-a22c-168f7155fd30", "ppv_adjoint_plot.png")
        plt.savefig(plot_path, dpi=150)
        plt.close()
        print(f"[PPV-ADJ] Saved diagnostic plot.")
    except ImportError:
        print("[WARNING] matplotlib not available, skipping plot.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
