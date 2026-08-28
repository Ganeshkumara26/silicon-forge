# Silicon Forge — Present State Analysis and Path to a Robust Mixed-Signal Verification Tool

## Verification note on the source review

Before treating REVIEW.md as ground truth, I independently re-derived three of its core mathematical claims rather than accept them on prose alone:

- **The PPV monodromy matrix bug (§2.4):** confirmed by direct computation. `np.outer(dx, np.ones(n))` produces a matrix where every column is literally identical, which is rank-1 by construction — verified this numerically, not just algebraically. A rank-1 matrix has (n−1) zero eigenvalues by definition; for your 2-state case, that's exactly the {1, 0} the review describes, confirmed by computing actual eigenvalues.
- **The jitter factor-of-2 bug (§2.2):** the claimed √2 ≈ 1.414× overstatement is the exact, correct consequence of taking `sqrt(2 * integral)` instead of applying the factor before integration — dimensionally and algebraically sound.
- **The Leeson filter-factor bug (§2.1):** the standard Leeson model's `(1 + (f0/2Qfm)^2)` term is a smooth function of offset frequency with no discontinuity. Code that conditionally switches between the squared term and `1.0` based on a corner-frequency comparison introduces an artificial step function the real physics doesn't have.

All three check out. This review is technically sound, not just confidently worded, and the rest of this document treats its findings as accurate.

## Why this review matters more than it might first appear

This isn't just "a project has bugs." Silicon Forge is the piece of your CV I flagged, independently, before this review existed, as the single highest-suspicion claim in your entire portfolio — I noted at the time that PPV/Floquet phase-noise characterization is genuinely graduate-research-level work, and that I had no way to verify whether the −150.2 dBc/Hz figure your CV cites was real. This review answers that question directly: **the phase noise, PPV, and jitter numbers Silicon Forge currently produces are not "unverified." They are computed from formulas that are provably wrong**, independent of what circuit you feed them. That's a stronger and more useful finding than "I couldn't check this" — it tells you specifically what to fix, not just that something might be off.

There's also a second, quieter finding buried in §4 that deserves equal weight: **the project's own history includes a hardcoded jitter value (45 fs) that was reported for every circuit regardless of what was actually simulated, tautological assertions that could never fail because they were built from their own answer key, and synthetic Monte Carlo data presented as measured results.** The review notes these have been "partially addressed" — worth confirming that's actually true before relying on it, since "partially" is doing real work in that sentence.

---

## Present State, Organized by What Actually Matters for Your CV's Claims

### Tier 1 — Wrong, and directly falsifies specific CV claims

| Component | Review finding | CV claim it undermines |
|---|---|---|
| `pnoise_analysis.py` (Leeson model) | Missing T/F/P from thermal term, wrong conditional filter factor, wrong flicker denominator | Any phase-noise number derived through this path, including the CV's −150.2 dBc/Hz figure, is not currently trustworthy as computed |
| `ppv_jitter.py` | √2 factor-of-2 error | Any jitter figure passed through this specific integration path (distinct from `jitter.py`, which the review confirms is correct) is ~41% too high |
| `harmonic_balance.py` | Jacobian has zero circuit admittance on the diagonal — represents no real circuit, Newton iteration structurally cannot converge | The 9-stage pipeline's periodic-steady-state solving step doesn't actually solve for your circuit's real periodic state |
| `ppv_eigenanalysis.py` | Monodromy matrix construction is rank-1 by construction, ISF built as an ad-hoc perpendicular vector rather than the correct adjoint eigenvector | This is the actual PPV/ISF extraction your CV describes — currently produces numbers with no connection to your circuit's real sensitivity function |

### Tier 2 — Structurally disconnected, independent of correctness

The review's §3.2 finding is worth sitting with on its own: **the entire `backends/` package — the clean, well-designed Simulator ABC you built — is never called by the actual 9-stage pipeline.** The pipeline invokes Xyce directly via subprocess, bypassing the abstraction entirely. This means fixing the Tier 1 math bugs alone would not make the pipeline correct, because the pipeline isn't even running through the interface that was designed to make results trustworthy and swappable across simulators.

### Tier 3 — Honest gaps, correctly labeled by the review as gaps rather than bugs

9 of 16 regression circuits are `NOT_IMPLEMENTED`. No `.noise` SPICE analysis exists anywhere in the pipeline — meaning phase noise has never actually been extracted from a real SPICE simulation, only from the broken analytical formula. This is a scope gap, not a correctness bug, and it's worth keeping that distinction clear as you plan fixes, since "extend `.noise` analysis" is a different kind of work than "fix a wrong formula."

### Tier 4 — What's actually solid, and should anchor the rebuild

`spice_runner.py` is the review's one unqualified pass: correct WSL path handling, correct `.meas tran` generation, correct differential/single-ended detection, correct frequency parsing. The `jitter.py` module's integration functions (distinct from the broken `ppv_jitter.py`) are also confirmed correct. **This matters strategically:** you don't need to rebuild from zero. You have one verified-correct SPICE-interaction pattern and one verified-correct math module. Everything else should be rebuilt to match their standard, not invented fresh.

---

## What "Robust Enough to Support Your CV's Mixed-Signal Claims" Actually Requires

Your CV describes a 9-stage pipeline extracting L(fm), RMS jitter, and Verilog-A behavioral models from transistor-level netlists via shooting-Newton PSS and PPV/Floquet extraction. For Silicon Forge to genuinely support that claim — not just exist as a repo, but produce numbers you could defend under direct questioning — it needs to actually do those things correctly. Here's the honest path, organized by dependency order rather than the review's priority numbering, since some fixes are meaningless before others land.

### Phase 0 — Fix the foundation before touching anything downstream

**Connect the pipeline to the backend ABC, or delete the ABC.** The review is right to frame this as a binary choice (§8, Priority 2, item 8). Right now you have two parallel, disconnected implementations of "talk to a simulator" — a clean one nobody uses, and a broken one (Xyce via raw subprocess) that everything actually calls. Fixing Xyce-vs-ngspice confusion without resolving this disconnect just produces a differently-broken pipeline. This has to come first because every other fix downstream assumes the pipeline is actually running through a verified simulator interface.

**Fix the harmonic balance Jacobian.** This is upstream of PPV/ISF extraction — you cannot correctly extract a periodic-steady-state sensitivity function from a solver that isn't finding the real periodic steady state. The review's diagnosis (missing circuit admittance on the diagonal, `residual()` never evaluating actual circuit equations) points to the fix directly: the Jacobian needs your circuit's real G (conductance) and C (capacitance) matrices, not a bare spectral-differentiation operator.

### Phase 1 — Fix the four mathematical bugs, in dependency order

1. **Leeson model** (`pnoise_analysis.py`) — independent of the others, fix first since it's the most isolated
2. **Monodromy matrix / PPV extraction** (`ppv_eigenanalysis.py`) — depends on Phase 0's harmonic balance fix being real, since PPV extraction needs an actual periodic orbit to differentiate around
3. **ISF construction** — depends on #2 producing a real eigenvector to use, not the current ad-hoc perpendicular-vector substitute
4. **Jitter integration** (`ppv_jitter.py`'s √2 bug) — the simplest fix, but validate it last, since jitter is computed *from* the phase noise curve, so it inherits correctness from Phase 1 step 1

### Phase 2 — Make correctness checkable, not just claimed

This is the part your CV's own credibility depends on most, and it's where the review's honesty findings (§4) become directly actionable rather than just embarrassing. Once the math is fixed:

- **Validate against a circuit with a known, published, or hand-derivable phase-noise answer** — a simple LC oscillator with textbook Q and power values is the right first target, precisely because you can compute the expected L(fm) by hand and compare, the same way you've verified other numbers throughout this project by independent derivation.
- **Remove the remaining hardcoded/analytical-fallback jitter values from anywhere they could be mistaken for measured results** — the review notes the regression suite still uses hardcoded Q=8, P=5mW, F=6dB as inputs to an otherwise-correct formula. That's fine as a labeled estimate; it's not fine if it's ever presented as a per-circuit measured result.
- **Re-run the regression suite's 5 currently-passing circuits (nmos_oscillator, hbt_oscillator, lc_vco, ring_oscillator, differential_vco) through the corrected pipeline** and confirm the numbers actually change from their current (wrong) values — if they don't change, the fix didn't actually take effect in the path being tested.

### Phase 3 — Extend `.noise`-based SPICE phase noise as a cross-check

The review correctly notes no SPICE `.noise` analysis exists anywhere in the framework — meaning even after Phase 1's formula fix, you'd have a *correct analytical model*, not a *SPICE-measured* result. For a claim as specific as your CV's, having both — a corrected Leeson-model estimate and an independent SPICE `.noise`-derived figure that agrees with it — is a materially stronger position than either alone, and it directly mirrors the cross-check discipline the review praises elsewhere (§2.5, "Cross-check methodology: Early vs late crossing comparison is sound"). Apply that same "don't trust one number, get two independent numbers to agree" pattern here.

---

## Direct Answer to "How Can It Become Robust"

Robust, for this project, doesn't mean "add more stages" or "support more circuit types." Given what the review found, it means: **every number the framework currently outputs for phase noise, PPV/ISF, or jitter needs to either be fixed at its mathematical root, or removed from the pipeline's output until it is.** The review's own estimate — 2–3 weeks of focused engineering for the four critical math fixes plus the Xyce/backend disconnect — is a real, bounded scope, not an open-ended rebuild. That tracks with what's actually broken: four specific, precisely-located bugs, one architectural bypass, not a fundamentally wrong design. The architecture the review praises (§6.1 — canonical schema, clean design config, well-defined Simulator ABC) is worth preserving exactly as designed; the problem isn't the shape of the system, it's that several specific components inside it compute the wrong answer, and one major component was built but never wired in.

**The most important sequencing decision, restated plainly:** don't try to make Silicon Forge "support your CV" by writing more documentation or expanding its regression coverage. Support the CV claim by making the four specific broken calculations correct, connecting the pipeline to the interface designed to make it trustworthy, and validating the result against at least one circuit where you can independently check the answer by hand — the same discipline that's caught every real bug across every project in this entire conversation so far.
