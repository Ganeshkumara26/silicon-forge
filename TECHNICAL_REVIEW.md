# SiliconForge: Independent Technical Review

**Review Date:** 2026-08-28  
**Reviewer:** Independent EDA Technical Audit  
**Scope:** Full codebase review of `ppv guided clock generation adpll/siliconforge/`  
**Classification:** Pre-tapeout research codebase assessment

---

## 1. Executive Summary

SiliconForge is an ambitious research-grade EDA framework that attempts to bridge transistor-level analog characterization (PSS, PPV, phase noise) with digital functional verification (UVM, SVA, formal). The project demonstrates genuine understanding of mixed-signal verification methodology and has working infrastructure for oscillator frequency measurement via SPICE transient simulation.

**However, the codebase contains critical mathematical errors in core numerical algorithms, fundamental architectural disconnects between components, and significant gaps between documented claims and actual implementation.** Of approximately 28,000 lines of code across 380+ files, roughly 40% is dead code, placeholder implementations, or non-functional stubs.

**Bottom line:** The framework's SPICE-based oscillator frequency measurement works correctly and has been validated on 5 distinct topologies. Everything else — phase noise computation, jitter extraction, PPV/ISF extraction, harmonic balance, formal verification, UVM generation — contains critical errors or is non-functional.

---

## 2. Project Claims vs. Reality

| Claim | Status | Evidence |
|-------|--------|----------|
| "Mixed-signal verification framework" | **Partial** | Frequency measurement works; PPV/PN/jitter/math are broken |
| "9-stage pipeline" | **Broken** | Stages 3, 7 reference non-existent scripts; stages 1-2 use Xyce (blocked on IHP) |
| "5 oscillator topologies SPICE-validated" | **True** | NMOS VCO, HBT VCO, ideal LC VCO, ring osc, differential VCO all measured |
| "Canonical jitter definition" | **True** | `solvers/jitter.py` has correct formula; pipeline `ppv_jitter.py` does not |
| "Physically calibrated jitter sequences" | **False** | Jitter always from Leeson model estimate; never from SPICE .noise |
| "Automated 3σ statistical coverage" | **Broken** | Coverage bins generated from analytical estimates with seed=42, not real MC |
| "Cycle-accurate SVA generation" | **Tautological** | SVA bounds match DUT characterization exactly unless `--silicon-spec` provided |
| "Formally verified with Z3" | **True** | Phase_gating formal proof works (separate from framework) |
| "Mutation testing with 100% detection" | **False** | `_apply_and_test()` is a stub; detection rate is actually 0% |
| "Reusable for other designs" | **Partial** | `design_config.py` works; only oscillators tested so far |

---

## 3. Critical Mathematical Errors

### 3.1 Jitter Integration: Double-Counting Factor of 2

**File:** `automation/rf_pipeline/ppv_jitter.py:40`

```python
phi_rms = np.sqrt(2 * integral)
```

**Error:** The factor of 2 is applied *after* integration, inside the sqrt. The correct approach:
- Single-sideband L(f) → double-sideband S_phi(f) = 2 × 10^(L(f)/10) — multiply *before* integration
- Or integrate L(f) directly and multiply final result by sqrt(2)

**Impact:** All jitter values from the pipeline are sqrt(2) ≈ 1.414× too high. A true 45 fs jitter would report as ~63.6 fs.

**Note:** The newer `solvers/jitter.py` does NOT have this bug — it correctly applies the factor of 2 to S_phi before integration. This means the pipeline and the solver framework disagree.

### 3.2 Phase Noise: Leeson Model Incorrect

**File:** `solvers/pnoise_analysis.py:42-58`

The Leeson formula is implemented as:
```python
noise_density = k_t                          # Missing * T * F / P_signal
filter_factor = (f_osc_hz / (2.0 * f_offset_hz)) ** 2 if f_offset_hz < f_corner_hz else 1.0
white_noise = noise_density * filter_factor / f_offset_hz
```

**Correct Leeson model:**
```
L(fm) = 10·log₁₀[ (2kTF/P) · (1 + (f₀/(2Q·fm))²) · (1 + fc/fm) ]
```

**Errors:**
1. Thermal term omits T (temperature), F (noise figure), P (signal power)
2. Filter factor uses wrong condition (`f_offset < f_corner` instead of always applying the resonance term)
3. Flicker term has extra `f_offset²` in denominator

**Impact:** All phase noise values from this function are wrong by unknown (frequency-dependent) amounts.

### 3.3 Harmonic Balance: Jacobian is Structurally Wrong

**File:** `solvers/harmonic_balance.py:295-330`

The HB Jacobian has all zero diagonal entries and only spectral differentiation off-diagonals:
```python
J[row_offset + cos_idx, col_offset + cos_idx] = 0      # diagonal = 0
J[row_offset + sin_idx, col_offset + sin_idx] = 0      # diagonal = 0
J[row_offset + cos_idx, col_offset + sin_idx] = -k * omega   # off-diagonal only
```

**Correct structure:** The Jacobian should be `Y + jωC` where Y is the circuit admittance matrix and C is the capacitance matrix. The current implementation represents a pure integrator chain — Newton iteration cannot converge.

**Impact:** The harmonic balance solver is non-functional for any circuit.

### 3.4 Monodromy Matrix: Rank-1 Approximation

**File:** `solvers/ppv_eigenanalysis.py:296-299`

```python
Phi += np.outer(dx, np.ones(n_states)) / (dt * n_samples)
```

`np.outer(dx, np.ones(n_states))` produces a rank-1 matrix (every column identical). The resulting monodromy matrix has at most one non-zero eigenvalue. A limit cycle should have one eigenvalue = 1 (phase perturbation) and the rest < 1 (amplitude perturbations decay).

**Impact:** PPV/ISF extracted via eigenanalysis is mathematically meaningless.

### 3.5 ISF Construction: Geometric Perpendicular ≠ Adjoint Eigenvector

**File:** `solvers/ppv_eigenanalysis.py:107-119`

```python
if len(ppv) == 2:
    isf = np.array([-ppv[1], ppv[0]])  # perpendicular, not adjoint
```

The ISF should come from the left eigenvector of the monodromy matrix (adjoint method), not a geometric perpendicular. For N>2 dimensions, the Gram-Schmidt construction is arbitrary.

**Impact:** ISF values do not correspond to physical impulse sensitivity.

---

## 4. Architecture Assessment

### 4.1 Backend Abstraction: Clean Design, Zero Adoption

The `Simulator` ABC in `backends/base.py` defines a clean contract:
```
load(), reset(), operating_point(), transient(), inject_state(), get_vector()
```

Three backends implement it:
- `ReferenceOdeBackend` — pure Python RLC (works for passive only)
- `NgspiceCliBackend` — subprocess ngspice (broken CLI flags)
- `NgspiceSharedBackend` — libngspice ctypes (most complete, Linux only)

**Problem:** None of the pipeline stages use any backend. They all directly invoke Xyce via subprocess. The entire `backends/` package is dead code.

**Recommendation:** Either connect pipeline to backend ABC (preferred) or delete the abstraction.

### 4.2 Pipeline vs Framework: Two Separate Codebases

| Component | SPICE Engine | Status |
|-----------|-------------|--------|
| `automation/rf_pipeline/` | Xyce (blocked on IHP) | Non-functional |
| `solvers/spice_runner.py` | ngspice via WSL | Working |
| `solvers/regression.py` | Calls spice_runner | Working for frequency |

The pipeline (`run_v1_pipeline.py`) and the framework (`solvers/regression.py`) are completely independent. The pipeline cannot run on this environment (Xyce blocked), so all PPV/PN/jitter extraction is unavailable.

### 4.3 Duplicate Implementations

| Function | Locations | Divergence |
|----------|-----------|------------|
| `_wsl_path()` | `spice_runner.py`, `shooting_method.py`, `ppv_direct_injection.py`, `config/paths.py` | `p[2:]` vs `p[3:]` |
| Phase noise calculation | `pnoise_analysis.py`, `ppv_breakdown.py`, `jitter.py` | Different formulas, different results |
| Jitter integration | `ppv_jitter.py`, `jitter.py` | Factor-of-2 disagreement |

---

## 5. What Actually Works

### 5.1 Oscillator Frequency Measurement ✅

**Files:** `solvers/spice_runner.py`, `solvers/regression.py`

The ngspice-based frequency measurement via zero-crossing detection is correct and validated:

| Circuit | Topology | Measured | Expected | Error |
|---------|----------|----------|----------|-------|
| NMOS VCO | LC, CMOS | 10.2145 GHz | ~10.21 GHz | < 0.1% |
| HBT VCO | LC, BiCMOS | 10.4033 GHz | ~10.4 GHz | < 0.1% |
| Ring Oscillator | 5-stage inverter | 10.8586 GHz | 5-15 GHz | N/A |
| Differential VCO | LC, diff NMOS | 6.7049 GHz | 5-8 GHz | N/A |

The cross-check mechanism (early vs late zero-crossings) correctly validates steady-state.

### 5.2 Design Configuration Abstraction ✅

**File:** `solvers/design_config.py`

Clean YAML/JSON design description with auto-reference resolution. No ADPLL hardcodes in the abstraction layer (though presets exist for ADPLL).

### 5.3 Result Schema ✅

**File:** `solvers/schema.py`

Well-structured machine-readable output with schema versioning. Correctly distinguishes measured vs estimated fields.

### 5.4 Formal Verification (Separate) ✅

Yosys + Z3 formal proof of `phase_gating` module works correctly. This is separate from the framework.

---

## 6. What Is Broken or Non-Functional

### 6.1 Pipeline Stages (9-stage)

| Stage | Script | Status | Blocker |
|-------|--------|--------|---------|
| 1. PSS Shooting | `shooting_method.py` | ❌ Uses Xyce (blocked) | IHP models |
| 2. PPV Direct Injection | `ppv_direct_injection.py` | ❌ Uses Xyce (blocked) | IHP models |
| 3. PPV Suite | `ppv_suite.py` | ❌ File missing | No implementation |
| 4. Phase Noise Breakdown | `ppv_breakdown.py` | ⚠️ Wrong Leeson formula | Math error |
| 5. Multi-Part PN | embedded in breakdown | ⚠️ Wrong formula | Math error |
| 6. Jitter Integration | `ppv_jitter.py` | ⚠️ sqrt(2) error | Math error |
| 7. Verilog-A Generation | `gen_verilog_a.py` | ❌ File missing | No implementation |
| 8. Adjoint PPV | `ppv_adjoint.py` | ❌ Uses Xyce (blocked) | IHP models |
| 9. PVT Sweep | `pvt_sweep.py` | ❌ Uses Xyce (blocked) | IHP models |

### 6.2 Regression Suite (15 circuits)

| Category | Count | Status |
|----------|-------|--------|
| SPICE-measured oscillators | 5 | ✅ Working |
| Analytical estimate (no SPICE) | 4 | ⚠️ Estimates only |
| NOT_IMPLEMENTED | 5 | ❌ No test method |
| EXPECTED_FAIL | 1 | ✅ Correctly fails |

### 6.3 Numerical Solvers

| Solver | File | Status | Blocker |
|--------|------|--------|---------|
| Shooting-Newton PSS | `pss_shooting.py` | ⚠️ Code exists, untested without Xyce | IHP models |
| Harmonic Balance | `harmonic_balance.py` | ❌ Jacobian is structurally wrong | Math error |
| PPV Eigenanalysis | `ppv_eigenanalysis.py` | ❌ Monodromy matrix is rank-1 | Math error |
| Phase Noise Analysis | `pnoise_analysis.py` | ❌ Leeson formula wrong | Math error |
| Reference ODE | `reference_ode.py` | ✅ Works for passive RLC only | Limited scope |

---

## 7. Code Quality Issues

### 7.1 Bare Except Clauses (12+ locations)

**Files:** `end_to_end.py`, `staged_design.py`, `check_v1.py`, `plot_v1.py`, `generate_v1_figures.py`

```python
except:
    pass
```

These catch `KeyboardInterrupt`, `SystemExit`, and all runtime errors. Simulation failures are silently swallowed.

### 7.2 Hardcoded Development Paths

**File:** `ppv_adjoint.py:460`
```python
plot_path = os.path.join(os.environ.get("USERPROFILE", "C:\\"), ".gemini", "antigravity-ide",
                         "brain", "90300897-07a5-4b42-a22c-168f7155fd30", "ppv_adjoint_plot.png")
```

This references an LLM tool's internal cache. Will fail on any other machine.

### 7.3 Wrong Executable Name

**File:** `backends/ngspice_cli.py:109`
```python
xyce_path: str = "NgspiceCli"  # Should be "ngspice"
```

### 7.4 Wrong CLI Flags

**File:** `backends/ngspice_cli.py:150-154`
```python
cmd.extend(["-dc", self._circuit_file])  # ngspice has no -dc flag
```

### 7.5 Raw File Format Mismatch

**File:** `backends/ngspice_cli.py:227, 295`
```python
dat_file = os.path.splitext(self._circuit_file)[0] + ".raw"   # line 227
dat_file = os.path.splitext(self._circuit_file or "")[0] + ".dat"  # line 295
```

Expects both `.raw` and `.dat` but parser can only handle one format.

---

## 8. Verification Gaps

### 8.1 No Independent Cross-Check of Phase Noise

The framework claims to compute phase noise but never validates against:
- SPICE `.noise` analysis
- Published measurements from IHP
- Analytical hand calculations

### 8.2 No PPV/ISF Validation

The PPV/ISF extraction (the core novel contribution) has never been validated against:
- Direct injection vs adjoint method agreement
- SPICE transient perturbation
- Published ISF shapes from literature

### 8.3 Jitter Discrepancy Unresolved

The 45 fs vs 389 fs discrepancy identified in the original report is still not fully reconciled. The new `solvers/jitter.py` gives different results from `ppv_jitter.py` due to the sqrt(2) factor difference.

### 8.4 No Silicon Validation

All results are from simulation only. No comparison against silicon measurements.

---

## 9. Strengths

Despite the issues, several aspects deserve recognition:

1. **Genuine methodology understanding**: The PSS→PPV→PN→Jitter flow is architecturally correct
2. **Working SPICE integration**: The ngspice/WSL interface is functional and tested
3. **Clean result schema**: Well-designed JSON output with versioning
4. **Design abstraction**: `design_config.py` is PDK-agnostic and extensible
5. **Cross-check mechanism**: Early/late crossing comparison is sound
6. **Honest test labeling**: After recent fixes, estimates are clearly marked
7. **Formal verification**: Yosys+Z3 flow for digital blocks works correctly

---

## 10. Recommendations

### 10.1 Immediate (Correctness)

1. **Fix `ppv_jitter.py:40`** — remove erroneous factor of 2
2. **Fix `pnoise_analysis.py:42-58`** — rewrite Leeson model correctly
3. **Fix `harmonic_balance.py:295-330`** — rebuild Jacobian with circuit admittance
4. **Fix `ppv_eigenanalysis.py:296-299`** — correct monodromy matrix estimation
5. **Fix `ngspice_cli.py:109`** — change default to `"ngspice"`
6. **Remove bare `except:` clauses** — replace with specific exception types

### 10.2 Short-term (Architecture)

7. **Decide: Xyce or ngspice?** — The codebase claims ngspice but pipeline uses Xyce
8. **Connect pipeline to backend ABC** — Or delete the abstraction
9. **Consolidate duplicate functions** — `_wsl_path()`, jitter integration
10. **Mark all placeholder circuits** — Clear NOT_IMPLEMENTED status in regression output
11. **Add missing scripts** — `ppv_suite.py`, `gen_verilog_a.py` or remove stages

### 10.3 Medium-term (Validation)

12. **Validate phase noise** — Run ngspice `.noise` analysis on test circuits
13. **Validate PPV** — Compare direct injection vs adjoint on same circuit
14. **Reconcile jitter** — Single authoritative definition, validated against SPICE
15. **Add silicon comparison** — At least one measured vs simulated comparison

### 10.4 Documentation

16. **Update README** — Reflect actual capabilities, not aspirational ones
17. **Separate "works" from "broken"** — Clear documentation of what's functional
18. **Add accuracy claims** — With evidence, for each computed metric

---

## 11. Scoring

| Criterion | Score | Notes |
|-----------|-------|-------|
| **Architecture** | 6/10 | Clean design, poor adoption |
| **Mathematical correctness** | 3/10 | 5 critical math errors |
| **Code quality** | 4/10 | Dead code, bare excepts, duplicates |
| **Testing** | 5/10 | 26 tests + regression, but gaps |
| **Documentation** | 5/10 | Claims exceed implementation |
| **Reproducibility** | 6/10 | Fixed seeds, but env-specific paths |
| **Novelty** | 7/10 | PPV-guided verification is a real contribution |
| **Silicon readiness** | 2/10 | No PN/PPV/jitter validation |

**Overall: 4.75/10** — A research prototype with genuine methodological contributions but significant mathematical and architectural gaps that must be addressed before production use.

---

## 12. Conclusion

SiliconForge demonstrates real understanding of mixed-signal verification methodology. The core innovation — using PPV/ISF characterization to guide digital verification — is sound. The working oscillator frequency measurement infrastructure is solid.

However, the codebase cannot be trusted for production use until:
1. The 5 critical mathematical errors are fixed
2. The pipeline is made to run on the available toolchain (ngspice)
3. Phase noise and PPV results are validated against independent references
4. All placeholder/stub code is either implemented or clearly marked

The gap between the README's claims and the actual implementation is the most significant issue. A senior EDA engineer should treat this as a research prototype requiring substantial additional development before it can be used for sign-off verification.

---

*Review compiled from direct code analysis, test execution, and SPICE simulation results. All findings traceable to specific file paths and line numbers.*
