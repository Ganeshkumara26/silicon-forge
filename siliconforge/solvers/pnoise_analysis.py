"""
siliconforge.solvers.pnoise_analysis
=====================================

Phase Noise analysis via Floquet perturbation (PNoise-equivalent).

Implements guidebook Chapter 4.7 PNoise without Spectre.
Uses ISF (Impulse Sensitivity Function) from PPV analysis.

The phase noise L(f) is computed from noise current spectral densities
projected onto the ISF direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

__all__ = [
    "CircuitPart",
    "CircuitPartNoiseModel",
    "MultiPartPhaseNoiseReport",
    "MultiPartPhaseNoiseAnalyzer",
    "leeson_phase_noise",
    "compute_phase_noise_spectrum",
    "compute_ppv_phase_noise",
    "PNoiseReport",
]


def leeson_phase_noise(
    f_osc_hz: float,
    f_offset_hz: float,
    v_swing_v: float,
    q_loaded: float,
    f_corner_hz: float = 100e3,
    noise_figure_db: float = 6.0,
    temperature_k: float = 300.0,
) -> float:
    """Compute single-sideband phase noise via the Leeson model.

    Standard Leeson formula:
        L(fm) = 10*log10[ (2*k_B*T*F / P) * (1 + (f0/(2*Q*fm))^2) * (1 + fc/fm) ]

    Parameters
    ----------
    f_osc_hz : float
        Carrier frequency [Hz]
    f_offset_hz : float
        Offset frequency from carrier [Hz]
    v_swing_v : float
        Peak-to-peak voltage swing [V]
    q_loaded : float
        Loaded quality factor of the tank
    f_corner_hz : float
        Flicker (1/f) noise corner frequency [Hz]
    noise_figure_db : float
        Active device noise figure [dB]
    temperature_k : float
        Temperature [K]

    Returns
    -------
    float : Single-sideband phase noise L(f) in dBc/Hz
    """
    if f_offset_hz < 1.0:
        raise ValueError(f"f_offset_hz must be >= 1 Hz; got {f_offset_hz}")

    k_B = 1.38e-23          # Boltzmann constant [J/K]
    t = temperature_k        # Temperature [K]
    f_lin = 10.0 ** (noise_figure_db / 10.0)  # Noise figure (linear)

    # Signal power: P = Vrms^2 / R. For a tank with peak-to-peak swing Vpp:
    # Vrms ≈ Vpp / (2*sqrt(2)), so P ≈ (Vpp^2) / (8*R). We use the proportional
    # quantity (no R) since Leeson model is typically calibrated empirically.
    signal_power = (v_swing_v ** 2) / 8.0  # proportional to actual power

    # Thermal noise floor: 2*k_B*T*F / P
    # Factor of 2 converts one-sided L(f) to double-sideband S_phi
    thermal_noise = 2.0 * k_B * t * f_lin / signal_power if signal_power > 0 else float('inf')

    # Resonance term: (1 + (f0/(2*Q*fm))^2) creates the 1/f^2 slope
    resonance_term = 1.0 + (f_osc_hz / (2.0 * q_loaded * f_offset_hz)) ** 2

    # Flicker term: (1 + fc/fm) adds 1/f noise below the corner
    flicker_term = 1.0 + (f_corner_hz / f_offset_hz)

    # Combined Leeson model
    noise_linear = thermal_noise * resonance_term * flicker_term

    return 10.0 * math.log10(max(noise_linear, 1e-30))


def compute_phase_noise_spectrum(
    f_osc_hz: float,
    v_swing_v: float,
    q_loaded: float,
    f_offsets_hz: list[float] | np.ndarray,
) -> dict[float, float]:
    """Compute phase noise spectrum L(f) at multiple offset frequencies."""
    return {float(f): leeson_phase_noise(f_osc_hz, float(f), v_swing_v, q_loaded) for f in f_offsets_hz}


@dataclass(frozen=True)
class CircuitPart:
    """One noise-contributing slice of the VCO/PLL.

    Attributes:
        name:         Human-readable label used in reports.
        noise_density_a_per_hz: White thermal noise current spectral density (A/√Hz).
        flicker_corner_hz:      1/f corner frequency in Hz.
        flicker_alpha:           Flicker noise exponent slope factor.
        weight:       Relative coupling weight to phase (default 1.0).
    """

    name: str
    noise_density_a_per_hz: float
    flicker_corner_hz: float = 1e6
    flicker_alpha: float = 1.0
    weight: float = 1.0


@dataclass(frozen=True)
class CircuitPartNoiseModel:
    """Per-circuit-part noise model expressed as spectral density callables.

    Attributes:
        name: Circuit part name.
        white_noise_density_a_per_sqrt_hz: White noise (A/√Hz).
        flicker_corner_hz: 1/f corner frequency.
        flicker_alpha: Flicker coefficient.
        injection_node: Node where the noise source is injected.
    """

    name: str
    white_noise_density_a_per_sqrt_hz: float = 0.0
    flicker_corner_hz: float = 1e6
    flicker_alpha: float = 1.0
    injection_node: str = ""


def compute_ppv_phase_noise(
    ppv: np.ndarray,
    noise_current_density_a_per_hz: float,
    i_cp_a: float = 0.0,
    v_swing_v: float = 0.3,
) -> float:
    """Compute phase noise standard deviation from PPV projection.

    Returns phase std per √Hz.
    """
    if noise_current_density_a_per_hz < 0:
        raise ValueError(
            f"noise_current_density_a_per_hz must be >= 0; got {noise_current_density_a_per_hz}")
    pp_intensity = np.sum(np.asarray(ppv, dtype=float) ** 2)
    phase_std_per_sqrt_hz = pp_intensity * noise_current_density_a_per_hz
    return float(phase_std_per_sqrt_hz)


def _thermal_noise_spectral_density(part: CircuitPart, f_offset_hz: float) -> float:
    return (part.noise_density_a_per_hz ** 2) * (part.weight ** 2)


def _flicker_noise_spectral_density(part: CircuitPart, f_offset_hz: float) -> float:
    fc = part.flicker_corner_hz
    return (part.noise_density_a_per_hz ** 2) * (fc / f_offset_hz) * (part.flicker_alpha ** 2) * (part.weight ** 2)


def _phase_noise_from_ppv(
    ppv: np.ndarray,
    isf: np.ndarray,
    noise_spectral_density_a2_per_hz: float,
    f_offset_hz: float,
    f_osc_hz: float,
    v_swing_v: float,
) -> float:
    isf_rms = float(np.linalg.norm(isf)) / \
        np.sqrt(len(isf)) if len(isf) > 0 else 0.0
    signal_power = v_swing_v ** 2

    # Phase noise falls off at 1/f^2 relative to the carrier
    transfer_function = (f_osc_hz / (2.0 * f_offset_hz)) ** 2 if f_offset_hz > 0 else 1.0
    projected_noise = (isf_rms ** 2) * noise_spectral_density_a2_per_hz * transfer_function

    if projected_noise <= 0:
        return -200.0
    return 10.0 * math.log10(projected_noise / signal_power)


@dataclass
class MultiPartPhaseNoiseReport:
    """Phase noise report broken down by circuit part."""

    f_osc_hz: float
    v_swing_v: float
    q_loaded: float
    ppv: np.ndarray
    isf: np.ndarray
    c0: float
    offsets_hz: list[float]
    total_phase_noise_db: dict[float, float]
    part_contributions_db: dict[str, dict[float, float]]
    dominant_parts: dict[float, str]

    def to_markdown(self) -> str:
        lines = [
            "# Multi-Part Phase Noise Report",
            "",
            f"**Oscillation Frequency:** {self.f_osc_hz / 1e6:.2f} MHz",
            f"**ISF DC Coefficient (c0):** {self.c0:.4f}",
            "",
            "## Summary at 1 MHz Offset",
            "",
            "| Offset (MHz) | Total (dBc/Hz) | Dominant Part |",
            "|--------------|----------------|---------------|",
        ]
        for f in sorted(self.total_phase_noise_db.keys()):
            dominant = self.dominant_parts.get(f, "n/a")
            lines.append(
                f"| {f * 1e-6:.3f} | {self.total_phase_noise_db[f]:.1f} | {dominant} |")
        lines.append("")
        lines.append("## Per-Part Contributions")
        for part_name, contrib in self.part_contributions_db.items():
            lines.append(f"### {part_name}")
            lines.append("")
            lines.append("| Offset (MHz) | PN (dBc/Hz) |")
            lines.append("|--------------|-------------|")
            for f, val in contrib.items():
                lines.append(f"| {f * 1e-6:.3f} | {val:.1f} |")
            lines.append("")
        return "\n".join(lines)


class MultiPartPhaseNoiseAnalyzer:
    """Phase noise analyzer that breaks down contributions by circuit part.

    Usage:
        analyzer = MultiPartPhaseNoiseAnalyzer(f_osc_hz=10.25e9, v_swing_v=0.7, q_loaded=15.0)
        analyzer.add_part(CircuitPart(name="cross_coupled", noise_density_a_per_hz=1e-9))
        analyzer.add_part(CircuitPart(name="tail", noise_density_a_per_hz=0.5e-9))
        report = analyzer.compute(ppv, isf, offsets_hz=[1e6, 1e7, 1e8])
    """

    def __init__(
        self,
        f_osc_hz: float,
        v_swing_v: float,
        q_loaded: float,
    ) -> None:
        self.f_osc_hz = float(f_osc_hz)
        self.v_swing_v = float(v_swing_v)
        self.q_loaded = float(q_loaded)
        self.parts: list[CircuitPart] = []

    def add_part(self, part: CircuitPart) -> None:
        self.parts.append(part)

    def compute(
        self,
        ppv: np.ndarray,
        isf: np.ndarray,
        offsets_hz: Sequence[float],
    ) -> MultiPartPhaseNoiseReport:
        ppv = np.asarray(ppv, dtype=float)
        isf = np.asarray(isf, dtype=float)
        offsets = [float(f) for f in offsets_hz]

        total_db: dict[float, float] = {}
        part_db: dict[str, dict[float, float]] = {
            p.name: {} for p in self.parts}
        dominant_parts: dict[float, str] = {}

        for f in offsets:
            linear_parts: list[float] = []
            for part in self.parts:
                white = _thermal_noise_spectral_density(part, f)
                flicker = _flicker_noise_spectral_density(part, f)
                noise_spectral = white + flicker
                part_linear = 10.0 ** (_phase_noise_from_ppv(ppv, isf,
                                       noise_spectral, f, self.f_osc_hz, self.v_swing_v) / 10.0)
                part_db[part.name][f] = 10.0 * \
                    math.log10(part_linear) if part_linear > 0 else -200.0
                linear_parts.append(part_linear)
            total_linear = sum(linear_parts)
            total_db[f] = 10.0 * \
                math.log10(total_linear) if total_linear > 0 else -200.0
            if self.parts and linear_parts:
                max_idx = int(np.argmax(linear_parts))
                dominant_parts[f] = self.parts[max_idx].name

        c0 = float(np.mean(isf)) if isf.size else 0.0
        return MultiPartPhaseNoiseReport(
            f_osc_hz=self.f_osc_hz,
            v_swing_v=self.v_swing_v,
            q_loaded=self.q_loaded,
            ppv=ppv,
            isf=isf,
            c0=c0,
            offsets_hz=offsets,
            total_phase_noise_db=total_db,
            part_contributions_db=part_db,
            dominant_parts=dominant_parts,
        )


@dataclass
class PNoiseReport:
    """Complete phase noise analysis report."""

    f_osc_hz: float
    phase_noise_db: dict[float, float]  # offset_hz -> dBc/Hz
    isf_dc_coefficient: float
    flicker_upconversion_factor: float
    recommended_action: str

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            f"# PNoise Analysis Report",
            "",
            f"**Oscillation Frequency:** {self.f_osc_hz / 1e6:.2f} MHz",
            f"**ISF DC Coefficient (c0):** {self.isf_dc_coefficient:.4f}",
            f"**Flicker Upconversion:** {self.flicker_upconversion_factor:.2e}",
            f"**Recommendation:** {self.recommended_action}",
            "",
            "## Phase Noise Spectrum",
            "",
            "| Offset (kHz) | Phase Noise (dBc/Hz) |",
            "|-------------|---------------------|",
        ]

        for offset in sorted(self.phase_noise_db.keys()):
            lines.append(
                f"| {offset / 1e3:.0f} | {self.phase_noise_db[offset]:.1f} |")

        return "\n".join(lines)
