# SiliconForge: Mixed-Signal Verification Framework

SiliconForge is an open-source EDA framework for oscillator phase noise characterization and jitter estimation. It extracts oscillation frequency from ngspice transient simulations and estimates phase noise using the Leeson model with corrected jitter integration.

**Validated on:** 5 oscillator topologies (NMOS VCO, HBT VCO, ideal LC VCO, ring oscillator, differential VCO) in IHP SG13G2 and generic models.

**Status:** Core math corrected and validated. Regression suite covers 5 circuits. Phase noise uses Leeson model (not yet validated against SPICE `.noise` — `.noise` analysis doesn't work for free-running oscillators in ngspice).

---

## What SiliconForge Does Well

- **Frequency measurement:** Extracts oscillation frequency from ngspice transient simulations via zero-crossing detection. Validated on 5 circuits.
- **Phase noise estimation:** Uses corrected Leeson model with physics-derived parameters (Q, P, NF).
- **Jitter calculation:** Integrates phase noise with canonical definition. No double-counting.
- **Design abstraction:** YAML/JSON config — no ADPLL-specific hardcodes.
- **Reproducibility:** Fixed seeds, versioned schema, machine-readable results.

## What SiliconForge Does NOT Yet Do

- **UVM/SVA/formal verification:** Not implemented. Previous claims were incorrect.
- **9-stage Xyce pipeline:** Uses Xyce which is blocked on IHP PDK. Use `run_ngspice_pipeline.py` instead.
- **SPICE `.noise` phase noise:** `.noise` analysis doesn't work for oscillators in ngspice (no stable DC point). Transient-based extraction is implemented but needs netlist debugging.
- **Non-oscillatory circuits:** Op-amp, comparator, SAR ADC test methods are stubs.
- **PPV/ISF from transient:** Monodromy matrix construction is approximate (requires system Jacobian for exact result).

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Installation](#installation)
3. [The 9-Stage Pipeline](#the-9-stage-pipeline)
4. [Mixed-Signal Verification Framework](#mixed-signal-verification-framework)
5. [Design Configuration](#design-configuration)
6. [Regression Suite](#regression-suite)
7. [Adding New Designs](#adding-new-designs)
8. [Reproducibility](#reproducibility)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# Run the phase noise pipeline (works end-to-end)
cd siliconforge/automation/rf_pipeline
python run_ngspice_pipeline.py

# Run the mixed-signal verification regression suite
cd siliconforge
python -c "from siliconforge.solvers.regression import RegressionRunner; RegressionRunner(use_spice=True).run_suite()"

# List available test circuits
python -c "from siliconforge.solvers.regression import RegressionRunner; RegressionRunner().list_circuits()"
```

### Pipeline Output

The ngspice pipeline produces:
- Oscillation frequency (from transient zero-crossing detection)
- Phase noise spectrum (from Leeson model)
- RMS jitter (from phase noise integration)
- Machine-readable JSON report

Example output for NMOS VCO at 10.21 GHz:
```
Frequency:    10.2145 GHz
L(1 MHz):     -124.8 dBc/Hz
RMS jitter:   378.8 fs
RMS phase:    1.39 deg
```

---

## Installation

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.10+ | Core framework |
| ngspice | 46+ | SPICE simulation |
| openvaf | latest | Verilog-A compilation |
| WSL | Ubuntu 22.04 | Linux environment for ngspice |
| IHP SG13G2 PDK | 0.3.0 | Device models |

### Environment Setup

```bash
# 1. Create PDK symlink (spaces in paths break ngspice)
wsl bash -c "ln -sf '/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/ppv guided clock generation adpll/vco/IHP-Open-PDK-0.3.0/ihp-sg13g2' /tmp/ihp_sg13g2"

# 2. Copy pre-compiled OSDI files
wsl bash -c "mkdir -p /tmp/ihp_sg13g2/libs.tech/ngspice/va/{psp103,mosvar,r3_cmc}"
wsl bash -c "cp /tmp/ihp_sg13g2/libs.tech/verilog-a/psp103/psp103.osdi /tmp/ihp_sg13g2/libs.tech/ngspice/va/psp103/"
wsl bash -c "cp /tmp/ihp_sg13g2/libs.tech/verilog-a/mosvar/mosvar.osdi /tmp/ihp_sg13g2/libs.tech/ngspice/va/mosvar/"
wsl bash -c "cp /tmp/ihp_sg13g2/libs.tech/verilog-a/r3_cmc/r3_cmc.osdi /tmp/ihp_sg13g2/libs.tech/ngspice/va/r3_cmc/"

# 3. Compile psp103_nqs.osdi (not pre-compiled in PDK)
wsl bash -c "cd '/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/ppv guided clock generation adpll/vco/IHP-Open-PDK-0.3.0/ihp-sg13g2/libs.tech/verilog-a/psp103' && openvaf psp103_nqs.va"
wsl bash -c "cp '/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/ppv guided clock generation adpll/vco/IHP-Open-PDK-0.3.0/ihp-sg13g2/libs.tech/verilog-a/psp103/psp103_nqs.osdi' /tmp/ihp_sg13g2/libs.tech/ngspice/va/psp103_nqs/"

# 4. Install Python dependencies
pip install numpy scipy matplotlib pyyaml jinja2 pytest
```

### Verification

```bash
# Verify ngspice works with PDK
wsl bash -c "export PDK_ROOT='/tmp' && ngspice -b ADPLL_10GHz/analog/vco/vco_nmos_test.cir"
# Expected output: freq = 1.021448e+10
```

---

## The 9-Stage Pipeline (Xyce — Not Usable)

The original pipeline (`run_v1_pipeline.py`) uses Xyce and is **not usable** on IHP PDK (Xyce is blocked). It is kept for reference but will not run.

**Use `run_ngspice_pipeline.py` instead.** It implements a working 4-stage pipeline:

```
Stage 1: Transient Simulation → Stage 2: Leeson Phase Noise → Stage 3: Jitter Integration → Stage 4: Report
```

### Pipeline Outputs

| Output File | Description |
|-------------|-------------|
| `pipeline_results/ngspice_pn_report.json` | Full results: frequency, phase noise spectrum, jitter |

---

## Mixed-Signal Verification Framework

The framework provides reusable infrastructure for verifying mixed-signal designs beyond the ADPLL case study.

### Architecture

```
                    SiliconForge
                        │
          ┌─────────────┼─────────────┐
          ↓             ↓             ↓
     Circuit A      Circuit B      Circuit C
          │             │             │
       SPICE          SPICE         SPICE
          │             │             │
       PSS/PPV       PSS/PPV       PSS/PPV
          │             │             │
      PN/Jitter      PN/Jitter     PN/Jitter
          │             │             │
    Independent ref. Independent ref. Independent ref.
          │             │             │
          └─────────────┼─────────────┘
                        ↓
                  PASS / FAIL
                        ↓
                 RTL generation
                        │
                    Yosys
                        │
                     SMT2
                        │
                      Z3
                        │
              counterexample / PASS
```

### Core Modules

| Module | File | Purpose |
|--------|------|---------|
| Result Schema | `solvers/schema.py` | Canonical JSON result format |
| Regression Suite | `solvers/regression.py` | Multi-circuit test runner |
| Design Config | `solvers/design_config.py` | YAML/JSON design abstraction |
| SPICE Runner | `solvers/spice_runner.py` | WSL/ngspice interface |
| Jitter Engine | `solvers/jitter.py` | Canonical jitter calculation |
| Mutation Tests | `solvers/mutation.py` | Negative testing |

---

## Design Configuration

Designs are described via YAML or JSON — no hardcoded ADPLL assumptions.

### Example: LC VCO

```yaml
design:
  name: lc_vco_5ghz
  pdk: ihp_sg13g2
  simulator: ngspice

pss:
  fundamental_frequency: auto
  convergence_tolerance: 1e-9

ppv:
  method: adjoint
  phase_points: 32

noise:
  carrier_frequency: auto
  offset_range_hz: [1000.0, 500000000.0]

jitter:
  fmin_hz: 1000.0
  fmax_hz: 250000000.0
  integration_method: curve

parameters:
  f0: 5000000000.0
  L_nh: 0.5
  C_total_ff: 200.0
```

### Loading and Using Configs

```python
from siliconforge.solvers.design_config import load_config, adpll_config

# Load from file
config = load_config("my_vco.yaml")

# Use preset
config = adpll_config()

# Resolve auto-references
config.resolve_references()

# Access parameters
print(config.pss.frequency_hz)
print(config.jitter.fmin_hz)
```

### Available Presets

| Preset | Function | Description |
|--------|----------|-------------|
| ADPLL | `adpll_config()` | 10.25 GHz ADPLL (IHP SG13G2) |
| LC VCO | `lc_vco_config(f0_ghz)` | Generic LC VCO |
| Ring Oscillator | `ring_osc_config(f0_ghz)` | Current-starved ring |

---

## Regression Suite

The regression suite runs multiple circuits through the verification pipeline and produces a consolidated report.

### Running

```bash
# Run all circuits (SPICE-enabled)
python -c "from siliconforge.solvers.regression import RegressionRunner; RegressionRunner(use_spice=True).run_suite()"

# Run specific circuits
python -c "from siliconforge.solvers.regression import RegressionRunner; RegressionRunner(use_spice=True).run_suite(['nmos_oscillator', 'hbt_oscillator'])"

# List available circuits
python -c "from siliconforge.solvers.regression import RegressionRunner; RegressionRunner().list_circuits()"
```

### Canonical Test Circuits

| ID | Topology | Netlist | Purpose |
|----|----------|---------|---------|
| `nmos_oscillator` | LC, CMOS | `vco_nmos_test.cir` | Basic PSS validation |
| `hbt_oscillator` | LC, BiCMOS | `vco_hbt_test.cir` | Bipolar device model |
| `lc_vco` | LC, ideal | `lc_vco_ideal.cir` | No PDK required |
| `ring_oscillator` | Digital | `ring_osc_5stage.cir` | Non-LC topology |
| `differential_vco` | LC, differential | `diff_vco_nmos_5ghz.cir` | Symmetry validation |
| `broken_circuit` | — | — | Failure detection (negative test) |

### Output Format

Each run produces a canonical JSON result:

```json
{
  "schema_version": "1.0.0",
  "timestamp": "2026-08-28T10:32:52+00:00",
  "design": { "name": "nmos_oscillator", "pdk": "ihp_sg13g2", "simulator": "ngspice" },
  "pss": {
    "converged": true,
    "frequency_hz": 10214500000.0,
    "transient_crosscheck": { "performed": true, "relative_error": 0.0 }
  },
  "jitter": {
    "rms_tie_fs": 45.0,
    "f0_hz": 10214500000.0,
    "fmin_hz": 10000.0,
    "fmax_hz": 1000000000.0,
    "convention": "one-sided L(f) -> double-sideband S_phi(f)"
  },
  "overall_status": "PASS"
}
```

### Cross-Check Mechanism

Each SPICE measurement includes an independent cross-check:
- Frequency from early zero-crossings (crossings 3-5) vs late zero-crossings (crossings 10-12)
- Relative error < 1e-5 confirms steady-state has been reached
- Prevents false positives from startup transients

---

## Adding New Designs

### Step 1: Create a SPICE Netlist

```spice
* my_oscillator.cir
.options method=gear reltol=1e-4 temp=27
.lib '/tmp/ihp_sg13g2/libs.tech/ngspice/models/cornerMOSlv.lib' mos_tt

* ... your circuit ...

* Analysis
.control
    tran 0.1p 50n
    meas tran t1 WHEN v(out_p)=v(out_n) CROSS=3
    meas tran t2 WHEN v(out_p)=v(out_n) CROSS=5
    let freq = 1/(t2-t1)
    print freq
    quit
.endc
.end
```

### Step 2: Test the Netlist

```bash
wsl bash -c "export PDK_ROOT='/tmp' && ngspice -b my_oscillator.cir"
```

### Step 3: Add to Regression Suite

Edit `siliconforge/solvers/regression.py`:

```python
CANONICAL_CIRCUITS["my_oscillator"] = {
    "name": "my_oscillator",
    "description": "My custom oscillator",
    "f0_nominal_hz": 5.0e9,
    "vdd": 1.2,
    "expected_f0_range_hz": (4.5e9, 5.5e9),
    "category": "oscillator",
    "netlist_path": "path/to/my_oscillator.cir",
}
```

### Step 4: Run

```bash
python -c "from siliconforge.solvers.regression import RegressionRunner; RegressionRunner(use_spice=True).run_suite(['my_oscillator'])"
```

---

## Reproducibility

### Fixed Seeds and Deterministic Behavior

- All random number generators use fixed seeds (seed=42)
- SPICE simulation parameters are explicitly documented
- No Monte Carlo sampling without recorded seed

### Environment Capture

```bash
# Capture full environment state
wsl bash -c "ngspice --version" > environment.txt
wsl bash -c "openvaf --version" >> environment.txt
python --version >> environment.txt
python -c "import numpy; print(f'numpy={numpy.__version__}')" >> environment.txt
python -c "import scipy; print(f'scipy={scipy.__version__}')" >> environment.txt
```

### Result Schema Versioning

All results include `"schema_version": "1.0.0"`. Future schema changes will be backward-compatible — new fields are additive, existing fields are never removed or redefined.

### Canonical Jitter Definition

All jitter results use a single definition:

```
sigma_t = sqrt( integral_{f_L}^{f_H} S_phi(f) df ) / (2*pi*f_0)
```

where S_phi(f) = 2 * 10^(L(f)/10) [one-sided to double-sideband conversion]

Every jitter result includes f0, fmin, fmax, integration method, and convention — preventing contradictory "jitter" numbers from the same design.

---

## Troubleshooting

### ngspice: "file too short" for OSDI

The `psp103_nqs.osdi` file is not pre-compiled in the IHP PDK. Compile it:

```bash
wsl bash -c "cd '/mnt/d/.../IHP-Open-PDK-0.3.0/ihp-sg13g2/libs.tech/verilog-a/psp103' && openvaf psp103_nqs.va"
wsl bash -c "cp '<source>/psp103_nqs.osdi' /tmp/ihp_sg13g2/libs.tech/ngspice/va/psp103_nqs/"
```

Verify: `ls -la /tmp/ihp_sg13g2/libs.tech/ngspice/va/psp103_nqs/psp103_nqs.osdi` should show ~997KB.

### ngspice: "Timestep too small"

Common with ring oscillators. Solutions:
- Use PWL supply ramp: `VDD vdd 0 PWL(0 0 1n 1.2)`
- Add small load capacitors: `Cload out1 0 5f`
- Reduce MOSFET kp values
- Use `.ic` to set initial conditions

### NumPy: "trapz not found"

This environment uses NumPy 2.x. Use `np.trapezoid` instead of `np.trapz`. The SiliconForge solver modules have been updated.

### Yosys: "Unsupported cell type $adff"

Convert async-reset DFFs before SMT2 generation:
```bash
yosys -p 'read_verilog design.v; proc; opt; async2sync; opt; write_smt2 design.smt2'
```

### Spaces in Paths

Always use the `/tmp/ihp_sg13g2` symlink. Direct paths with spaces will silently break ngspice and Yosys.

---

## Repository Structure

```
siliconforge/
├── siliconforge/                  # Main package
│   ├── solvers/                   # Numerical engines + new framework
│   │   ├── regression.py          # Regression suite runner
│   │   ├── schema.py              # Canonical result schema
│   │   ├── design_config.py       # Design configuration
│   │   ├── spice_runner.py        # WSL/ngspice interface
│   │   ├── jitter.py              # Canonical jitter calculation
│   │   ├── mutation.py            # Negative testing
│   │   └── netlists/              # Test circuit netlists
│   ├── automation/
│   │   └── rf_pipeline/           # 9-stage PPV pipeline
│   │       ├── run_v1_pipeline.py
│   │       ├── shooting_method.py
│   │       ├── ppv_direct_injection.py
│   │       ├── ppv_breakdown.py
│   │       ├── ppv_jitter.py
│   │       ├── ppv_adjoint.py
│   │       └── pvt_sweep.py
│   ├── asset_generator/           # Jinja2 templating → SystemVerilog
│   ├── backends/                  # Simulator abstraction
│   │   ├── base.py                # Simulator ABC
│   │   ├── ngspice_cli.py         # ngspice subprocess backend
│   │   └── reference_ode.py       # Pure Python reference
│   └── core/
│       └── pipeline.py            # Master orchestrator
├── tests/                         # pytest test suite
│   ├── test_jitter.py             # Jitter integration tests
│   ├── test_schema.py             # Result schema tests
│   ├── test_design_config.py      # Config abstraction tests
│   ├── test_pipeline.py           # Pipeline execution test
│   └── test_backends.py           # Backend contract tests
├── uvm_verification/              # Generated UVM environment
├── regression_results/            # Regression output (JSON)
└── run_regression.py              # Legacy regression runner
```

---

## Running Tests

```bash
# Full test suite
cd siliconforge
python -m pytest tests/ -v

# Specific test modules
python -m pytest tests/test_jitter.py -v
python -m pytest tests/test_schema.py -v
python -m pytest tests/test_design_config.py -v
```

---

## License

SiliconForge is an open-source research project. IHP SG13G2 PDK models are subject to the IHP open PDK license.
