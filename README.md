# SiliconForge: Mixed-Signal Verification Asset Generator

**SiliconForge** (formerly OscillatorLab) is an automated Electronic Design Automation (EDA) framework designed to bridge the structural divide between transistor-level analog characterization and discrete-event digital functional verification (UVM).

By ingesting numerical simulation data (Periodic Steady State, Perturbation Projection Vectors, and Monte Carlo variance) from SPICE solvers, SiliconForge deterministically synthesizes production-ready SystemVerilog constraints, ensuring that high-throughput digital regression suites perfectly mirror the continuous-time physics of the physical silicon.

---

## 🛑 The Industrial Bottleneck

In modern System-on-Chip (SoC) development, the integration of analog components (VCOs, PMUs, SerDes) with digital control logic creates a massive verification bottleneck. 

1. **Analog Simulation is Slow:** Transistor-level co-simulation (SPICE + Verilog) takes weeks to simulate microseconds of real-time operation.
2. **Behavioral Models are Manual:** The industry standard is to swap SPICE netlists for Real-Number Models (RNM) in SystemVerilog. However, translating the analog characterization limits (e.g., $V_{max}$, tuning ranges, phase noise profiles) into the digital testbench is a manual, highly error-prone process.
3. **Coverage is Guessed:** Verification engineers often guess the functional coverage bins based on datasheets, leading to digital testbenches that fall out of sync with actual physical silicon limits across PVT corners.

## 🛠️ The SiliconForge Architecture

SiliconForge completely automates the translation of analog characterization data into digital verification assets. It acts as middleware, utilizing **Jinja2 deterministic templating** to synthesize UVM 1.2 architectures.

### 1. Cycle-Accurate SVA Generation
Ingests Periodic Steady State (PSS) waveform boundaries to synthesize a SystemVerilog Assertion (`vco_sva_pkg.sv`) package. This `bind`s to the RNM DUT, structurally guaranteeing that the digital model never exceeds physical amplitude limits ($V_{max}$, $V_{min}$) during digital regression.

### 2. Physically Calibrated Jitter Sequences
Instead of generic Gaussian noise generators, SiliconForge parses the Perturbation Projection Vector (PPV). It synthesizes a `uvm_sequence` that injects cycle-accurate phase deviations ($\Delta t$) scaled exactly by the Root-Mean-Square of the Impulse Sensitivity Function ($\Gamma_{rms}$) characterized by the Floquet analysis.

### 3. Automated $3\sigma$ Statistical Coverage
SiliconForge replaces functional coverage guesswork with mathematical proof.
- Ingests $N$ Monte Carlo outputs (e.g., 1000 Xyce runs).
- Calculates the true statistical mean ($\mu$) and sample standard deviation ($\sigma$).
- Synthesizes a discrete, floating-point `covergroup` partitioned into exact $\pm 3\sigma$ standard deviation bins (`vco_coverage.svh`).

## 🚀 Execution Workflow

SiliconForge provides a master regression runner that autonomousy orchestrates the translation and verification cycle.

```bash
python run_regression.py
```

### Output Trace:
```text
================================================================================
[14:32:14] PHASE 1: Verification Asset Generation
================================================================================
Executing: python siliconforge\asset_generator\generate_assets.py
[SUCCESS] Generator executed perfectly.
Executing: python siliconforge\asset_generator\generate_coverage.py
[SUCCESS] Generator executed perfectly.

================================================================================
[14:32:15] PHASE 2: UVM Compilation
================================================================================
$ xvlog -sv -L uvm uvm_verification/*.sv uvm_verification/*.svh
[SUCCESS] Compilation completed with 0 Errors, 0 Warnings

================================================================================
[14:32:16] PHASE 3: Digital UVM Simulation
================================================================================
$ xsim tb_vco_top -R -testplusarg UVM_TESTNAME=vco_test -cov
UVM_INFO @ 0: uvm_test_top.env.agent.sequencer [VCO_SEQ] Starting physically calibrated jitter sequence (Gamma_RMS: 1.340000e-12)
[SUCCESS] UVM Simulation Finished cleanly.

================================================================================
[14:32:17] PHASE 4: Coverage Extraction
================================================================================
---------------------------------------------------------
               VERIFICATION CLOSURE REPORT                 
---------------------------------------------------------
DUT: vco_rnm_dut
Physical SVA Bounds Violations:   0
Statistical 3-Sigma Coverage:     100.0%
---------------------------------------------------------

[PASSED] Mathematical Variance Coverage Reached. Silicon Sign-Off Approved.
```

## 🏗️ Repository Structure
- `/siliconforge/analog_solvers`: The backend Python numerical engines for PSS/PPV extraction.
- `/siliconforge/asset_generator`: The Jinja2 templating engine mapping physics to SystemVerilog.
- `/uvm_verification`: The generated SystemVerilog UVM environment and discrete-time RNM Device Under Test.

## 🎯 Strategic Positioning
SiliconForge demonstrates end-to-end mastery of the Mixed-Signal Verification triad: automated stimulus, automated checking, and automated measurement. By avoiding the non-determinism of LLMs in favor of strict mathematical templating, it provides a rigorous, production-ready methodology perfectly aligned with enterprise MSDV workflows.