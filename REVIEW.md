# SiliconForge: Comprehensive Technical Review

**Review Date:** 2026-08-28  
**Reviewer:** Senior EDA Engineer  
**Scope:** Full codebase audit — architecture, mathematics, SPICE integration, verification methodology  
**Conclusion:** Research prototype with fundamental mathematical bugs, broken SPICE integration, and significant gaps between claims and implementation.

---

## 1. Executive Summary

SiliconForge is an ambitious attempt to build a mixed-signal verification framework bridging transistor-level analog characterization with digital verification. The project demonstrates strong architectural thinking (backend abstraction, canonical result schema, design configuration) but suffers from:

- **Critical mathematical errors** in phase noise, jitter, and PPV extraction
- **Broken SPICE integration** (wrong executable names, wrong CLI flags, binary parser errors)
- **Systematic dishonesty** — fake results reported as real, stubs disguised as working code, tautological verification
- **Architectural dead ends** — the backend ABC is never used by the pipeline, 9/16 regression circuits are non-functional

The framework produces physically meaningless numbers for phase noise, PPV/ISF, and jitter from the 9-stage pipeline. Only the new `spice_runner.py` module (used by the regression suite) produces trustworthy results for oscillation frequency.

**Bottom line:** The project is a collection of partially-implemented ideas, not a working verification framework. With focused work on correctness and honesty, it could become one.

---

## 2. Mathematical Correctness

### 2.1 Phase Noise (`pnoise_analysis.py`) — WRONG

The Leeson model implementation is fundamentally broken:

```python
# CURRENT (WRONG):
noise_density = k_t                          # Missing * T * F / P_signal
filter_factor = (f_osc_hz / (2.0 * f_offset_hz)) ** 2 if f_offset_hz < f_corner_hz else 1.0
white_noise = noise_density * filter_factor / f_offset_hz
```

The standard Leeson formula is:
```
L(fm) = 10*log10[ (2*k*T*F/P) * (1 + (f0/(2*Q*fm))^2) * (1 + fc/fm) ]
```

**Errors:**
1. Missing temperature (T=300K), noise figure (F), and signal power (P) from thermal term
2. Wrong filter factor — should be `(1 + (f0/(2*Q*fm))^2)`, not conditional on `f_corner_hz`
3. Flicker term has extra `fm^2` denominator that doesn't match Leeson

**Impact:** All phase noise values from this function are physically meaningless.

### 2.2 Jitter Integration (`ppv_jitter.py`) — WRONG

```python
# Line 40:
phi_rms = np.sqrt(2 * integral)   # Factor of 2 is double-counting
```

The code starts with one-sided L(f), converts to linear, then applies `sqrt(2 * integral)`. But the factor of 2 should either be applied to the PSD *before* integration (SSB→DSB conversion) or not at all for one-sided integration. This produces jitter values that are `sqrt(2) ≈ 1.414x` too high.

### 2.3 Harmonic Balance (`harmonic_balance.py`) — NON-FUNCTIONAL

The Jacobian construction is structurally wrong:

```python
J[row_offset + cos_idx, col_offset + cos_idx] = 0      # diagonal = 0
J[row_offset + sin_idx, col_offset + sin_idx] = 0      # diagonal = 0
```

A correct HB Jacobian needs the circuit admittance matrix (Y) on the diagonal plus spectral differentiation off-diagonals. This implementation only has the off-diagonal terms — representing a pure integrator chain, not any actual circuit. Newton iteration cannot converge.

Additionally, the `residual()` function differentiates the trial waveform but never evaluates actual circuit equations (G(v) - C*dv/dt = 0).

### 2.4 PPV/ISF Extraction (`ppv_eigenanalysis.py`) — WRONG

The monodromy matrix computation:

```python
Phi += np.outer(dx, np.ones(n_states)) / (dt * n_samples)
```

`np.outer(dx, np.ones(n_states))` produces a rank-1 matrix where every column is identical. This means the computed monodromy matrix has rank 1, giving at most one non-zero eigenvalue. For a 2-state system, this yields eigenvalues {1, 0} — physically wrong (should be {1, λ} where |λ| < 1 for a stable limit cycle).

The ISF construction is also ad-hoc:
```python
if len(ppv) == 2:
    isf = np.array([-ppv[1], ppv[0]])  # Perpendicular, not adjoint eigenvector
```

### 2.5 What IS Correct

- **`jitter.py` integration:** The `integrate_jitter_from_pn_curve()` and `integrate_jitter_single_point()` functions are mathematically correct (after removing the factor-of-2 issue in `ppv_jitter.py`)
- **Leeson model in `jitter.py`:** The `estimate_phase_noise_leeson()` function uses the correct formula
- **Frequency measurement:** Zero-crossing detection in `spice_runner.py` is correct
- **Cross-check methodology:** Early vs late crossing comparison is sound

---

## 3. SPICE Integration

### 3.1 Pipeline Uses Xyce, Not ngspice

The entire 9-stage pipeline (`shooting_method.py`, `ppv_direct_injection.py`, etc.) invokes **Xyce**, not ngspice:

```python
cmd_args = ["Xyce"]
```

This contradicts all README claims and installation instructions. Xyce is blocked on IHP models (see AGENT_ONBOARDING.md), meaning the pipeline cannot run on the validated PDK.

### 3.2 Backend ABC is Dead Code

The `Simulator` abstract base class in `backends/base.py` defines a clean contract:
- `load()`, `operating_point()`, `transient()`, `inject_state()`, `get_vector()`

Three backends implement this:
1. `ReferenceOdeBackend` — pure Python RLC (works for passive circuits only)
2. `NgspiceCliBackend` — subprocess-based ngspice (broken, see below)
3. `NgspiceSharedBackend` — libngspice ctypes bindings

**None of the pipeline stages use any of these backends.** They all directly invoke Xyce via subprocess. The entire `backends/` package is architecturally disconnected from the actual workflow.

### 3.3 Ngspice CLI Backend is Broken

```python
xyce_path: str = "NgspiceCli"   # Wrong — actual binary is "ngspice"
```

The `operating_point()` method uses `cmd.extend(["-dc", self._circuit_file])` but ngspice has no `-dc` flag. The correct approach is batch mode with `.control` blocks in the netlist.

The raw file parser expects ASCII format but ngspice `.raw` files are binary by default. The parser silently returns empty results.

### 3.4 SPICE Runner (New) — WORKS

The new `spice_runner.py` module correctly:
- Converts Windows paths to WSL
- Generates `.meas tran` cards for frequency measurement
- Detects differential vs single-ended outputs
- Parses ngspice stdout for frequency values
- Implements VDD/2 threshold detection

**Limitation:** Only measures frequency, not phase noise or jitter.

---

## 4. Verification Honesty Assessment

### 4.1 The "45 fs Jitter" Problem

For the entire project history, jitter values were hardcoded to `45e-15` (45 fs) regardless of circuit:

```python
tie_rms = 45e-15  # Same for 1 GHz ring osc and 10 GHz LC VCO
```

This has been partially addressed — the regression suite now uses the Leeson model (`compute_jitter_from_osc_params`) with hardcoded Q=8, P=5mW, F=6dB. But these are still not measured values; they're analytical estimates with no per-circuit calibration.

### 4.2 Tautological SVA

The original `generate_assets.py` set SVA bounds from the same characterization data used to build the DUT. This means assertions could **never** fail — the DUT was guaranteed to match its own bounds. Fixed to require `--silicon-spec` or fail loudly.

### 4.3 Mock Coverage

`generate_coverage.py` generates synthetic Monte Carlo data using `random.gauss(seed=42)` and presents it as measured results. Fixed to ingest real SPICE results with analytical fallback clearly labeled.

### 4.4 Mutation Testing — Stub

`mutation.py` is a design skeleton. The `_apply_and_test()` method was a stub returning fabricated 100% detection rate. Fixed to return `NOT_IMPLEMENTED` status honestly.

### 4.5 Regression Suite — 9/16 Non-Functional

| Circuit | Status |
|---------|--------|
| nmos_oscillator | SPICE-validated |
| hbt_oscillator | SPICE-validated |
| lc_vco | SPICE-validated |
| ring_oscillator | SPICE-validated |
| differential_vco | SPICE-validated |
| broken_circuit | EXPECTED_FAIL (negative test) |
| pll_behavioral | Analytical estimate only |
| cml_divider | NOT_IMPLEMENTED |
| charge_pump | NOT_IMPLEMENTED |
| opamp | NOT_IMPLEMENTED |
| comparator | NOT_IMPLEMENTED |
| sar_adc | NOT_IMPLEMENTED |
| dac | NOT_IMPLEMENTED |
| pll_full | NOT_IMPLEMENTED |
| adpll | NOT_IMPLEMENTED |
| mixed_signal blocks | NOT_IMPLEMENTED |

---

## 5. Code Quality

### 5.1 Bare `except:` Clauses

At least 10 locations in `automation/end_to_end.py` and `staged_design.py`:
```python
except Exception:
    pass
```

These swallow all errors — simulation failures, file I/O errors, numerical exceptions — producing incomplete results silently.

### 5.2 Hardcoded Development Paths

```python
# ppv_adjoint.py:460
plot_path = os.path.join(os.environ.get("USERPROFILE", "C:\\"), ".gemini", "antigravity-ide",
                         "brain", "90300897-07a5-4b42-a22c-168f7155fd30", "ppv_adjoint_plot.png")
```

This is a path to an LLM tool's internal cache. Will fail on any other machine.

### 5.3 Duplicated Code

`_wsl_path()` function is duplicated in 4 files with slight variations:
- `spice_runner.py`
- `shooting_method.py`
- `ppv_direct_injection.py`
- `config/paths.py`

### 5.4 Unused Imports

| File | Unused Import |
|------|--------------|
| `harmonic_balance.py` | `integrate_implicit_bdf`, `integrate_stiff_trbdf2` |
| `ppv_adjoint.py` | `expm` from scipy.linalg |
| `spice_runner.py` | `shutil`, `tempfile` |
| `pnoise_analysis.py` | `Callable` |

### 5.5 Debug Prints in Production

```python
# ppv_direct_injection.py:227
print("DEBUG: BASELINE NETLIST:")
print(base_netlist)
```

---

## 6. Architecture Assessment

### 6.1 What's Good

- **Canonical result schema (`schema.py`):** Clean versioned JSON with cross-check fields
- **Design configuration (`design_config.py`):** Proper abstraction, no hardcoded assumptions
- **Simulator ABC:** Clean interface, well-defined contract
- **Regression runner:** Good separation of concerns, honest status reporting (after fixes)
- **Test infrastructure:** pytest fixtures, conftest, multiple test modules

### 6.2 What's Broken

- **Pipeline-to-backend disconnect:** Pipeline bypasses the ABC entirely
- **Xyce vs ngspice confusion:** Claims ngspice, uses Xyce
- **Dual solver stacks:** `solvers/` and `automation/rf_pipeline/` provide overlapping functionality
- **Dead code:** ~40% of files are unused stubs or placeholders

### 6.3 What's Missing

- **Phase noise from SPICE:** No `.noise` analysis integration
- **PPV from SPICE:** No transient perturbation injection
- **Jitter from SPICE:** No phase noise → jitter computation
- **Formal verification:** Yosys/Z3 flow exists in ADPLL_10GHz/ but not in framework
- **UVM verification:** No working UVM testbench (Vivado-only, not reproducible)

---

## 7. Reproducibility

### 7.1 Reproducible

- Frequency measurement via zero-crossing detection (deterministic)
- Cross-check methodology (early vs late crossings)
- pytest test suite (26 tests, all passing)
- Fixed RNG seeds where applicable

### 7.2 Not Reproducible

- 9-stage pipeline (uses Xyce, which is blocked on IHP)
- UVM verification (requires Vivado, Windows-only)
- Phase noise values (wrong formula)
- PPV/ISF values (wrong math)
- Jitter values (hardcoded estimates)

### 7.3 Environment Lock

```bash
# No requirements.txt with pinned versions
# No Dockerfile or Nix flake
# No CI/CD pipeline
# WSL dependency not documented in setup.py
```

---

## 8. Recommended Actions

### Priority 1: Fix Mathematics (Critical)

1. **`ppv_jitter.py:40`** — Remove erroneous factor of 2
2. **`pnoise_analysis.py:42-58`** — Rewrite Leeson model correctly
3. **`harmonic_balance.py`** — Rebuild Jacobian with circuit admittance
4. **`ppv_eigenanalysis.py:296-299`** — Correct monodromy matrix estimation

### Priority 2: Fix SPICE Integration (Major)

5. **`ngspice_cli.py:109`** — Change default to `"ngspice"`
6. **`ngspice_cli.py:150`** — Remove `-dc` flag, use batch mode
7. **Pipeline** — Switch from Xyce to ngspice or document Xyce requirement
8. **Backend ABC** — Either connect pipeline to it or delete it

### Priority 3: Fix Honesty (Major)

9. **README** — Update claims to match actual capabilities
10. **Regression suite** — Remove or clearly mark non-functional circuits
11. **Mutation testing** — Implement or remove from README claims
12. **Jitter values** — Clearly label all estimates vs measurements

### Priority 4: Code Quality (Minor)

13. Replace all bare `except:` with specific exception types
14. Remove hardcoded development paths
15. Consolidate `_wsl_path()` into one location
16. Add `requirements.txt` with pinned versions

---

## 9. Scoring

| Category | Score | Notes |
|----------|-------|-------|
| Mathematical correctness | 2/10 | Core equations are wrong |
| SPICE integration | 3/10 | New runner works, pipeline broken |
| Code quality | 4/10 | Good structure, poor execution |
| Architecture | 6/10 | Clean ABC, but disconnected |
| Verification honesty | 3/10 | Systematic fake results |
| Reproducibility | 4/10 | Partial, environment not locked |
| Documentation | 5/10 | README overclaims, onboarding good |
| Test coverage | 5/10 | 26 tests, but don't cover pipeline |
| **Overall** | **3.5/10** | Research prototype, not production |

---

## 10. Conclusion

SiliconForge has the **architecture** of a real verification framework but the **implementation** of a research prototype. The core mathematical operations (phase noise, PPV extraction, jitter integration) are wrong. The SPICE integration is broken. The verification results are largely fabricated.

**The one thing that works:** The new `spice_runner.py` module correctly measures oscillation frequency from ngspice transient simulations. This is a solid foundation to build on.

**What it would take to become real:**
1. Fix the 4 critical mathematical bugs (2-3 days of work)
2. Switch pipeline from Xyce to ngspice (1 day)
3. Add SPICE `.noise` analysis for phase noise (2-3 days)
4. Connect pipeline to backend ABC (1 day)
5. Update README to match reality (half day)

**Estimated effort to become a credible framework:** 2-3 weeks of focused engineering.

---

*Review compiled from direct code analysis, test execution, and SPICE simulation. All findings traceable to specific file paths and line numbers.*
