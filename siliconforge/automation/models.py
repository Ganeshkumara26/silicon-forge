from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class DesignSpecification:
    """Target specifications for the LC VCO PLL."""
    frequency_ghz: float = 10.25
    phase_noise_dbc_at_1mhz: float = -100.0
    reference_mhz: float = 50.0
    loop_bandwidth_khz: float = 2500.0
    charge_pump_uA: float = 500.0
    temperature_min_c: float = -40.0
    temperature_max_c: float = 125.0

@dataclass(frozen=True)
class TransientResult:
    """Parsed Cadence/Spectre transient output."""
    time: list[float]
    signals: dict[str, list[float]]
    n_timepoints: int = 0
    converged: bool = True

@dataclass(frozen=True)
class SimulationRecord:
    """Audit trail for one simulation call."""
    chapter_id: str
    operation_id: str
    tool: str
    netlist: str
    tstop_ns: float
    wall_time_s: float
    return_code: int
    stdout: str
    stderr: str
    output_files: list[str]
    parsed: TransientResult | None = None

@dataclass
class Equation:
    id: str
    guidebook_eq_number: str
    name: str
    latex: str
    variables: list[dict[str, Any]]
    engineering_intent: str
    physical_reasoning: str
    assumptions: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    failure_modes: list[dict[str, str]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    required_solver_types: list[str] = field(default_factory=list)
    simulation_required: dict[str, Any] | None = None
    verification_rule: str | None = None
    source_page: int | None = None
    implementation_python: str | None = None
    correction_loop: dict[str, Any] | None = None

@dataclass
class MROperation:
    id: str
    type: str
    action: str
    target: str
    parameters: dict[str, Any]
    depends_on: list[str]
    produces: list[str]
    optional: bool = False
    correction_loop: dict[str, Any] | None = None

@dataclass
class ChapterSpec:
    id: str
    title: str
    source_pages: list[int] = field(default_factory=list)
    phase: str = ""
    extraction_status: str = "full"
    extraction_coverage: str = ""
    prerequisites: list[str] = field(default_factory=list)
    produces_artifacts: list[str] = field(default_factory=list)
    equations: list[Equation] = field(default_factory=list)
    operations: list[MROperation] = field(default_factory=list)
    engineering_decisions: list[dict[str, Any]] = field(default_factory=list)
    open_source_tools: list[str] = field(default_factory=list)

@dataclass
class ChapterArtifacts:
    """Tracks files produced by a chapter."""
    chapter_id: str
    files: dict[str, Path] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
