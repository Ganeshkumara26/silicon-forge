"""
siliconforge
============

Open-source PSS/PNoise/PPV simulation infrastructure for BiCMOS PLL design.

This package implements the guidebook's Chapter 2-13 requirements:
- PSS Shooting-Newton for autonomous oscillator convergence
- PPV/Floquet eigenanalysis for ISF extraction
- End-to-end parameter extraction with zero hardcoding
"""

from __future__ import annotations

# Core pipeline
from siliconforge.core.pipeline import (
    SiliconForgePipeline,
    DesignSpecification,
    PipelineState,
)

# Backend classes
from siliconforge.backends.base import (
    CircuitState,
    ReactiveElement,
    ReactiveKind,
    Simulator,
    TransientResult,
    BenchmarkMetrics,
)
from siliconforge.backends.reference_ode import ReferenceOdeBackend
from siliconforge.backends.ngspice_shared import NgspiceSharedBackend

# VCO sizing
from siliconforge.parameter_extraction.vco_core import (
    VCOComponentSizing,
    size_vco_core,
)

# Calibration extraction
from siliconforge.parameter_extraction.calibration import (
    AACParameters,
    AFCParameters,
    ChargePumpParameters,
    extract_aac_parameters,
    extract_afc_parameters,
    extract_charge_pump_parameters,
)

# Solvers
from siliconforge.solvers.pss_shooting import PSSResult, shoot_newton, find_limit_cycle_period
from siliconforge.solvers.ppv_eigenanalysis import (
    compute_monodromy_matrix,
    extract_ppv,
    compute_isf_dc_coefficient,
    analyze_phase_noise_vulnerability,
)
from siliconforge.solvers.harmonic_balance import (
    HarmonicBalanceResult,
    harmonic_balance_tran,
)

# RTL generation
from siliconforge.rtl_generator import (
    generate_aac_fsm,
    generate_afc_fsm,
    generate_master_controller,
    generate_sdc_constraints,
)

# Numerical methods
from siliconforge.numerical.gmres import matrix_free_gmres, arnoldi_iteration
from siliconforge.numerical.sparse_lu import sparse_lu_factorize, sparse_lu_solve
from siliconforge.numerical.implicit_ode import integrate_implicit_bdf, integrate_stiff_trbdf2

# Device characterization
from siliconforge.device_characterization.mos import characterize_mos_sg13g2, MOSCharacteristics
from siliconforge.device_characterization.hbt import characterize_hbt_sg13g2, HBTCharacteristics
from siliconforge.device_characterization.varactor import characterize_varactor_sg13g2, VaractorCharacteristics
from siliconforge.device_characterization.inductor import size_inductor_sg13g2, InductorCharacteristics

# Analog design
from siliconforge.analog.tank_synthesis import synthesize_tank, TankSynthesisResult

# Digital RTL flow
from siliconforge.digital.rtl_flow import lint_rtl, synthesize_rtl

# Optimization
from siliconforge.optimization import (
    OptimizationResult,
    single_objective_optimize,
    multi_objective_optimize,
    genetic_algorithm,
    compute_pareto_front,
    sensitivity_analysis,
)

# Mixed-signal
from siliconforge.mixed_signal import (
    MixedSignalInterface,
    connect_blocks,
    synchronize_clocks,
    calibrate_loop,
    end_to_end_simulation,
)

# Layout
from siliconforge.layout import (
    LayoutCell,
    place_devices,
    create_matching_pair,
    add_guard_rings,
)

# Reporting
from siliconforge.reporting import (
    PhaseNoiseReport,
    generate_phase_noise_report,
    generate_jitter_report,
    generate_github_readme,
)
from siliconforge.automation import (
    ProjectConfig,
    generate_project,
    pipeline_manager,
)
from siliconforge.equation_engine import (
    Equation,
    EquationMetadata,
    register_equation,
    parse_equation,
    compute_sensitivity,
)

__all__ = [
    # Core
    "SiliconForgePipeline",
    "DesignSpecification",
    "PipelineState",
    # Backend classes
    "CircuitState",
    "ReactiveElement",
    "ReactiveKind",
    "Simulator",
    "TransientResult",
    "BenchmarkMetrics",
    "ReferenceOdeBackend",
    "NgspiceSharedBackend",
    # VCO sizing
    "VCOComponentSizing",
    "size_vco_core",
    # Calibration extraction
    "AACParameters",
    "AFCParameters",
    "ChargePumpParameters",
    "extract_aac_parameters",
    "extract_afc_parameters",
    "extract_charge_pump_parameters",
    # Solvers
    "PSSResult",
    "shoot_newton",
    "find_limit_cycle_period",
    "compute_monodromy_matrix",
    "extract_ppv",
    "compute_isf_dc_coefficient",
    "analyze_phase_noise_vulnerability",
    "HarmonicBalanceResult",
    "harmonic_balance_tran",
    # RTL generation
    "generate_aac_fsm",
    "generate_afc_fsm",
    "generate_master_controller",
    "generate_sdc_constraints",
    # Numerical methods
    "matrix_free_gmres",
    "arnoldi_iteration",
    "sparse_lu_factorize",
    "sparse_lu_solve",
    "integrate_implicit_bdf",
    "integrate_stiff_trbdf2",
    # Device characterization
    "characterize_mos_sg13g2",
    "MOSCharacteristics",
    "characterize_hbt_sg13g2",
    "HBTCharacteristics",
    "characterize_varactor_sg13g2",
    "VaractorCharacteristics",
    "size_inductor_sg13g2",
    "InductorCharacteristics",
    # Analog design
    "synthesize_tank",
    "TankSynthesisResult",
    # Digital RTL flow
    "lint_rtl",
    "synthesize_rtl",
    # Optimization
    "OptimizationResult",
    "single_objective_optimize",
    "multi_objective_optimize",
    "genetic_algorithm",
    "compute_pareto_front",
    "sensitivity_analysis",
    # Mixed-signal
    "MixedSignalInterface",
    "connect_blocks",
    "synchronize_clocks",
    "calibrate_loop",
    "end_to_end_simulation",
    # Layout
    "LayoutCell",
    "place_devices",
    "create_matching_pair",
    "add_guard_rings",
    # Reporting
    "PhaseNoiseReport",
    "generate_phase_noise_report",
    "generate_jitter_report",
    "generate_github_readme",
    # Automation
    "ProjectConfig",
    "generate_project",
    "pipeline_manager",
    # Equation Engine
    "Equation",
    "EquationMetadata",
    "register_equation",
    "parse_equation",
    "compute_sensitivity",
]
