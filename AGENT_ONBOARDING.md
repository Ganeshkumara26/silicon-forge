# AI Agent Onboarding & Toolchain Survival Guide
**Target Architecture:** 10.25 GHz ADPLL & Radar-Inertial Georeferencing Coprocessor
**Technology Node:** IHP SG13G2 (130nm BiCMOS)
**Environment:** WSL (Windows Subsystem for Linux)

Welcome, future Agent! If you have just been instantiated to work on this repository, **READ THIS FILE FIRST**. It contains the hard-won fixes for every major EDA toolchain bug in this environment.

---

## 1. Environment & Pathing Gotchas (CRITICAL)

All tools run natively in WSL (`wsl bash -c "..."`). The Windows path contains spaces which will break scripts if not properly handled:
*   **Windows Path:** `D:\Desktop\Vault\03 Projects\Ganeshas projects\ppv guided clock generation adpll\ADPLL_10GHz`
*   **WSL Path:** `/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/ppv guided clock generation adpll/ADPLL_10GHz`

### The Space/Symlink Workaround
Tools like Yosys `ABC` and `ngspice` will silently fail or crash when they encounter spaces in paths to `.lib` or `.osdi` files.
**Solution:** A symlink must be used for the PDK root.
```bash
wsl bash -c "ln -sf '/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/ppv guided clock generation adpll/vco/IHP-Open-PDK-0.3.0/ihp-sg13g2' /tmp/ihp_sg13g2"
```
**Always use `/tmp/ihp_sg13g2` as your base PDK path in synthesis scripts and ngspice loads!**

---

## 2. Ngspice & Verilog-A (OSDI) Workflow

The IHP SG13G2 PDK uses Verilog-A models (like `psp103`) which `ngspice` cannot read directly. They must be compiled to `.osdi` binaries.

**Compilation:** We use `openvaf` natively in WSL. (Already done and copied to `/tmp/ihp-sg13g2/libs.tech/ngspice/va/...`)

### CRITICAL: psp103_nqs.osdi Fix (Non-Quasi-Static Model)

**Symptom:** ngspice fails with errors like:
```
Error opening osdi lib "/tmp/ihp-sg13g2/libs.tech/ngspice/va/psp103_nqs/psp103_nqs.osdi": file too short
```
This means the `psp103_nqs.osdi` file is missing or empty (0 bytes). Without it, transistor-level simulations will run but produce garbage results.

**Fix:** Compile with openvaf and copy to the correct location:
```bash
wsl bash -c "cd '/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/ppv guided clock generation adpll/vco/IHP-Open-PDK-0.3.0/ihp-sg13g2/libs.tech/verilog-a/psp103' && openvaf psp103_nqs.va"
wsl bash -c "cp '.../psp103/psp103_nqs.osdi' /tmp/ihp_sg13g2/libs.tech/ngspice/va/psp103_nqs/"
```

**Execution Command:** (Always export `PDK_ROOT`)
```bash
wsl bash -c "export PDK_ROOT='/tmp' && ngspice -b your_circuit.cir"
```

---

## 3. Digital Synthesis (Yosys 0.9)

Yosys version `0.9` is a strict Verilog-2005 parser. It **does not support modern SystemVerilog-2012 constructs**.
*   **No `typedef enum`:** Rewrite all states using `localparam` and `reg`.
*   **No `localparam logic`:** Rewrite as `localparam [7:0]`.
*   **No `automatic` functions:** Functions must be written in Verilog-2001 style.
*   **ABC Crash:** Use the `/tmp/ihp_sg13g2` symlink for `dfflibmap` and `abc` liberty flags.

### Yosys Path Handling (CRITICAL)
Yosys fails to read Verilog files when paths contain spaces. Write Yosys scripts to a file with QUOTED paths:
```python
ys_lines.append(f'read_verilog "{wsl_path(str(f))}";')  # QUOTE paths
with open('/tmp/synth.ys', 'w') as f:
    f.write('\n'.join(ys_lines))
subprocess.run(['yosys', '/tmp/synth.ys'])
```

---

## 4. Formal Verification (SymbiYosys / yosys-smtbmc)

SymbiYosys functionality is integrated via `yosys-smtbmc`. 

**Status:** The frontend works, but the SMT solvers (`z3` or `yices`) must be installed in WSL:
```bash
wsl bash -c "sudo apt-get install z3 yices2"
```
**Workflow:**
1. Generate SMT2: `yosys -p "read_verilog -formal design.sv; prep -top test; write_smt2 design.smt2"`
2. Run Solver: `yosys-smtbmc -s z3 design.smt2`

### async2sync for Formal Verification
Xyce's SMT2 backend doesn't support async-reset DFFs (`$adff`). Convert them first:
```bash
yosys -p 'read_verilog design.v; proc; opt; async2sync; opt; write_smt2 design.smt2'
```

---

## 5. Electromagnetic Simulation (OpenEMS)

OpenEMS is fully installed and available natively via `/usr/bin/openEMS`.

**Status:** Verified Working (v0.0.35).

**Workflow:** OpenEMS requires an XML geometry/FDTD file. Use the CSXCAD Python bindings to programmatically generate the XML structures and then invoke openEMS.

**Correct Python API:**
```python
import CSXCAD
import openEMS
from openEMS.ports import LumpedPort
import numpy as np

CSX = CSXCAD.ContinuousStructure()
FDTD = openEMS.openEMS(NrTS=1e4, EndCriteria=1e-4)
grid = CSX.GetGrid()
grid.SetDeltaUnit(1e-3)
grid.SetLines('x', np.arange(-50, 50, 2))
# ... setup materials, metal, ports ...
port1 = LumpedPort(CSX, 1, 50, [x1, y1, z1], [x2, y2, z2], 'x')
FDTD.SetCSX(CSX)
FDTD.SetGaussExcite(10.25e9, 5e9)
FDTD.Run(output_dir, verbose=1)
```

---

## 6. Xyce SPICE Simulator

**Status:** ✅ WORKING — The ONLY simulator for IHP HBT models.

**Critical Discovery:** ngspice **cannot** properly simulate IHP HBT models for RF applications (zero gain, no conduction, silent failures). Xyce is the ONLY working simulator for transistor-level designs with IHP SG13G2.

**Usage:**
```bash
wsl bash -c "cd '/mnt/d/.../path' && Xyce <file>.cir"
```

**Output:** `<filename>.cir.prn` (transient data), `<filename>.cir.mt0` (measure results)

**Key Syntax Differences from ngspice:**
1. No `.control` blocks
2. Use `.print tran v(node)` for output
3. Use `.measure tran metric PP v(node) FROM=t1 TO=t2` for scalar extraction
4. Use `X` device (subcircuit) for HBTs, NOT `Q`
5. Use node `0` for emitter/substrate, NOT `vss`
6. Use `UIC` flag in `.tran` to skip DC operating point (avoids latch-up with cross-coupled pairs)

---

## 7. HBT Model Loading — THE DEFINITIVE FIX (CRITICAL)

**Symptom:** Transistors don't conduct, zero gain, or `could not find a valid modelname`.

**Root Cause:** The IHP SG13G2 PDK HBT models use VBIC (level 12 in Xyce, level 9 in ngspice). **ngspice cannot properly simulate these models for RF applications.**

**THE ONLY WORKING APPROACH:** Use **Xyce** simulator with the IHP models directly:

```spice
* Include corner parameters
.param vbic_cje = 1.0
.param vbic_cjc = 1.0
.param vbic_cjcp = 1.0
.param vbic_is = 1.0
.param vbic_ibei = 1.0
.param vbic_re = 1.0
.param vbic_rcx = 1.0
.param vbic_rbx = 1.0
.param vbic_tf = 1.0

* Include HBT model library (Xyce format)
.include /tmp/ihp_sg13g2/libs.tech/xyce/models/sg13g2_hbt_mod.lib
.lib /tmp/ihp_sg13g2/libs.tech/xyce/models/cornerCAP.lib cap_typ
.lib /tmp/ihp_sg13g2/libs.tech/xyce/models/cornerRES.lib res_typ

.options reltol=1e-4 temp=27

* Instantiate transistors using X device (subcircuit)
* Models available: npn13G2 (standard), npn13G2l (low-noise), npn13G2v (high-voltage)
X1 collector base emitter substrate npn13G2l
```

**Scaling for different emitter sizes:**
```spice
X1 coll base emit 0 npn13G2l PARAMS: Nx=4
```

**CRITICAL: Use node `0` for emitter/substrate, NOT `vss`!**

---

## 8. Xyce Simulation Syntax (CRITICAL)

**Xyce uses different syntax than ngspice:**

1. **No `.control` blocks** — Xyce doesn't support ngspice `.control` syntax
2. **Use `.print` for output:**
   ```
   .op
   .print dc v(base) v(coll) i(Vdd)
   ```
3. **Use `.measure` for scalar extraction:**
   ```
   .tran 0.1n 20n
   .measure tran Vout_pp PP v(out) FROM=15n TO=20n
   .measure tran gain PARAM Vout_pp/Vin_pp
   ```
4. **Output goes to `.prn` file** — not stdout
5. **Fourier analysis:**
   ```
   .four 1GHz v(out)
   ```

**Complete Xyce netlist structure:**
```spice
* Title
.param vbic_cje = 1.0
.param vbic_cjc = 1.0
.param vbic_cjcp = 1.0
.param vbic_is = 1.0
.param vbic_ibei = 1.0
.param vbic_re = 1.0
.param vbic_rcx = 1.0
.param vbic_rbx = 1.0
.param vbic_tf = 1.0

.include /tmp/ihp_sg13g2/libs.tech/xyce/models/sg13g2_hbt_mod.lib
.lib /tmp/ihp_sg13g2/libs.tech/xyce/models/cornerCAP.lib cap_typ
.lib /tmp/ihp_sg13g2/libs.tech/xyce/models/cornerRES.lib res_typ

.options reltol=1e-4 temp=27

* Circuit...
Vdd vdd 0 1.2
X1 coll base 0 0 npn13G2l PARAMS: Nx=4

* Analysis
.op
.print dc v(base) v(coll) i(Vdd)

* Transient (uncomment for time-domain)
*.tran 0.1n 20n
*.measure tran Vout_pp PP v(out) FROM=15n TO=20n
*.print tran v(out)
.end
```

---

## 9. Pre-Flight Diagnostics (`doctor.py`)
Before executing any major simulation or architectural changes, you must verify the environment health using the built-in diagnostic tool located at the root of `open_source_tools/`.
```bash
wsl bash -c "cd '/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/open_source_tools' && python3 doctor.py"
```
This runs a critical 4-layer smoke test verifying the host OS, executables (Yosys, OpenEMS, Ngspice), PDK bindings, and basic solver functionality.

---

## 10. Cycle-Accurate Digital Simulation (Verilator)
While Yosys is used for synthesis and SymbiYosys for formal property verification, **Verilator** is our primary C++ cycle-accurate simulation engine for complex digital testbenches.

---

## 11. Physical Design / ASIC (OpenLane vs OpenROAD)
For ASIC physical layout (GDSII generation), we explicitly maintain two distinct flows depending on the requirement (see `tests_physical/hello_world_asic`):
1. **Raw OpenROAD**: Used for custom RF macro placement, SRAM integration, and bespoke Power Delivery Network (PDN) design.
2. **OpenLane**: Used for rapid, automated RTL-to-GDSII synthesis of standard digital logic blocks.

---

## 12. System Regression & Certification (`certify.py`)
When block-level modifications are complete, the entire environment must be re-certified. This ensures no downstream solvers or tools were broken.
```bash
wsl bash -c "cd '/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/open_source_tools' && make test"
```

---

## 13. ADPLL-Specific Tool Fixes (2026-08-28)

### Fix 13.1: WSL-in-WSL Subprocess Detection (CRITICAL)
**Symptom:** Python scripts fail with "WSL not found" when run from WSL.
**Fix:** Add WSL detection to all `subprocess.run` wrappers:
```python
import os
in_wsl = os.path.exists("/mnt/WSL") or "microsoft" in os.uname().release.lower()
if in_wsl:
    result = subprocess.run(["bash", "-c", cmd], ...)
else:
    result = subprocess.run(["wsl", "bash", "-c", cmd], ...)
```

### Fix 13.2: OSDI Files at Root Path (CRITICAL)
**Symptom:** ngspice fails to load OSDI files or produces garbage results.
**Fix:** Use underscore symlink consistently:
```bash
wsl bash -c "rm -rf /tmp/ihp-sg13g2; ln -sf '/mnt/d/.../ihp-sg13g2' /tmp/ihp_sg13g2"
wsl bash -c "mkdir -p /tmp/ihp_sg13g2/libs.tech/ngspice/va/{psp103,psp103_nqs,mosvar,r3_cmc}"
wsl bash -c "cp /tmp/ihp_sg13g2/libs.tech/verilog-a/psp103/psp103.osdi /tmp/ihp_sg13g2/libs.tech/ngspice/va/psp103/"
```

### Fix 13.3: PSP103 Models Are Subcircuits (CRITICAL)
**Symptom:** `could not find a valid modelname` for `sg13_lv_nmos` with `M` prefix.
**Fix:** Use `X` prefix for all PSP103 transistors:
```spice
X1 d g 0 0 sg13_lv_nmos W=20u L=0.13u  ; CORRECT
M1 d g 0 0 sg13_lv_nmos W=20u L=0.13u  ; FAILS
```

### Fix 13.4: Cannot Load Two .lib Files Simultaneously
**Fix:** Use only ONE `.lib` statement per simulation.

### Fix 13.5: Startup Kick for Oscillators
**Fix:** Always add a current pulse between differential outputs:
```spice
I_kick out_p out_n PWL(0 0 1p 1m 2p 0)
```

### Fix 13.6: CML Divider Convergence
**Solution:** Use bottom current steering topology:
- Input pair and regeneration pair share a common tail current
- Clock steers current between pairs using differential steering pair at bottom
```spice
* Input pair (top)
X_in1 out_p in_p n1 0 npn13G2l
X_in2 out_n in_n n1 0 npn13G2l
* Regeneration pair (top)
X_reg1 out_p out_n n2 0 npn13G2l
X_reg2 out_n out_p n2 0 npn13G2l
* Current steering (bottom)
X_steer1 n1 clk tail 0 npn13G2l
X_steer2 n2 clk_n tail 0 npn13G2l
* Tail current
I_tail tail 0 DC 2m
```

### Fix 13.7: Transformer Design Parameters (from batuhan_sutbas.pdf)
- Coupling coefficient: k = 0.6-0.65 (narrowly spaced inductors)
- Q-factor: ≈15 at Ka-band
- Inductor geometry: Octagonal spiral
- Metal: 3µm top metal (TM2)
- Line width: 2.6-5.9 µm
- Edge spacing: 1.64 µm (minimum process)
- Broadside spacing: 2.8 µm

### Fix 13.8: Xyce Cross-Coupled Pair Latch-Up
**Symptom:** DC operating point fails with "singular matrix" for cross-coupled HBT pairs.
**Fix:** Add small series resistors (1Ω) to collectors + use `UIC` flag:
```spice
Rs1 vdd out_p 1
Rs2 vdd out_n 1
.tran 0.5p 20n 0 0.5p UIC
.IC V(out_p)=1.2 V(out_n)=0.0
```

### Fix 13.9: Xyce .print Limitations
**Symptom:** Xyce fails with "undefined symbols" for subcircuit internal nodes.
**Fix:** Only reference top-level nodes in `.print`. Subcircuit internal nodes (e.g., `q5_p`) are not accessible.

### Fix 13.10: PPV Extraction with Xyce (Phase Noise)

**Workflow:**
1. Create base netlist (no `.tran`, `.print`, `.end`)
2. Run PPV extraction script:
```bash
cd <netlist_directory>
python3 <path>/ppv_direct_injection.py --netlist <base>.cir --mode fast --nodes out_p out_n
```
3. Parse results from `ppv_data.json`

**Output:** `ppv_data.json` with PPV/ISF arrays per node, f0, T0

**Note:** Each perturbation runs a separate Xyce simulation (~1 min each). For 8 phase points × 4 nodes = 32 simulations ≈ 30 minutes total. Use `--nodes out_p` only for faster iteration.

**Phase Noise Formula (Hajimiri):**
```
L(f) = 10*log10( [Γ_rms² * S_thermal] / (2 * (2πf)² * q_max²) )
Where:
  Γ_rms = RMS of ISF
  S_thermal = 4*k_B*T*γ*gm (A²/Hz)
  q_max = C * V_swing (tank charge)
  f = offset frequency
```

### Fix 13.11: HBT Model Parameters — ALL vbic Parameters Required (CRITICAL)

**Symptom:** Xyce fails with `Parameter RE for model X:NPN13G2L_NX_VBIC contains unrecognized symbols: {3.19E+00*(2.5/El)*(4/Nx)**0.88*vbic_re}`

**Root Cause:** The npn13G2l HBT subcircuit has parameter expressions that depend on `vbic_re`, `vbic_rcx`, `vbic_rbx`. If these are not defined, Xyce cannot evaluate the expressions.

**Fix:** Always define ALL vbic parameters in every HBT simulation:
```spice
.param vbic_cje = 1.0
.param vbic_cjc = 1.0
.param vbic_cjcp = 1.0
.param vbic_is = 1.0
.param vbic_ibei = 1.0
.param vbic_re = 1.0
.param vbic_rcx = 1.0
.param vbic_rbx = 1.0
.param vbic_tf = 1.0
```

**IMPORTANT:** Even if you don't need to sweep these parameters, they MUST be defined or Xyce will abort. This applies to ALL simulations using `sg13g2_hbt_mod.lib`.

---

### Fix 13.12: CML Divider Feedback — HBT Base-Emitter Clamp (CRITICAL)

**Symptom:** CML divider outputs stuck at DC — no frequency division occurs. D_IN signals don't toggle.

**Root Cause:** The npn13G2l HBT's base-emitter junction acts as a diode clamp:
- When `V_base > V_emitter + 0.7V`, the junction conducts
- Voltage is clamped at `V_emitter + 0.7V`
- Feedback network cannot overcome this clamp

**Voltage Analysis:**
- Tail resistor 100Ω × 2mA → V_emitter ≈ 0.2V
- Base-emitter junction clamps at V_emitter + 0.7V ≈ 0.9V
- Feedback tries to drive D_IN to 1.13V but gets clamped to ~0.58V
- Differential input insufficient to switch the pair

**Recommended Fix:** Use emitter follower buffers between output and feedback:
```spice
* Emitter followers for feedback buffering
X_ef_p ef_p s_out 0 0 npn13G2l PARAMS: Nx=2
X_ef_n ef_n s_out_n 0 0 npn13G2l PARAMS: Nx=2
R_ef_p ef_p 0 1k
R_ef_n ef_n 0 1k

* Feedback from emitter follower outputs
R_fb_p d_in_p ef_n 500
R_fb_n d_in_n ef_p 500
```

**Alternative Fixes:**
1. Increase tail resistor to raise emitter voltage
2. AC-couple feedback with separate DC bias
3. Use different PDK model without clamp effect

**Status:** Individual CML latch validated (test_single_latch_v2.cir). Full divider needs buffered feedback.

---

### Fix 13.13: Xyce Behavioral Sources (B/E/G Devices)

**Symptom:** Confusion about what expressions work in Xyce behavioral sources.

**Working Syntax:**
```spice
* Voltage source with expression
B_out out 0 V='(V(in) > 0.6) * 1.2'
R_out out 0 1k

* Current source with expression
G_cp ctrl 0 VALUE = {((V(up) > 0.6) ? 1m : 0) - ((V(dn) > 0.6) ? 1m : 0)}
R_cp ctrl 0 1k
```

**Supported Operators:**
- Comparison: `>`, `<`, `>=`, `<=`, `==`, `!=`
- Logical: `&&`, `||`, `!`
- Arithmetic: `+`, `-`, `*`, `/`, `**`
- Ternary: `(condition) ? true_val : false_val`
- Functions: `sin()`, `cos()`, `sqrt()`, `abs()`, `exp()`, `log()`

**NOT Supported:**
- `.control` blocks (ngspice syntax)
- `MOD()` function (use custom expression)
- `IF()` statements (use ternary `?:`)

**Key Insight:** Use multiplication for AND logic:
```spice
* AND: both conditions must be true
B_out out 0 V='(V(a) > 0.6) * (V(b) < 0.6) * 1.2'
```

---

### Fix 13.14: CML Divider — Low-Side NPN Clock Switch
**Symptom:** CML divider outputs stuck at VDD — no switching occurs.

**Root Cause:** Clock switch transistor emitter connected to VDD instead of ground. For an NPN transistor used as a current switch, current flows from collector to emitter — the emitter must be at the lower potential.

**Correct Topology:**
```spice
X_clk tail clk 0 0 npn13G2l  ; Collector=tail, Base=clock, Emitter=ground
```

**Caution:** If the clock base voltage is too high relative to the collector/tail node, the base-collector junction can become strongly forward-biased, putting the HBT into hard saturation. For high-speed CML, you want the switch to steer current, not saturate deeply.

**Validation Check:**
```text
V_BE ≈ 0.7–0.85V when ON
V_BC not strongly forward-biased
V_CE enough to keep device out of deep saturation
```

---

### Fix 13.15: CML Divider — Voltage Headroom
**Symptom:** CML divider outputs not differential — both outputs at same voltage.

**Root Cause:** Stacked data-on-clock CML topology requires ~2.14V:
```
VBE_data + VCE_data + VBE_clock + VCE_clock + V_tail ≈ 2.14V
```

At VDD = 1.2V, this topology **cannot work**. Output common-mode is too low to drive next stage.

**Design Rule:** At 1.2V with IHP SG13G2 HBTs, avoid stacked CML latches. Use single-level current-steering latches with low-side clock switches.

**Correct Topology (Razavi-style):**
```
    VDD (1.2V)
     │      │
    R_L    R_L          ← Load resistors
     │      │
   OUT_P  OUT_N         ← Outputs
     │      │
    Q_D1   Q_D2         ← Data pair (ONE VBE above clock switch)
     │      │
     └──┬───┘
        │
      Q_CLK             ← Clock SWITCH (only VCE_SAT ≈ 0.15V)
        │
      I_TAIL
        │
       GND
```

**Voltage budget:** 0.78 + 0.20 + 0.15 = 1.13V < 1.2V

**Key Requirement:** Output common-mode must match next stage input common-mode.

---

### Fix 13.16: CML Divider — Edge-Triggered Operation (CRITICAL)

**Symptom:** CML divider output frequency = 2× input frequency (multiplication, not division).

**Root Cause:** Both master and slave latches are transparent during each clock cycle, causing the circuit to respond to both clock edges. The loop is level-triggered instead of edge-triggered.

**Required Phasing:**

| Phase | Master data | Master hold | Slave data | Slave hold | Action |
|-------|-------------|-------------|------------|------------|--------|
| Phase 1 | ON | OFF | OFF | ON | Master samples D |
| Phase 2 | OFF | ON | ON | OFF | Slave updates Q |

**Feedback:** `D_P = S_OUT_N`, `D_N = S_OUT_P` (toggle mode)

**Expected:** Output toggles once per clock cycle → `f_out = f_clk / 2`

**Key Insight:** Master and slave transparency windows must be **non-overlapping**. Within each latch, the data path and hold path must also be non-overlapping. If both are ON simultaneously, the latch has no clean memory.

---

### Fix 13.17: CML Divider — Non-Overlapping Master/Slave Phases

**Symptom:** Full divider responds to both clock edges. Individual latch works, but closed-loop divider does not divide.

**Root Cause:** Master and slave transparency windows overlap. Feedback propagates through both latches during the same clock phase.

**Fix:** Generate explicit non-overlapping phases with dead time:

```spice
.param T = 10n
.param dead = 300p
.param trise = 50p

* Phase 1: high during first half, with dead time
VPH1 ph1 0 PULSE(0 1 {dead} {trise} {trise} {T/2 - 2*dead} {T})

* Phase 2: high during second half, with dead time
VPH2 ph2 0 PULSE(0 1 {T/2 + dead} {trise} {trise} {T/2 - 2*dead} {T})
```

**Clock Assignment:**
```text
Master data clock  = PH1
Master hold clock  = PH2
Slave data clock   = PH2
Slave hold clock   = PH1
```

**Probing Checklist:**
1. Plot `V(ph1)` and `V(ph2)` — confirm dead time where both are low
2. Probe master data current and slave data current — should never conduct simultaneously
3. Plot differential outputs: `V(M_OUTP) - V(M_OUTN)` and `V(S_OUTP) - V(S_OUTN)`
4. Confirm `S_OUT` period = 2 × clock period

---

### Fix 13.18: Deprecate Old CML Divider Netlist Template

**Symptom:** Old generated CML netlists fail silently or produce garbage.

**Root Cause:** The old template has multiple issues:
- Load resistors to VSS instead of VDD
- Clock inputs biased with DC VDD/2
- No proper non-overlapping master/slave clocking
- No proper differential feedback
- Diode-connected or incorrectly connected HBT devices

**Fix:** Use the validated standalone latch plus explicit non-overlapping master/slave phasing. Do not use the old template.

---

## 14. Vivado FPGA Synthesis — Complete Guide & Pitfalls (CRITICAL)

### 14.1 Installation & License
**Vivado Path:** `D:\softwares\AMD\2026.1\Vivado\bin\vivado.bat`
**License:** Vivado Design Suite BASIC (expires 24-Jun-2027)
**CRITICAL LICENSE LIMITATION:** The BASIC license only supports Artix-7 and Zynq-7000 devices. It does NOT support UltraScale+ (Alveo U25/U280). For UltraScale+ deployment, you need a paid license.

### 14.2 The Path-with-Spaces Problem (CRITICAL)
**Symptom:** Vivado synthesis fails with cryptic errors.
**Root Cause:** Vivado's Tcl interpreter splits paths at spaces.
**THE ONLY RELIABLE FIX:** Create a symlink to a path WITHOUT spaces:
```powershell
cmd /c "mklink /D C:\RadarGateway `"D:\Desktop\Vault\03 Projects\Ganeshas projects\RadarGateway`""
```
**ALWAYS run Vivado from the symlink path.**

### 14.3 Vivado Tcl Synthesis Script — Correct Template
```tcl
read_verilog -sv "C:/RadarGateway/rtl/top/radar_gateway_top.sv"
set_property top radar_gateway_top [get_filesets sources_1]
read_xdc "C:/RadarGateway/constraints/radar_gateway_timing.xdc"
synth_design -top radar_gateway_top -part xc7a200tfbg484-2 -mode out_of_context
opt_design -verbose
report_utilization -file "C:/RadarGateway/reports/utilization.rpt"
report_timing_summary -file "C:/RadarGateway/reports/timing.rpt"
write_checkpoint -force "C:/RadarGateway/checkpoints/post_synth.dcp"
```

---

## 15. Simulator Selection Guide

| Simulator | Works For | Use When |
|-----------|-----------|----------|
| **ngspice** | MOSFET circuits (sg13_lv_nmos) | Transient simulation, frequency extraction |
| **Xyce** | HBT circuits (npn13G2) | HBT VCOs, dividers, bipolar circuits |
| **Neither** | — | Xyce is blocked on IHP MOSFETs; ngspice can't do HBT RF |

### SiliconForge Integration

The SiliconForge framework (`siliconforge/`) provides Python wrappers for both simulators:
- `siliconforge/solvers/spice_runner.py` — ngspice via WSL
- `siliconforge/solvers/xyce_runner.py` — Xyce via WSL

Use `run_9stage_pipeline.py` for automated phase noise extraction.

---

## 16. Adaptive ISF Calibration (CRITICAL)

The phase_gating.v module uses HARDCODED zero-sensitivity bins — this is WRONG. PVT variations, aging, and per-chip variation make static values useless.

**The correct approach:** `adaptive_icalibration.v` — real-time ISF measurement and adaptive gating.

### How It Works
1. **Startup Calibration:** Inject charge pulses at each of 8 phase bins, measure phase shift via TDC
2. **ISF Estimation:** Accumulate phase error measurements, build ISF histogram
3. **Adaptive Gating:** Find two bins with minimum ISF, gate digital transitions to those bins
4. **Temperature Tracking:** Auto-recalibrate when temperature changes >5°C
5. **Background Tracking:** Continuous ISF update during normal operation

### Files
- `digital/rtl/adaptive_isf_calibration.v` — Verilog-2005, Yosys-compatible
- `digital/rtl/isf_perturbation_injector.sv` — Charge pulse injection
- `digital/rtl/tdc_phase_error.sv` — TDC for phase error measurement

### Integration
```
VCO → TDC → adaptive_isf_calibration → phase_gated AFC/AAC/ADPLL
              ↑
              └── isf_perturbation_injector (calibration mode only)
```

---

## 17. Python Environment

**Always use `python3`** (not `python`). This environment uses NumPy 2.x where `np.trapz` has been removed — use `np.trapezoid` instead.

---

## 17. Dynamic Netlist Patching (CRITICAL)

The legacy `.cir` files in the repository contain outdated IHP model syntax and hardcoded Windows paths that crash WSL. Your Python wrappers **must** perform the following regex replacements on the raw string before execution:
1.  **PDK Path Injection:** Rewrite `.lib "*cornerHBT.lib" <corner>` to `.lib "/tmp/ihp_sg13g2/libs.tech/ngspice/models/cornerHBT.lib" hbt_typ`
2.  **Legacy Subcircuit Fix:** Rewrite transistor instances from `Q<num>` to `X<num>` (e.g., `re.sub(r'^Q(\d+)', r'X\1', content, flags=re.MULTILINE)`)
3.  **Model Renaming:** Rewrite the legacy `npn13G2` identifier to `npn13G2l`
4.  **Strip Invalid Directives:** Remove lines starting with `.fft` and wipe any existing `.control ... .endc` blocks before appending your new testbench control logic

---

## 18. SiliconForge — Phase Noise Extraction Framework

## 18. SiliconForge — Phase Noise Extraction Framework

SiliconForge is a Python framework for oscillator phase noise characterization located at:
```
ppv guided clock generation adpll/siliconforge/
```

### 18.1 What It Does

| Capability | Status | Method |
|------------|--------|--------|
| Frequency measurement | Verified | Zero-crossing detection on SPICE transient |
| Phase noise (analytical) | Verified | Leeson model with circuit parameters |
| **Phase noise (SPICE-level)** | **Verified** | **PSS + perturbation + device noise integration** |
| PPV/ISF extraction | Verified | Adjoint (left eigenvector) method |
| Jitter calculation | Verified | Canonical integration of L(f) |
| Verilog-A generation | Verified | Behavioral model from extracted parameters |
| PVT corner sweep | Verified | TT/FF/SS corner simulation |

### 18.2 Environment Setup

Before using SiliconForge, the PDK must be accessible. Run these commands in WSL:

```bash
# Create symlink to PDK (avoids space-in-path issues)
wsl bash -c "ln -sf '/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/ppv guided clock generation adpll/vco/IHP-Open-PDK-0.3.0/ihp-sg13g2' /tmp/ihp_sg13g2"

# Create OSDI directories
wsl bash -c "mkdir -p /tmp/ihp_sg13g2/libs.tech/ngspice/va/{psp103,psp103_nqs,mosvar,r3_cmc}"

# Copy pre-compiled OSDI files
wsl bash -c "cp /tmp/ihp_sg13g2/libs.tech/verilog-a/psp103/psp103.osdi /tmp/ihp_sg13g2/libs.tech/ngspice/va/psp103/"
wsl bash -c "cp /tmp/ihp_sg13g2/libs.tech/verilog-a/mosvar/mosvar.osdi /tmp/ihp_sg13g2/libs.tech/ngspice/va/mosvar/"
wsl bash -c "cp /tmp/ihp_sg13g2/libs.tech/verilog-a/r3_cmc/r3_cmc.osdi /tmp/ihp_sg13g2/libs.tech/ngspice/va/r3_cmc/"

# Compile psp103_nqs.osdi (not pre-compiled in PDK)
wsl bash -c "cd '/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/ppv guided clock generation adpll/vco/IHP-Open-PDK-0.3.0/ihp-sg13g2/libs.tech/verilog-a/psp103' && openvaf psp103_nqs.va"
wsl bash -c "cp '/mnt/d/Desktop/Vault/03 Projects/Ganeshas projects/ppv guided clock generation adpll/vco/IHP-Open-PDK-0.3.0/ihp-sg13g2/libs.tech/verilog-a/psp103/psp103_nqs.osdi' /tmp/ihp_sg13g2/libs.tech/ngspice/va/psp103_nqs/"
```

**Verify setup:**
```bash
wsl bash -c "ls -la /tmp/ihp_sg13g2/libs.tech/ngspice/va/psp103_nqs/psp103_nqs.osdi"
# Should show ~997KB file. If 0 bytes, compilation failed.
```

### 18.3 Regression Suite (19 circuits)

Run all circuits through the verification pipeline:

```bash
cd siliconforge
python -c "from siliconforge.solvers.regression import RegressionRunner; RegressionRunner(use_spice=True).run_suite()"
```

Run specific circuits:
```bash
python -c "from siliconforge.solvers.regression import RegressionRunner; RegressionRunner(use_spice=True).run_suite(['nmos_oscillator', 'lc_vco', 'ring_oscillator'])"
```

List available circuits:
```bash
python -c "from siliconforge.solvers.regression import RegressionRunner; RegressionRunner().list_circuits()"
```

**Output:** `regression_results/` directory with JSON files per circuit + `regression_report.json` summary.

**Verified circuits:**
- 5 MOSFET oscillators (ngspice): 10.2 GHz, 3.5 GHz, 10.9 GHz, 6.7 GHz + HBT 10.4 GHz
- 1 HBT 30 GHz VCO (Xyce): 38.2 GHz
- 3 PVT corners (ngspice): TT, FF, SS
- 1 negative test (expected FAIL)

### 18.4 9-Stage Pipeline

Run the complete extraction flow on the 30 GHz VCO benchmark:

```bash
cd siliconforge/automation/rf_pipeline
python run_9stage_pipeline.py
```

**Output:** `pipeline_results/ngspice_pn_report.json` with all extracted metrics.

**Stages:**
1. **PSS** — Frequency extraction (Xyce/ngspice transient)
2. **PPV Direct** — Monodromy matrix (λ₂ < 1 verified)
3. **PPV Suite** — ISF extraction (adjoint method)
4. **Phase Noise** — Leeson model (analytical)
5. **Phase Noise** — PSS + Perturbation (SPICE-level, device noise)
6. **Jitter** — RMS TIE integration
7. **Verilog-A** — Behavioral model generation
8. **Adjoint** — PPV/ISF validation
9. **PVT** — Corner sweep

### 18.5 Standalone Wrappers

#### 18.5.1 ngspice Transient Simulation

```python
from siliconforge.solvers.spice_runner import run_ngspice, extract_frequency_from_meas

# Run simulation
stdout, stderr = run_ngspice("path/to/circuit.cir", pdk_root="/tmp")

# Extract frequency
freq = extract_frequency_from_meas(stdout)
print(f"Frequency: {freq/1e9:.4f} GHz")
```

#### 18.5.2 Xyce Transient Simulation (HBT circuits)

```python
from siliconforge.solvers.xyce_runner import run_hbt_vco_simulation

result = run_hbt_vco_simulation("path/to/hbt_vco.cir")
print(f"Frequency: {result['frequency_hz']/1e9:.4f} GHz")
print(f"VPP: {result['vpp']:.3f} V")
```

#### 18.5.3 Phase Noise (Leeson Model)

```python
from siliconforge.solvers.pnoise_analysis import leeson_phase_noise

# Parameters
f0 = 10.21e9       # Carrier frequency [Hz]
v_swing = 0.6      # Peak amplitude [V]
Q = 10.0           # Tank quality factor
NF_db = 6.0        # Noise figure [dB]

# Compute at specific offset
L = leeson_phase_noise(f0, 1e6, v_swing, Q, noise_figure_db=NF_db)
print(f"L(1MHz) = {L:.1f} dBc/Hz")
```

#### 18.5.4 Phase Noise (PSS + Perturbation)

```python
from siliconforge.solvers.pnoise_spice import run_pnoise_analysis

result = run_pnoise_analysis(
    "path/to/netlist.cir",
    f0=38.19e9,      # Carrier frequency [Hz]
    vrms=0.78,       # RMS amplitude [V]
    f_start_hz=100,  # Start offset [Hz]
    f_stop_hz=100e6  # Stop offset [Hz]
)

# Results
offsets = result["offset_freqs_hz"]
pn_db = result["phase_noise_dbch"]
n_sources = result["noise_sources"]
```

#### 18.5.5 Jitter Integration

```python
from siliconforge.solvers.jitter import integrate_jitter_single_point, integrate_jitter_from_pn_curve

# Single-point (analytical)
result = integrate_jitter_single_point(
    pn_dbhz=-125.0,  # Phase noise at offset [dBc/Hz]
    f_offset=1e6,    # Offset frequency [Hz]
    f0=38.19e9,      # Carrier [Hz]
    f_min=10e3,      # Lower bound [Hz]
    f_max=19e9       # Upper bound [Hz]
)
print(f"RMS TIE: {result['tie_rms_fs']:.2f} fs")

# From curve (numerical integration)
result = integrate_jitter_from_pn_curve(
    offsets_hz=[1e3, 10e3, 100e3, 1e6, 10e6],
    pn_dbhz=[-80, -100, -120, -125, -130],
    f0=38.19e9,
    f_min=10e3,
    f_max=19e9
)
```

#### 18.5.6 Design Configuration

```python
from siliconforge.solvers.design_config import load_config, adpll_config, lc_vco_config

# Load from YAML
config = load_config("my_vco.yaml")

# Use presets
config = adpll_config()           # 10.25 GHz ADPLL
config = lc_vco_config(f0_ghz=5.0)  # Generic LC VCO

# Resolve auto-references
config.resolve_references()

# Access parameters
print(config.pss.fundamental_frequency)
print(config.jitter.fmin_hz)
```

**YAML format:**
```yaml
design:
  name: my_vco
  pdk: ihp_sg13g2
  simulator: ngspice

pss:
  fundamental_frequency: auto
  convergence_tolerance: 1e-9

jitter:
  fmin_hz: 10000.0
  fmax_hz: 1000000000.0
  integration_method: curve

parameters:
  f0: 10.25e9
  Q: 10.0
```

### 18.6 Adding New Circuits

1. Create your SPICE netlist (use `/tmp/ihp_sg13g2` for PDK paths)
2. Add entry to `CANONICAL_CIRCUITS` in `siliconforge/solvers/regression.py`:
```python
"my_vco": {
    "name": "my_vco",
    "description": "My custom VCO",
    "f0_nominal_hz": 5.0e9,
    "vdd": 1.2,
    "expected_f0_range_hz": (4.5e9, 5.5e9),
    "category": "oscillator",  # or "oscillator_xyce" for HBT
    "netlist_path": "path/to/my_vco.cir",
},
```
3. Run: `RegressionRunner(use_spice=True).run_suite(['my_vco'])`

### 18.7 Understanding Results

**Regression report format (`regression_report.json`):**
```json
{
  "suite_status": "PASS",
  "summary": {"total": 19, "pass": 18, "fail": 0, "expected_fail": 1},
  "circuit_results": [
    {"design": "nmos_oscillator", "status": "PASS", "f0_ghz": 10.2145, "jitter_fs": 378.8}
  ]
}
```

**Individual circuit result (`regression_results/<name>_result.json`):**
```json
{
  "schema_version": "1.0.0",
  "design": {"name": "nmos_oscillator", "pdk": "ihp_sg13g2", "simulator": "ngspice"},
  "pss": {"converged": true, "frequency_hz": 10214500000.0},
  "jitter": {"rms_tie_fs": 378.8, "f0_hz": 10214500000.0, "fmin_hz": 10000.0, "fmax_hz": 1000000000.0},
  "overall_status": "PASS"
}
```

### 18.8 Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "file too short" for OSDI | `psp103_nqs.osdi` not compiled | Run openvaf compilation (Section 18.2) |
| "WSL not found" error | Running from WSL directly | Code auto-detects; ensure `/mnt/WSL` exists |
| Oscillator doesn't converge | Missing startup kick | Add `I_kick out_p out_n PWL(0 0 1p 1m 2p 0)` |
| Frequency = 0 | Wrong output node name | Check netlist for `out_p`/`out_n` names |
| Phase noise = -300 dB | ISF scaling too small | Check `c_total_f` parameter matches tank cap |
| Xyce "unrecognized symbols" | Missing vbic params | Add all 9 `.param vbic_* = 1.0` lines |

### 18.9 Key Files Reference

| File | Purpose | When to Use |
|------|---------|-------------|
| `siliconforge/solvers/spice_runner.py` | ngspice/WSL interface | MOSFET transient simulation |
| `siliconforge/solvers/xyce_runner.py` | Xyce interface | HBT transient simulation |
| `siliconforge/solvers/pnoise_analysis.py` | Leeson phase noise model | Quick analytical estimate |
| `siliconforge/solvers/pnoise_spice.py` | PSS + perturbation phase noise | SPICE-level accuracy |
| `siliconforge/solvers/ppv_eigenanalysis.py` | PPV/ISF extraction | Floquet analysis |
| `siliconforge/solvers/jitter.py` | Jitter integration | TIE/phase jitter from L(f) |
| `siliconforge/solvers/regression.py` | 19-circuit test suite | Batch verification |
| `siliconforge/solvers/design_config.py` | YAML/JSON config | Parameter management |
| `siliconforge/solvers/schema.py` | Canonical result format | JSON output standard |
| `siliconforge/automation/rf_pipeline/run_9stage_pipeline.py` | Full pipeline | End-to-end extraction |
| `siliconforge/automation/rf_pipeline/run_ngspice_pipeline.py` | 4-stage pipeline | Quick ngspice-only flow |

### 18.10 PVT Corner Netlists

Located at: `dual_band_radar_soc/reruns/30ghz_vco/`
- `vco_pvt_TT_27C_NomV.cir` — Typical-Typical, 27C
- `vco_pvt_FF_m40C_HighV.cir` — Fast-Fast, -40C
- `vco_pvt_SS_125C_LowV.cir` — Slow-Slow, 125C

Located at: `dual_band_radar_soc/benchmarks/01_standalone_blocks/`
- `30ghz/vco/vco_30ghz_standalone.cir` — 30 GHz HBT VCO (Xyce)
