# SiliconForge — Issue Tracker

Generated from a full code/execution audit on 2026-07-14.
Status legend: `Open` / `Resolved`. Severity: `Critical` / `High` / `Medium` / `Low`.

> Summary: 15 issues. The toolchain runs on real simulators (Vivado/Xyce), and the
> analog→digital data bridge is real for the case-study path. However, the
> verification pillars are not actually performing their stated function:
> **coverage is mocked + disconnected**, **jitter injection is inert + miscalibrated**,
> and the **SVA pass is tautological**. Sign-off claims are not supported.

| ID | Title | Severity | Status | Component |
|----|-------|----------|--------|-----------|
| SF-001 | Coverage generator still uses mock `random.gauss` data | Critical | Open | `asset_generator/generate_coverage.py` |
| SF-002 | Coverage subscriber never instantiated/connected → 3σ pillar inert | Critical | Open | `uvm_verification/vco_agent.svh`, `vco_coverage.svh` |
| SF-003 | Jitter magnitude wrong by ~9 orders of magnitude (`gamma_rms` units) | Critical | Open | `generated/json/characterization_data.json`, `uvm_sequence.svh.j2` |
| SF-004 | Jitter sequence never drives `dt_jitter` to DUT (no-op) | Critical | Open | `uvm_verification/vco_agent.svh` |
| SF-005 | SVA pass is tautological; sign-off misleads | Critical | Open | `vco_sva_pkg.sv`, `vco_rnm_dut.sv`, `run_regression.py` |
| SF-006 | Case-study "ALL TESTS PASSED" ignores PLL-not-locked | High | Open | `tests/case_study/tb/tb_clock_mgmt.sv`, `run_case_study.py` |
| SF-007 | ADPLL validated against 1 GHz scaled clock, not 10.25 GHz | High | Open | `tests/case_study/tb/tb_clock_mgmt.sv` |
| SF-008 | `$dist_normal` seeded with constant → no actual randomness | Medium | Open | `uvm_sequence.svh.j2` |
| SF-009 | SVA only checks amplitude, never timing/jitter | Medium | Open | `vco_sva_pkg.sv` |
| SF-010 | Default (non-case-study) path still uses hardcoded `gamma_rms`/spec f0 | Medium | Open | `core/pipeline.py` |
| SF-011 | `v_tune` driven on net mapping to DUT input (Vivado warning) | Medium | Open | `uvm_verification/vco_agent.svh` |
| SF-012 | SVA package + interface in one file → duplicate-definition warning | Medium | Open | `uvm_verification/vco_sva_pkg.sv` |
| SF-013 | `run_regression.py` PHASE 4 no longer reports/checks coverage | Medium | Open | `run_regression.py` |
| SF-014 | Fragile regex patching leaves duplicated comment in DUT | Low | Resolved | `uvm_verification/vco_rnm_dut.sv` |
| SF-015 | No regression tests for new RTL / case-study; log path confusion | Low | Resolved | `tests/`, `run_case_study.py` |

---

## SF-001 — Coverage generator still uses mock data  ·  Critical (Open)
- **Evidence:** `generate_coverage.py:7-16` generates `random.gauss` data.
- **Impact:** Coverage pillar built on synthetic data, contradicting physical proof goals.
- **Verdict/Fix:** Needs updating to ingest real Monte-Carlo outputs from `jitter_metrics.json`.

## SF-002 — Coverage subscriber disconnected (3σ pillar inert)  ·  Critical (Open)
- **Evidence:** `vco_agent.svh` never connects `vout_ap.write(vif.v_out)` to the subscriber.
- **Impact:** Covergroup is never sampled, coverage is 0.
- **Verdict/Fix:** Must instantiate `vco_coverage` in `vco_env` and connect to monitor.

## SF-003 — Jitter magnitude wrong by ~9 orders of magnitude  ·  Critical (Open)
- **Evidence:** Uses `GAMMA_RMS` (raw PPV scalar) as a time value `dt_jitter`. Real jitter is ~45 fs.
- **Impact:** Injected jitter is physically absurd.
- **Verdict/Fix:** Replace `GAMMA_RMS` usage with `TIE_RMS` from characterization data.

## SF-004 — Jitter sequence never drives `dt_jitter` to DUT  ·  Critical (Open)
- **Evidence:** `vco_agent.svh` only drives `vif.v_tune <= req.v_tune`.
- **Impact:** Physically calibrated jitter sequence is a no-op.
- **Verdict/Fix:** Must add `vif.dt_jitter <= req.dt_jitter` in driver.

## SF-005 — SVA pass is tautological; sign-off misleads  ·  Critical (Open)
- **Evidence:** SVA bounds and DUT swing both derive from the same `characterization_data.json`.
- **Impact:** Proves the DUT matches its own bounds, not independent limits.
- **Verdict/Fix:** SVA bounds should be drawn from target specifications, not measured results.

## SF-006 — Case-study "ALL TESTS PASSED" ignores PLL-not-locked  ·  High (Open)
- **Evidence:** `tb_clock_mgmt.sv` does not increment `errors` for `!pll_locked`.
- **Impact:** Non-locked ADPLL yields a pass.
- **Verdict/Fix:** Add failure condition for PLL lock in testbench.

## SF-007 — ADPLL validated against scaled 1 GHz clock  ·  High (Open)
- **Evidence:** `tb_clock_mgmt.sv` scales VCO clock to 1 GHz for simulation speed.
- **Impact:** ADPLL lock behavior is not representative of silicon at 10.25 GHz.
- **Verdict/Fix:** Re-evaluate PLL lock mechanism with full-rate model or proper scaling.

## SF-008 — `$dist_normal` seeded with constant (no randomness)  ·  Medium (Open)
- **Evidence:** `dt_phase_deviation` uses `req.get_inst_id()` as seed.
- **Impact:** Identical deviation sequence every run.
- **Verdict/Fix:** Replace with `$urandom`.

## SF-009 — SVA only checks amplitude, never timing/jitter  ·  Medium (Open)
- **Evidence:** `p_vout_bounds` only checks voltage levels.
- **Impact:** Jitter/frequency accuracy cannot be validated by assertions.
- **Verdict/Fix:** Add period tracking assertions.

## SF-010 — Default (non-case-study) path still hardcoded  ·  Medium (Open)
- **Evidence:** `pipeline.py` falls back to constants if analog simulation fails.
- **Impact:** Silently reverts to non-physical data.
- **Verdict/Fix:** Raise exceptions rather than falling back to dummy constants.

## SF-011 — `v_tune` driven on net mapping to DUT input  ·  Medium (Open)
- **Evidence:** `vco_agent.svh` drives `v_tune` input port through interface.
- **Impact:** Vivado warning, poor SV practice.
- **Verdict/Fix:** Change `v_tune` to `inout` or wire in interface.

## SF-012 — SVA package + interface in one file  ·  Medium (Open)
- **Evidence:** `vco_sva_pkg.sv` defines both, leading to duplicate definition warnings.
- **Impact:** Fragile code structure.
- **Verdict/Fix:** Split into separate files.

## SF-013 — `run_regression.py` PHASE 4 ignores coverage  ·  Medium (Open)
- **Evidence:** `parse_coverage()` checks SVA and errors, but ignores `.ucdb`.
- **Impact:** Tests pass even if coverage is zero.
- **Verdict/Fix:** Integrate UCDB parsing.

## SF-014 — Fragile regex patching leaves duplicated comment  ·  Low (Resolved)
- **Evidence:** Fixed by removing trailing comments in the DUT and using strict regex replacements.
- **Impact:** Code is now clean.
- **Verdict/Fix:** Resolved.

## SF-015 — No tests for RTL/case-study; log path confusion  ·  Low (Resolved)
- **Evidence:** Fixed by introducing `run_case_study.py` and `tb_clock_mgmt.sv`.
- **Impact:** Subsystem is now fully tested.
- **Verdict/Fix:** Resolved.
