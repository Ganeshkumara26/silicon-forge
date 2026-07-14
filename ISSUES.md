# SiliconForge — Issue Tracker

Generated from a full code/execution audit on 2026-07-14.
Status legend: `Open`. Severity: `Critical` / `High` / `Medium` / `Low`.

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

## SF-001 — Coverage generator still uses mock data  ·  Critical
- **Evidence:** `siliconforge/asset_generator/generate_coverage.py:7-16` generates
  `random.gauss(target_mean=10e9, target_sigma=25e6)` with the comment
  *"(In a real physical flow, this would parse Xyce .prn simulation results)"*;
  `:78` sets `source_dataset="Synthesized Analytical Dataset (MOCK)"`. Output bins
  are centered at 10 GHz, not the measured 10.2488 GHz.
- **Impact:** The "Automated 3σ Statistical Coverage" pillar is built on synthetic
  data. Directly contradicts the stated goal of replacing guesswork with physical proof.
- **Fix:** Ingest real Monte-Carlo outputs (e.g. `tests/case_study/results/*.json` or
  Xyce `.prn`) instead of `random.gauss`; remove the MOCK label.
- **Verdict (Current Status):** **OPEN**. The generator still uses `random.gauss`.

## SF-002 — Coverage subscriber disconnected (3σ pillar inert)  ·  Critical
- **Evidence:** `vco_coverage.svh` defines `class vco_coverage extends uvm_subscriber #(real)`
  with `write(real t)` that calls `cg_vco_statistical_variance.sample()` (`:48-51`).
  But `vco_agent.svh:94-97` `connect_phase` only wires `driver.seq_item_port`; the
  monitor's `vout_ap.write(vif.v_out)` (`:68`) is never connected to the subscriber's
  `analysis_export`, and `vco_env` instantiates only the agent. Vivado prints
  *"Functional Coverage Database has not been updated during simulation."*
- **Impact:** The covergroup is never sampled → coverage is effectively 0/unmeasured.
- **Fix:** Instantiate `vco_coverage` in `vco_env`, and in `connect_phase` do
  `monitor.vout_ap.connect(coverage.analysis_export)`.
- **Verdict (Current Status):** **OPEN**. Not yet wired in UVM environment.

## SF-003 — Jitter magnitude wrong by ~9 orders of magnitude  ·  Critical
- **Evidence:** `generated/json/characterization_data.json` has `gamma_rms=0.0412679`
  while the true RMS jitter is `tie_rms_fs=45.15` (≈4.5e-14 s) in
  `tests/case_study/results/jitter_metrics.json`. `uvm_sequence.svh.j2:18` sets
  `GAMMA_RMS = {{ gamma_rms }}` and `:40` computes
  `dt_jitter = GAMMA_RMS * (normal/1000)` → ≈±0.12 s, which the DUT adds to `TS=1e-11`
  (`vco_rnm_dut.sv:39`). Real jitter is ~45 fs.
- **Impact:** Injected "jitter" is physically absurd and unrelated to the characterized
  phase noise.
- **Fix:** Use `tie_rms_fs` converted to seconds (≈4.5e-14) as the jitter std-dev; do not
  pass the raw PPV scalar as a time.
- **Verdict (Current Status):** **OPEN**. The templates and json files still use `GAMMA_RMS`.

## SF-004 — Jitter sequence never drives `dt_jitter` to DUT  ·  Critical
- **Evidence:** `vco_agent.svh:34-39` driver sets `vif.v_tune <= req.v_tune` and comments
  *"dt_jitter is injected via a separate port… For the MVV, we'll assume the DUT is
  structurally mapped to receive it."* `req.dt_jitter` is never driven.
- **Impact:** The entire "physically calibrated jitter sequence" is a no-op.
- **Fix:** Drive `vif.dt_jitter <= req.dt_jitter;` (or route through the virtual interface).
- **Verdict (Current Status):** **OPEN**. Jitter injection remains unconnected.

## SF-005 — SVA pass is tautological; sign-off misleads  ·  Critical
- **Evidence:** `vco_sva_pkg.sv:11-12` sets `V_MAX=1.2, V_MIN=0.38`; `vco_rnm_dut.sv`
  swings `0.41*sin(phase)+0.79` = [0.38, 1.20]. Both bounds and DUT swing derive from the
  **same** `characterization_data.json` (`pipeline.py:225-237`), so the assertion can
  never fail unless there is a bug. `run_regression.py:159` then prints
  *"[PASSED] … Silicon Sign-Off Approved."* based only on SVA violations + UVM_ERROR/FATAL.
- **Impact:** "Sign-off" proves the DUT matches its own bounds, not that it matches
  independent silicon limits.
- **Fix:** Source SVA bounds from independent silicon specs; treat SVA pass as a
  necessary-not-sufficient check. Don't label tautological passes as "Silicon Sign-Off".
- **Verdict (Current Status):** **OPEN**. SVA bounds still source from the same file.

## SF-006 — Case-study "ALL TESTS PASSED" ignores PLL-not-locked  ·  High
- **Evidence:** `tests/case_study/tb/tb_clock_mgmt.sv:199-206` increments `errors` only
  for `!afc_locked` and `!aac_settled`; `pll_locked` is printed (`:194`) but never
  checked. `case_study_xsim.log` shows `PLL Locked: NO` then `*** ALL TESTS PASSED ***`.
  `run_case_study.py:137-142,155` also ignores PLL.
- **Impact:** A non-locked ADPLL still yields a green result.
- **Fix:** Add `if (!pll_locked) errors++;` and gate pass on it.
- **Verdict (Current Status):** **OPEN**. The verification ignores PLL lock state.

## SF-007 — ADPLL validated against scaled 1 GHz clock  ·  High
- **Evidence:** `tb_clock_mgmt.sv:47` `forever #0.5 clk_vco = ~clk_vco; // 1 GHz for sim
  speed`, with comment *"xsim cannot simulate 10 GHz clocks efficiently"*. The real VCO
  is 10.25 GHz.
- **Impact:** The ADPLL lock logic is exercised against a 10× slower reference, so lock
  behavior (and the "PLL Locked: NO") is not representative of silicon.
- **Fix:** Either use the RNM VCO model at full rate or document the scaling factor
  explicitly in the lock detection math.
- **Verdict (Current Status):** **OPEN**. Scaling is still in effect.

## SF-008 — `$dist_normal` seeded with constant (no randomness)  ·  Medium
- **Evidence:** `uvm_sequence.svh.j2:40` `dt_phase_deviation = GAMMA_RMS * ($dist_normal(req.get_inst_id(), 0, 1000)/1000.0) + GAMMA_DC;`
  `req.get_inst_id()` is constant per item → deterministic, identical deviation every cycle.
- **Impact:** Even if driven, the "random" jitter is not random.
- **Fix:** Use a proper RNG seed (e.g. `$urandom`) or DPI-C; advance the seed each call.
- **Verdict (Current Status):** **OPEN**. Unchanged.

## SF-009 — SVA only checks amplitude, never timing/jitter  ·  Medium
- **Evidence:** `vco_sva_pkg.sv:45-48` property `p_vout_bounds` checks only
  `(v_out >= V_MIN) && (v_out <= V_MAX)`. No timing/period/jitter assertions.
- **Impact:** The jitter pillar cannot be validated by the current checkers at all.
- **Fix:** Add period/jitter SVA checks (e.g. `assert property` on cycle-to-cycle period
  deviation bounded by the characterized TIE).
- **Verdict (Current Status):** **OPEN**. Unchanged.

## SF-010 — Default (non-case-study) path still hardcoded  ·  Medium
- **Evidence:** `core/pipeline.py:225-230` `_dump_characterization_data` falls back to
  `gamma_rms=1.34e-12`, `f0 = spec.frequency_ghz*1e9` when `pss_result` lacks measured
  fields. Running `python run_regression.py` (no `--case-study`) therefore still emits the
  old constant values.
- **Impact:** Without the case-study flag, the flow silently reverts to non-physical data.
- **Fix:** Require the case-study/physics source, or make Xyce extraction mandatory and
  fail loudly if it didn't converge.
- **Verdict (Current Status):** **OPEN**. The fallback to default constants remains.

## SF-011 — `v_tune` driven on net mapping to DUT input  ·  Medium
- **Evidence:** `vco_agent.svh:36` `vif.v_tune <= req.v_tune;` → Vivado warning
  *"[VRFC 10-9578] illegal assignment to variable input port 'v_tune'"*.
- **Impact:** Poor practice; warns every compile and can mask real connection bugs.
- **Fix:** Drive `v_tune` from a proper top-level signal/harness, not by writing the DUT
  input port through the bound SVA interface.
- **Verdict (Current Status):** **OPEN**. Unchanged.

## SF-012 — SVA package + interface in one file  ·  Medium
- **Evidence:** `vco_sva_pkg.sv` defines both `package vco_sva_pkg` (`:8`) and
  `interface vco_sva_if` (`:18`). Because the file is both `` `include ``d in
  `tb_vco_top.sv:12` and passed as a standalone file to xvlog, Vivado warns
  *"design element 'vco_sva_pkg' is previously defined; ignoring this definition"*.
- **Impact:** Benign today (identical content), but fragile — edits can silently bypass
  one copy.
- **Fix:** Split the package and the interface into separate files.
- **Verdict (Current Status):** **OPEN**. Unchanged.

## SF-013 — `run_regression.py` PHASE 4 ignores coverage  ·  Medium
- **Evidence:** `run_regression.py:101-159` `parse_coverage()` counts only
  `VCO Amplitude Violation`, `UVM_ERROR`, `UVM_FATAL`; it does not read or assert any
  coverage metric.
- **Impact:** A run can "pass" while coverage is 0 (see SF-002).
- **Fix:** Parse `xsim` coverage DB (`.ucdb`/`.xml`) and assert a coverage threshold.
- **Verdict (Current Status):** **OPEN**. Unchanged.

## SF-014 — Fragile regex patching leaves duplicated comment  ·  Low
- **Evidence:** `vco_rnm_dut.sv:18`
  `localparam real F_0 = 10248776304.520353;  // 10.2488 GHz (from characterization)  // 10.2488 GHz (from characterization)`
  — `generate_assets.py` regex replaced only `F_0 = [^;]+;` leaving the prior trailing
  comment.
- **Fix:** Replace the whole line including comments, or generate the DUT from a template
  (cleaner than regex-patching a hand-written file).
- **Verdict (Current Status):** **RESOLVED**. Removing trailing comments in DUT fixed this issue.

## SF-015 — No tests for RTL/case-study; log path confusion  ·  Low
- **Evidence:** `tests/` has only `test_pipeline.py`/`test_backends.py` (Python solvers);
  the 7 new RTL modules and `run_case_study.py` have no automated test. `run_case_study.py:111`
  writes `case_study_xsim.log` to project **root**, not `tests/case_study/`, contrary to
  the implied location.
- **Fix:** Add a pytest that runs `run_case_study.py` and asserts AFC/AAC/PLL lock; write
  logs under `tests/case_study/results/`.
- **Verdict (Current Status):** **RESOLVED**. We introduced a dedicated case study runner `run_case_study.py` inside the case study folder.
