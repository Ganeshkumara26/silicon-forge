# SiliconForge — Issue Tracker

Generated from a full code/execution audit on 2026-07-14.
Status legend: `Open`. Severity: `Critical` / `High` / `Medium` / `Low`.

> Summary: 20 issues. The toolchain runs on real simulators (Vivado/Xyce), and the
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
| SF-014 | Fragile regex patching leaves duplicated comment in DUT | Low | Open | `uvm_verification/vco_rnm_dut.sv` |
| SF-015 | No regression tests for new RTL / case-study; log path confusion | Low | Open | `tests/`, `run_case_study.py` |
| SF-016 | Coverage subscriber samples output **voltage**, not frequency → bins meaningless | Critical | Open | `uvm_verification/vco_agent.svh`, `vco_coverage.svh` |
| SF-017 | RNM DUT applies jitter to 10ps sub-step, not the ~10ns clock period → jitter ~1000× wrong | Critical | Open | `uvm_verification/vco_rnm_dut.sv` |
| SF-018 | `automation/end_to_end.py` broken: globs removed `chapter_*_*.yaml` → startup failure | Medium | Open | `siliconforge/automation/end_to_end.py` |
| SF-019 | DUT `phase` accumulator never wrapped → `$sin` precision loss over long sims | Low | Open | `uvm_verification/vco_rnm_dut.sv` |
| SF-020 | `vco_transaction` `v_tune` randomization unused; sequence hardcodes `v_tune=0.6` | Low | Open | `uvm_verification/vco_transaction.svh`, `vco_jitter_sequence.svh` |

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
- **Verdict (Current Status):** **OPEN**. The duplicated comment is still present in
  `vco_rnm_dut.sv:18` as of this audit (`F_0 = 10248776304.520353;  // 10.2488 GHz … // 10.2488 GHz …`).

## SF-015 — No tests for RTL/case-study; log path confusion  ·  Low
- **Evidence:** `tests/` has only `test_pipeline.py`/`test_backends.py` (Python solvers);
  the 7 new RTL modules and `run_case_study.py` have no automated test. `run_case_study.py:111`
  writes `case_study_xsim.log` to project **root**, not `tests/case_study/`, contrary to
  the implied location.
- **Fix:** Add a pytest that runs `run_case_study.py` and asserts AFC/AAC/PLL lock; write
  logs under `tests/case_study/results/`.
- **Verdict (Current Status):** **OPEN**. `tests/` still contains only `test_pipeline.py` /
  `test_backends.py` (Python solvers); the 7 RTL modules and `run_case_study.py` have no
  automated test.

---

## SF-016 — Coverage subscriber samples voltage, not frequency  ·  Critical
- **Evidence:** `vco_agent.svh:68` `vout_ap.write(vif.v_out)` writes the DUT output
  **voltage** (≈0.38–1.20). `vco_coverage.svh:48-49` does
  `current_f0_khz = longint'(t / 1000.0);` i.e. it treats `t` as a frequency in Hz and
  converts to kHz. The coverpoint bins are ~9.9e6–1.007e7 kHz (≈9.9–10.1 GHz).
- **Impact:** Even after SF-002 connects the subscriber, the covergroup bins a voltage
  value (~0) against frequency ranges (~1e10 kHz), so every sample is outside all bins.
  The "3σ statistical coverage" is semantically invalid — it never sees a frequency, and
  no frequency signal exists in the DUT/monitor to sample.
- **Fix:** Add a frequency output (measure period from `v_out` zero-crossings, or expose
  `f_inst`) and write that to the analysis port; or redefine the covergroup to bin the
  signal actually produced. Do not rename voltage as frequency.

## SF-017 — Jitter applied to 10ps sub-step, not the 10ns clock period  ·  Critical
- **Evidence:** `vco_rnm_dut.sv:23` `localparam real TS = 1e-11;` (10 ps) and `:39`
  `phase <= phase + 2*PI*f_inst*(TS + dt_jitter);`. The DUT is clocked at 100 MHz
  (`tb_vco_top.sv:71` `forever #5 clk` → 10 ns period). `dt_jitter` is added to `TS`
  (the internal 10 ps sub-step), never to the 10 ns clock period.
- **Impact:** F_0 is realized by running 1000 sub-steps per 10 ns clock edge
  (1000 × 2π·f·TS ≈ 102.5 cycles / 10 ns). Adding jitter to `TS` scales it by `dt/TS`;
  a physically correct `dt≈45 fs` gives `45e-15/1e-11 = 4.5e-3` → **~1000× too large**
  versus adding it to the 10 ns period (`45e-15/1e-8 = 4.5e-6`). So even a correctly
  sized `gamma_rms` injects jitter ~1000× wrong. Compounds SF-003 (gamma 9 orders off)
  and SF-004 (never driven).
- **Fix:** Model jitter as a perturbation of the clock period (advance phase by
  `2*PI*f_inst*(clk_period + dt_jitter)` per edge), or drive `dt_jitter` already scaled to
  the clock period; keep `TS` for sub-cycle resolution only.

## SF-018 — `end_to_end.py` broken by chapter-YAML removal  ·  Medium
- **Evidence:** `siliconforge/automation/end_to_end.py` `load_chapters()` does
  `yaml_files = sorted(root.glob("chapter_*_*.yaml"))` and has guards like
  `_MISSING_CHAPTER_06` referencing `chapter_06_cml_frequency_bridge.yaml`. Those 14
  files were removed from the repo root per the cleanup request.
- **Impact:** `python -m siliconforge.automation.end_to_end` now fails at startup (no
  chapter YAMLs found / missing-chapter guard trips). The engine is dead until retargeted.
- **Fix:** Restore the chapter specs under a tracked path (e.g. `specs/`) and point
  `load_chapters()` there, or remove `end_to_end.py`/`staged_design.py` if the case-study
  path supersedes them.

## SF-019 — DUT `phase` never wrapped  ·  Low
- **Evidence:** `vco_rnm_dut.sv:39` `phase <= phase + 2*PI*f_inst*(TS + dt_jitter);`
  accumulates without modulo. Over long runs `phase` grows large and `$sin(large_real)`
  loses floating-point precision.
- **Impact:** Slow numerical drift in `v_out` for extended simulations (minor at 1000
  cycles, worse over millions).
- **Fix:** Wrap phase: after accumulation, `if (phase > 2*PI) phase <= phase - 2*PI;`
  (or `phase = fmod(phase, 2*PI);`).

## SF-020 — `v_tune` randomization dead code  ·  Low
- **Evidence:** `vco_transaction.svh:24-27` declares `rand int v_tune_mv` with a
  `[0:1200]` constraint and maps it to `v_tune` in `post_randomize()`. But
  `vco_jitter_sequence.svh:43` sets `req.v_tune = 0.6;` directly and never calls
  `req.randomize()`, so the constraint/frequency-sweep infrastructure is never exercised.
- **Impact:** The DUT always sees a fixed tune voltage; no tuning-range stimulus coverage.
  Misleading "constraint-random" framing.
 - **Fix:** Randomize the transaction (`req.randomize()` with `v_tune_mv` constrained) or
   delete the unused randomization fields.

## SF-021 — Capstone SPICE netlists V1–V3 use undefined simplified MOS models (no PDK include)  ·  Critical
- **Evidence:** `_archive_junk/power-clock-co-design/src/spice/v1_varactor_vco.cir:14-15`
  instantiates `MN1 ... VSS nmos_rf W={W_nmos} L=0.13u` with **no `.MODEL nmos_rf`**
  and **no `.LIB`/`.INCLUDE`** of the IHP SG13G2 PDK. V2 adds `pmos_rf` (also undefined).
  V3 inherits V2. Contrast with `tests/case_study/netlists/v1_varactor_vco.cir` which uses
  `sg13_lv_nmos` (real PSP103 subckt loaded via `Xyce_Plugin_PSP103_VA.so`).
- **Impact:** All 91 capstone figures and claimed metrics (-129.5 dBc/Hz @1 MHz, 84.5 fs,
  16.59 GHz resonance) were generated on undefined/simplified Level-3 MOS models, not the
  real IHP PSP103 PDK. The MASTER_DOCUMENT's "strictly generated using these true physical
  metrics" is factually incorrect (see TIMELINE.md §6).
- **Fix:** Re-run capstone simulations with real PSP103 models, or clearly mark all capstone
  results as "simplified-model reference only — not valid for silicon sign-off."

## SF-022 — `adpll_ppv.v` uses a fake counter-based TDC instead of a real TDC  ·  High
- **Evidence:** `_archive_junk/power-clock-co-design/src/rtl/adpll_ppv.v:23` comment:
  *"In a real ADPLL, we would have a TDC... Here we model the phase error digitally using
  counters."* The "TDC" is a free-running counter, not a time-to-digital converter.
- **Impact:** The ADPLL lock behavior and jitter claims in the capstone are not based on a
  real TDC. The "PLL Locked: NO" result in the current case study may reflect the gap
  between this behavioral model and a real sub-cycle TDC.
- **Fix:** Either implement a gated-ring or Vernier TDC in RTL, or document the behavioral
  approximation explicitly in any claims derived from it.

## SF-023 — `mock_spice_results.py` explicitly generates fabricated SPICE data  ·  Critical
- **Evidence:** `_archive_junk/power-clock-co-design/src/python/mock_spice_results.py:5-16`
  `main()` writes `ppv_convergence.json` with synthetic `10**(-val)` relative-error data
  and prints *"Generated mock ppv_convergence.json"*. Lines 26-28: when `ppv_vector.json`
  is missing, generates an analytical fallback (`-0.5 * sin(...)`). Lines 33-34: scales it
  for PVT corners (`SS` ×1.15, `FF` ×0.85) without any SPICE back-annotation.
- **Impact:** Some of the "91 figures" and "PVT corner sweep" data are explicitly synthetic,
  not from SPICE. This was used to populate the capstone MASTER_DOCUMENT results.
- **Fix:** Replace mock data generation with actual SPICE result parsing, or remove the
  mock generator and clearly label any remaining synthetic data.

## SF-024 — `system_integration.py` returns hardcoded simulated startup metrics  ·  Medium
- **Evidence:** `_archive_junk/power-clock-co-design/src/python/system_integration.py:15-23`
  `startup_sequence()` returns `{'afc_lock_time_us': 8, 'aac_settling_us': 0.02,
  'adpll_lock_time_us': 15}` with print statements *"Step 1: AFC Locking... (simulated)"*.
  These exact values appear in the capstone MASTER_DOCUMENT timing claims.
- **Impact:** Startup timing claims in the capstone are not measured from simulation; they
  are hardcoded constants that look like measured results.
- **Fix:** Remove hardcoded values and measure actual simulation startup times, or label the
  values as "target/estimated" rather than measured.

## SF-025 — Cocotb tests in `tb_varactorless.py` print "PASSED" unconditionally  ·  High
- **Evidence:** `_archive_junk/power-clock-co-design/src/testbenches/tb_varactorless.py:64`
  `dut._log.info("PPV compliance test PASSED")` after only counting violations with no
  assertion on the count. Lines 116, 163, 220, 276: all tests print "PASSED" unconditionally
  after logging observations, without `assert` statements or pass/fail conditions.
- **Impact:** The capstone "verification" does not actually fail on any condition. All tests
  pass regardless of DUT behavior, including the PVT corner sweep which only logs
  "hierarchical_access_limited" when signals are inaccessible.
- **Fix:** Add `assert` statements with explicit pass/fail conditions (e.g. `assert
  afc_violation_count == 0`), and fail the testbench when conditions are not met.

## SF-026 — Capstone RTL constraints derived from simplified-model PPV extraction  ·  High
- **Evidence:** `_archive_junk/power-clock-co-design/src/rtl/ppv_constraints.vh` contains
  `PPV_PMU_SAFE_BIN_LO`, `PPV_AFC_MAX_STEP_MV`, etc. These values originate from
  `ppv_data.json`, which was generated by the simplified-model PPV solvers (V1–V3 netlists).
  The real-PDK PPV extraction in the current repo (`tests/case_study/`) produces different
  safe windows and jitter values.
- **Impact:** The behavioral RTL in `_archive_junk/power-clock-co-design/` is tuned to the
  wrong physics. Even if re-simulated with real PDK, the digital controllers would enforce
  constraints (safe bins, step sizes) derived from simplified models, not the real device.
- **Fix:** Re-extract PPV/constraints from real-PDK simulations and regenerate the RTL
  parameter headers, or clearly label the current constraints as simplified-model only.

## SF-027 — `ppv_phase_tracker.v` is a free-running 3-bit counter, not real phase tracking  ·  Medium
- **Evidence:** `_archive_junk/power-clock-co-design/src/rtl/ppv_phase_tracker.v` divides the
  VCO period into 8 bins using a free-running counter. There is no zero-crossing detection,
  no phase interpolation, and no relation to the actual PPV safe window (which is a
  continuous function of time, not 8 discrete bins).
- **Impact:** The "phase-safe" gating in all capstone RTL is based on 45° coarse bins
  derived from simplified models. The claimed "0°–45° safe window" is an approximation
  that does not reflect continuous PPV sensitivity.
- **Fix:** Replace the counter with a zero-crossing-based phase tracker, or add a note that
  the 8-bin discretization is a behavioral approximation for simulation only.

## SF-028 — Project diary partially fabricated to hide capstone failure  ·  Critical
- **Evidence:** `the_mode_that_never_corrects_itself (2).md` presents a clean heroic
  month-by-month narrative. `MASTER_CHAT_RAW_DUMP.md` (16,677 lines) contains hundreds of
  admissions: *"fabricated metrics"* (line 152), *"simplified Level-3 MOS models only"*
  (lines 823, 1458), *"never use simplified models, even for xyce"* (line 8987),
  *"must use complete IHP PDK models only; delete all simplified/modified PDK file
  references"* (lines 9940, 9963). `AI_HANDOVER.md` mandates: *"rebuild the 182 scripts
  and 91 figures with 100% honesty and real data."*
- **Impact:** The project record misrepresents the capstone's technical basis. Future work
  (thesis, publication, portfolio) built on these claims will inherit the simplified-model
  error and risk reproducibility failures.
- **Fix:** Treat `MASTER_CHAT_RAW_DUMP.md` as the authoritative record; mark the diary as
  half-fabricated; rebuild capstone figures with real PDK data per `AI_HANDOVER.md`.

