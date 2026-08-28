#!/usr/bin/env python3
"""design_config.py — Design Configuration Abstraction

Separates framework from any specific design (e.g., ADPLL).
Allows SiliconForge to accept arbitrary circuit descriptions via YAML/JSON.

Example YAML:
    design:
      name: my_vco
      pdk: ihp_sg13g2
      simulator: ngspice

    pss:
      fundamental_frequency: auto
      convergence_tolerance: 1e-9
      max_iterations: 50

    ppv:
      method: adjoint
      phase_points: 64
      charge_injection_fc: 5.0

    noise:
      carrier_frequency: ${pss.frequency}
      offset_range_hz: [1e3, 1e9]
      offset_points: 200

    jitter:
      fmin_hz: 10e3
      fmax_hz: 1e9
      integration_method: curve

    formal:
      solver: z3
      proof_depth: 20
"""

import os
import json
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Union

import yaml


@dataclass
class PSSConfig:
    """Periodic Steady State solver configuration."""
    fundamental_frequency: Union[float, str] = "auto"
    convergence_tolerance: float = 1e-9
    max_iterations: int = 50
    initial_period_s: Optional[float] = None
    transient_crosscheck: bool = True


@dataclass
class PPVConfig:
    """Perturbation Projection Vector solver configuration."""
    method: str = "adjoint"  # "direct", "adjoint", "eigenanalysis"
    phase_points: int = 64
    charge_injection_fc: float = 5.0
    validate_against: Optional[str] = None  # cross-check method


@dataclass
class NoiseConfig:
    """Phase noise analysis configuration."""
    carrier_frequency: Union[float, str] = "auto"
    offset_range_hz: List[float] = field(default_factory=lambda: [1e3, 1e9])
    offset_points: int = 200
    include_flicker: bool = True
    include_thermal: bool = True
    reference_crosscheck: bool = False


@dataclass
class JitterConfig:
    """Jitter calculation configuration."""
    fmin_hz: float = 10e3
    fmax_hz: float = 1e9
    integration_method: str = "curve"  # "curve" or "single_point"
    convention: str = "one-sided"


@dataclass
class FormalConfig:
    """Formal verification configuration."""
    solver: str = "z3"
    proof_depth: int = 20
    properties: List[str] = field(default_factory=lambda: [
        "safety", "liveness", "interface"
    ])


@dataclass
class DesignConfig:
    """Complete design configuration for SiliconForge.

    This is the single entry point for describing a design to the framework.
    No ADPLL-specific assumptions are embedded.
    """
    name: str = "unnamed_design"
    pdk: str = "ihp_sg13g2"
    simulator: str = "ngspice"
    description: str = ""

    pss: PSSConfig = field(default_factory=PSSConfig)
    ppv: PPVConfig = field(default_factory=PPVConfig)
    noise: NoiseConfig = field(default_factory=NoiseConfig)
    jitter: JitterConfig = field(default_factory=JitterConfig)
    formal: FormalConfig = field(default_factory=FormalConfig)

    # Design-specific parameters (arbitrary key-value)
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Netlist / RTL paths
    netlist_path: Optional[str] = None
    rtl_path: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization (nested format)."""
        return {
            "design": {
                "name": self.name,
                "pdk": self.pdk,
                "simulator": self.simulator,
                "description": self.description,
            },
            "pss": asdict(self.pss),
            "ppv": asdict(self.ppv),
            "noise": asdict(self.noise),
            "jitter": asdict(self.jitter),
            "formal": asdict(self.formal),
            "parameters": self.parameters,
            "netlist_path": self.netlist_path,
            "rtl_path": self.rtl_path,
        }

    def to_json(self, path: str):
        """Save configuration to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def to_yaml(self, path: str):
        """Save configuration to YAML file."""
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

    def resolve_references(self):
        """Resolve ${...} references between config sections."""
        if self.pss.fundamental_frequency == "auto":
            if "f0" in self.parameters:
                self.pss.fundamental_frequency = float(self.parameters["f0"])

        if self.noise.carrier_frequency == "auto":
            if isinstance(self.pss.fundamental_frequency, (int, float)):
                self.noise.carrier_frequency = self.pss.fundamental_frequency
            elif "f0" in self.parameters:
                self.noise.carrier_frequency = float(self.parameters["f0"])

        if isinstance(self.noise.carrier_frequency, (int, float)):
            if self.jitter.fmax_hz == 1e9:
                self.jitter.fmax_hz = self.noise.carrier_frequency / 2.0


def load_config(path: str) -> DesignConfig:
    """Load design configuration from YAML or JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Design config not found: {path}")

    with open(path) as f:
        if path.suffix in (".yaml", ".yml"):
            raw = yaml.safe_load(f)
        else:
            raw = json.load(f)

    return _dict_to_config(raw)


def _dict_to_config(raw: dict) -> DesignConfig:
    """Parse a raw dictionary into a DesignConfig."""
    design = raw.get("design", {})
    pss_raw = raw.get("pss", {})
    ppv_raw = raw.get("ppv", {})
    noise_raw = raw.get("noise", {})
    jitter_raw = raw.get("jitter", {})
    formal_raw = raw.get("formal", {})

    return DesignConfig(
        name=design.get("name", "unnamed_design"),
        pdk=design.get("pdk", "ihp_sg13g2"),
        simulator=design.get("simulator", "ngspice"),
        description=design.get("description", ""),
        pss=PSSConfig(**{k: v for k, v in pss_raw.items()
                        if k in PSSConfig.__dataclass_fields__}),
        ppv=PPVConfig(**{k: v for k, v in ppv_raw.items()
                        if k in PPVConfig.__dataclass_fields__}),
        noise=NoiseConfig(**{k: v for k, v in noise_raw.items()
                            if k in NoiseConfig.__dataclass_fields__}),
        jitter=JitterConfig(**{k: v for k, v in jitter_raw.items()
                              if k in JitterConfig.__dataclass_fields__}),
        formal=FormalConfig(**{k: v for k, v in formal_raw.items()
                              if k in FormalConfig.__dataclass_fields__}),
        parameters=raw.get("parameters", {}),
        netlist_path=raw.get("netlist_path"),
        rtl_path=raw.get("rtl_path"),
    )


# =============================================================================
# Preset Configurations for Known Designs
# =============================================================================

def adpll_config() -> DesignConfig:
    """Preset: 10.25 GHz ADPLL (IHP SG13G2)."""
    return DesignConfig(
        name="adpll_10ghz",
        pdk="ihp_sg13g2",
        simulator="ngspice",
        description="10.25 GHz All-Digital PLL with PPV-guided clock generation",
        pss=PSSConfig(fundamental_frequency=10.25e9, convergence_tolerance=1e-9),
        ppv=PPVConfig(method="adjoint", phase_points=64),
        noise=NoiseConfig(carrier_frequency=10.25e9),
        jitter=JitterConfig(fmin_hz=10e3, fmax_hz=1e9),
        formal=FormalConfig(solver="z3", proof_depth=20),
        parameters={
            "f0": 10.25e9,
            "divider": 205,
            "Icp": 1e-3,
            "prescaler_ratio": 5,
            "ref_freq": 50e6,
        },
    )


def lc_vco_config(f0_ghz: float = 5.0) -> DesignConfig:
    """Preset: Generic LC VCO."""
    f0 = f0_ghz * 1e9
    return DesignConfig(
        name=f"lc_vco_{f0_ghz}ghz",
        pdk="ihp_sg13g2",
        simulator="ngspice",
        description=f"LC VCO at {f0_ghz} GHz",
        pss=PSSConfig(fundamental_frequency=f0),
        ppv=PPVConfig(method="adjoint"),
        noise=NoiseConfig(carrier_frequency=f0),
        jitter=JitterConfig(fmin_hz=10e3, fmax_hz=f0 / 2),
        parameters={"f0": f0},
    )


def ring_osc_config(f0_ghz: float = 1.0) -> DesignConfig:
    """Preset: Ring oscillator."""
    f0 = f0_ghz * 1e9
    return DesignConfig(
        name=f"ring_osc_{f0_ghz}ghz",
        pdk="ihp_sg13g2",
        simulator="ngspice",
        description=f"Ring oscillator at {f0_ghz} GHz",
        pss=PSSConfig(fundamental_frequency=f0),
        ppv=PPVConfig(method="direct"),
        noise=NoiseConfig(carrier_frequency=f0),
        jitter=JitterConfig(fmin_hz=1e3, fmax_hz=f0 / 2),
        parameters={"f0": f0, "stages": 5},
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Design Config Tool")
    parser.add_argument("--preset", type=str, default="adpll",
                        choices=["adpll", "lc_vco", "ring_osc"],
                        help="Generate a preset configuration")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (.yaml or .json)")
    args = parser.parse_args()

    presets = {
        "adpll": adpll_config,
        "lc_vco": lc_vco_config,
        "ring_osc": ring_osc_config,
    }

    config = presets[args.preset]()
    config.resolve_references()

    if args.output:
        if args.output.endswith((".yaml", ".yml")):
            config.to_yaml(args.output)
        else:
            config.to_json(args.output)
        print(f"Saved {args.preset} config to {args.output}")
    else:
        print(json.dumps(config.to_dict(), indent=2))
