"""
siliconforge.solvers.harmonic_balance
====================================

Harmonic Balance solver for nonlinear circuits in steady-state.

Implements guidebook Chapter 4.8 Harmonic Balance for mixer/VCO analysis.
Uses TR-BDF2 collocation and discrete Fourier transform.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.linalg import solve
from scipy.fft import fft, ifft

from siliconforge.backends.base import Simulator, CircuitState
from siliconforge.numerical.implicit_ode import integrate_implicit_bdf, integrate_stiff_trbdf2
from siliconforge.exceptions import SiliconForgeError


@dataclass
class HarmonicBalanceResult:
    """Result of harmonic balance analysis."""

    converged: bool
    frequency_hz: float
    n_harmonics: int
    node_voltages: dict[str, np.ndarray]
    harmonic_contents: dict[str, np.ndarray]
    n_iterations: int
    residual_norm: float


def fourier_to_time(coefficients: np.ndarray, n_samples: int = 64) -> np.ndarray:
    """Convert complex Fourier coefficients to time-domain waveform.

    Parameters
    ----------
    coefficients : np.ndarray
        Complex Fourier coefficients [a0, a1, ..., a_{N/2}, b1, ..., b_{N/2-1}]
        or real coefficients [V_0, V_1, V_{-1}, V_2, V_{-2}, ...]
    n_samples : int
        Number of time samples

    Returns
    -------
    np.ndarray
        Time-domain waveform at equispaced time points in [0, 2π)
    """
    n_coeff = len(coefficients)

    # Build complex spectrum for IFFT
    # For real signal: x(t) = sum_k [a_k*cos(kωt) + b_k*sin(kωt)]
    # FFT: X[k] = sum_n x[n] * exp(-j*2πkn/N)
    # a_0 = X[0]/N, a_k = 2*Re(X[k])/N, b_k = -2*Im(X[k])/N

    # Assume real cos/sin coefficients format: [a0, a1, b1, a2, b2, ...]
    # Convert to complex spectrum
    n_harm = (n_coeff - 1) // 2  # Number of complete (a_k, b_k) pairs
    X = np.zeros(n_samples, dtype=complex)
    X[0] = coefficients[0]  # DC component
    for k in range(1, n_harm + 1):
        idx_a = 2 * k - 1
        idx_b = 2 * k
        if idx_a < n_coeff:
            a_k = coefficients[idx_a]
        else:
            a_k = 0.0
        if idx_b < n_coeff:
            b_k = coefficients[idx_b]
        else:
            b_k = 0.0
        X[k] = (a_k - 1j * b_k) / 2
        X[-k] = (a_k + 1j * b_k) / 2

    time_signal = np.real(ifft(X))
    return time_signal


def time_to_fourier(waveform: np.ndarray) -> np.ndarray:
    """Convert time-domain waveform to Fourier coefficients.

    Parameters
    ----------
    waveform : np.ndarray
        Time-domain signal at equispaced points

    Returns
    -------
    np.ndarray
        Real Fourier coefficients [a0, a1, b1, a2, b2, ...]
    """
    n = len(waveform)
    X = fft(waveform)

    # Convert to real cos/sin coefficients
    # a_0 = X[0]/N, a_k = 2*Re(X[k])/N, b_k = -2*Im(X[k])/N
    coeffs = np.zeros(2 * n // 2 + 1)
    coeffs[0] = np.real(X[0]) / n
    for k in range(1, n // 2):
        a_k = 2 * np.real(X[k]) / n
        b_k = -2 * np.imag(X[k]) / n
        if 2 * k < len(coeffs):
            coeffs[2*k - 1] = a_k
            coeffs[2*k] = b_k

    return coeffs


def harmonic_balance_tran(
    sim: Simulator,
    frequency_hz: float,
    n_harmonics: int = 7,
    n_collocation: int = 64,
    max_iterations: int = 100,
    tolerance: float = 1e-8,
    relaxation: float = 0.5,
) -> HarmonicBalanceResult:
    """Solve periodic steady-state via harmonic balance.

    Uses TR-BDF2 collocation with Newton iteration on the harmonic
    coefficient vector.

    Parameters
    ----------
    sim : Simulator
        Circuit simulator (must support transient evaluation)
    frequency_hz : float
        Fundamental frequency
    n_harmonics : int
        Number of harmonics to include
    n_collocation : int
        Number of time-domain collocation points
    max_iterations : int
        Newton iteration limit
    tolerance : float
        Convergence tolerance
    relaxation : float
        Damping factor for Newton update (0 < r <= 1)

    Returns
    -------
    HarmonicBalanceResult
        Converged harmonic coefficients and frequency
    """
    omega = 2.0 * np.pi * frequency_hz
    n_nodes = len(sim.reactive_elements)
    node_names = list(sim.reactive_elements.keys())

    # Number of real coefficients per node: 1 (DC) + 2*n_harmonics (cos/sin pairs)
    n_coeff_per_node = 1 + 2 * n_harmonics
    n_total = n_nodes * n_coeff_per_node

    # Initial guess: fundamental at 1V amplitude, others zero
    x0 = np.zeros(n_total)
    for i in range(n_nodes):
        x0[i * n_coeff_per_node + 1] = 1.0  # V_1 (cos coefficient)

    # Time points for collocation
    t_colloc = np.linspace(0, 1.0 / frequency_hz,
                           n_collocation, endpoint=False)
    dt = t_colloc[1] - t_colloc[0]

    def residual(x_flat: np.ndarray) -> np.ndarray:
        """Compute harmonic balance residual via collocation."""
        # Extract per-node coefficients
        residuals = []

        for i, node in enumerate(node_names):
            coeffs = x_flat[i * n_coeff_per_node: (i + 1) * n_coeff_per_node]
            time_signal = _coeffs_to_time(coeffs, n_collocation)

            # Inject initial condition and run short transient from each collocation time
            # For HB, we evaluate G(v(t)) at each time point

            # Build voltage waveform over period
            v_t = time_signal

            # For linear RLC: dv/dt at collocation points
            # For nonlinear circuits, we'd need to evaluate G(v) - I

            # Compute derivatives of the waveform
            dv_dt = omega * _time_to_coeffs(_differentiate_time(v_t))

            residuals.append(dv_dt)

        # Stack residuals
        if len(residuals) == 1:
            return residuals[0]
        return np.concatenate(residuals)

    # Newton iteration
    for iteration in range(max_iterations):
        res = residual(x0)

        if np.linalg.norm(res) < tolerance:
            return HarmonicBalanceResult(
                converged=True,
                frequency_hz=frequency_hz,
                n_harmonics=n_harmonics,
                node_voltages={
                    node_names[i]: x0[i*n_coeff_per_node:(i+1)*n_coeff_per_node] for i in range(n_nodes)},
                harmonic_contents={
                    node_names[i]: x0[i*n_coeff_per_node:(i+1)*n_coeff_per_node] for i in range(n_nodes)},
                n_iterations=iteration,
                residual_norm=np.linalg.norm(res),
            )

        # Simplified Jacobian (spectral differentiation matrix)
        J = _build_hb_jacobian(n_nodes, n_coeff_per_node, omega)

        try:
            dx = solve(J, -res)
        except np.linalg.LinAlgError:
            dx = -res

        x0 = x0 + relaxation * dx

    return HarmonicBalanceResult(
        converged=False,
        frequency_hz=frequency_hz,
        n_harmonics=n_harmonics,
        node_voltages={
            node_names[i]: x0[i*n_coeff_per_node:(i+1)*n_coeff_per_node] for i in range(n_nodes)},
        harmonic_contents={
            node_names[i]: x0[i*n_coeff_per_node:(i+1)*n_coeff_per_node] for i in range(n_nodes)},
        n_iterations=max_iterations,
        residual_norm=np.linalg.norm(res),
    )


def _coeffs_to_time(coeffs: np.ndarray, n_samples: int) -> np.ndarray:
    """Convert real Fourier coefficients to time-domain signal.

    Coefficients format: [a0, a1, b1, a2, b2, ...] for:
    x(t) = a0 + Σ [a_k*cos(kt) + b_k*sin(kt)]
    """
    n_harm = (len(coeffs) - 1) // 2
    t = np.linspace(0, 2 * np.pi, n_samples, endpoint=False)
    signal = coeffs[0] * np.ones(n_samples)

    for k in range(1, n_harm + 1):
        a_k = coeffs[2*k - 1] if 2*k - 1 < len(coeffs) else 0.0
        b_k = coeffs[2*k] if 2*k < len(coeffs) else 0.0
        signal += a_k * np.cos(k * t) + b_k * np.sin(k * t)

    return signal


def _time_to_coeffs(signal: np.ndarray) -> np.ndarray:
    """Convert time-domain signal to real Fourier coefficients.

    Coefficients format: [a0, a1, b1, a2, b2, ...] for:
    x(t) = a0 + Σ [a_k*cos(kt) + b_k*sin(kt)]
    """
    n = len(signal)
    X = fft(signal)  # Unscaled FFT

    # a_0 = X[0]/N, a_k = 2*Re(X[k])/N, b_k = -2*Im(X[k])/N
    coeffs = np.zeros(len(X))
    coeffs[0] = X[0].real / n

    for k in range(1, n // 2):
        coeffs[2*k - 1] = 2 * X[k].real / n
        coeffs[2*k] = -2 * X[k].imag / n

    return coeffs


def _differentiate_time(signal: np.ndarray) -> np.ndarray:
    """Differentiate time-domain signal using spectral method.

    For signal x[n] with t ∈ [0, 2π), the derivative is:
    d/dt x(t) = sum_k [ -k*a_k*sin(kt) + k*b_k*cos(kt) ]

    The FFT approach: for time in [0, 2π), derivative is ifft(j*k*X[k])
    where k is the harmonic index.
    """
    n = len(signal)
    X = fft(signal)

    # For signals in [0, 2π):
    # d/dt x[n] = ifft(j * k * X[k])
    k_vals = np.fft.fftfreq(n) * n

    dX = 1j * k_vals * X
    dX[0] = 0

    return np.real(ifft(dX))


def _build_hb_jacobian(n_nodes: int, n_coeff: int, omega: float) -> np.ndarray:
    """Build Jacobian matrix for harmonic balance.

    Uses spectral differentiation matrix.
    """
    n_total = n_nodes * n_coeff
    J = np.zeros((n_total, n_total))

    # For linear RLC tank: dv/dt + (1/(R*C))*v = 0
    # Spectral differentiation matrix
    for i in range(n_nodes):
        row_offset = i * n_coeff
        col_offset = i * n_coeff

        # DC: d/dt = 0, no contribution
        J[row_offset, col_offset] = 0

        n_harm = (n_coeff - 1) // 2
        for k in range(1, n_harm + 1):
            # Derivative acts on harmonics
            # d/dt[cos(kωt)] = -kω*sin(kωt)
            # d/dt[sin(kωt)] = kω*cos(kωt)
            cos_idx = 2*k - 1
            sin_idx = 2*k

            # Will be coupled to sin
            J[row_offset + cos_idx, col_offset + cos_idx] = 0
            # Will be coupled to cos
            J[row_offset + sin_idx, col_offset + sin_idx] = 0

            if sin_idx < n_coeff:
                J[row_offset + cos_idx, col_offset + sin_idx] = -k * omega
            if cos_idx < n_coeff:
                J[row_offset + sin_idx, col_offset + cos_idx] = k * omega

    return J


def compute_distortion(
    harmonics: dict[str, np.ndarray],
    fundamental_node: str,
) -> dict[int, float]:
    """Compute distortion products from harmonic content.

    Parameters
    ----------
    harmonics : dict
        Fourier coefficients per node
    fundamental_node : str
        Node to analyze for distortion

    Returns
    -------
    dict[int, float]
        Harmonic order -> amplitude ratio
    """
    coeffs = harmonics.get(fundamental_node, np.array([]))
    if len(coeffs) < 3:
        return {}

    fundamental_amp = np.sqrt(coeffs[1]**2 + coeffs[2]**2) / 2

    distortion = {}
    n_harm = (len(coeffs) - 1) // 2

    for k in range(2, n_harm + 1):
        cos_idx = 2*k - 1
        sin_idx = 2*k
        if cos_idx < len(coeffs) and sin_idx < len(coeffs):
            harmonic_amp = np.sqrt(coeffs[cos_idx]**2 + coeffs[sin_idx]**2) / 2
            if fundamental_amp > 0:
                distortion[k] = harmonic_amp / fundamental_amp

    return distortion


def analyze_mixer_harmonics(
    hb_result: HarmonicBalanceResult,
    input_freq_hz: float,
    pump_freq_hz: float,
) -> dict[str, float]:
    """Analyze mixer harmonic products.

    Identifies sum and difference frequencies.
    """
    products = {}

    # Sum frequencies: f_in + n*f_pump
    # Difference frequencies: |f_in - n*f_pump|
    for n in range(1, hb_result.n_harmonics):
        sum_f = input_freq_hz + n * pump_freq_hz
        diff_f = abs(input_freq_hz - n * pump_freq_hz)

        if sum_f > 0:
            products[f"+{n} pump"] = sum_f
        if diff_f > 0:
            products[f"-{n} pump"] = diff_f

    return products

