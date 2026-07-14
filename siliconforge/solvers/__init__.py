"""
siliconforge.solvers
====================

Matrix-free GMRES shooting-Newton solver stack.

Implements guidebook Chapter 4 PSS/PNoise/PPV without Spectre dependency.
"""

from __future__ import annotations

from siliconforge.solvers.pnoise_analysis import (
    CircuitPart,
    CircuitPartNoiseModel,
    MultiPartPhaseNoiseAnalyzer,
    MultiPartPhaseNoiseReport,
    compute_ppv_phase_noise,
    compute_phase_noise_spectrum,
    leeson_phase_noise,
    PNoiseReport,
)
from siliconforge.solvers.ppv_eigenanalysis import (
    compute_isf_dc_coefficient,
    compute_isf_waveform,
    compute_monodromy_matrix,
    extract_ppv,
    extract_ppv_from_transient,
)
from siliconforge.solvers.pss_shooting import PSSResult, find_limit_cycle_period, shoot_newton
from siliconforge.solvers.harmonic_balance import (
    HarmonicBalanceResult,
    analyze_mixer_harmonics,
    compute_distortion,
    harmonic_balance_tran,
)

__all__ = [
    "PSSResult",
    "shoot_newton",
    "find_limit_cycle_period",
    "compute_monodromy_matrix",
    "extract_ppv",
    "extract_ppv_from_transient",
    "compute_isf_dc_coefficient",
    "compute_isf_waveform",
    "analyze_phase_noise_vulnerability",
    "HarmonicBalanceResult",
    "harmonic_balance_tran",
    "compute_distortion",
    "analyze_mixer_harmonics",
    "leeson_phase_noise",
    "compute_phase_noise_spectrum",
    "compute_ppv_phase_noise",
    "CircuitPart",
    "CircuitPartNoiseModel",
    "MultiPartPhaseNoiseAnalyzer",
    "MultiPartPhaseNoiseReport",
    "PNoiseReport",
]
