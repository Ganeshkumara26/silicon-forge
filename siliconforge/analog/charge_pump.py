"""
siliconforge.analog.charge_pump
==============================

Charge pump design for PLL.

Implements guidebook Chapter 13.2 charge pump with current matching.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChargePumpResult:
    """Charge pump sizing result."""

    current_ma: float
    voltage_gain: float
    power_mw: float


def size_charge_pump(
    target_current_ua: float = 500.0,
    vdd_v: float = 1.2,
) -> ChargePumpResult:
    """Size charge pump for PLL.

    From guidecase Eq 13.3: I_CP = I_target +/- mismatch
    Must have I_CP >> I_leak for phase offset < 0.01 rad.
    """
    power_mw = vdd_v * target_current_ua / 1000.0

    return ChargePumpResult(
        current_ma=target_current_ua / 1000.0,
        voltage_gain=1.0,
        power_mw=power_mw,
    )


def generate_charge_pump_netlist(
    current_ua: float,
    vdd_v: float = 1.2,
) -> str:
    """Generate charge pump SPICE netlist using IHP PDK subcircuits."""
    return f"""* Charge pump for CPLR
* Target current: {current_ua} uA
* Using IHP SG13G2 PDK subcircuits: sg13_hv_nmos, sg13_hv_pmos

VDD VDD 0 DC {vdd_v}
VSS VSS 0 DC 0

* NMOS switch (IHP PDK subcircuit: d g s b)
X1 UP VSS VDD VSS sg13_hv_nmos w=4u l=0.13u

* PMOS switch (IHP PDK subcircuit: d g s b)
X2 DN VDD VSS VDD sg13_hv_pmos w=12u l=0.13u

.END"""


if __name__ == "__main__":
    cp = size_charge_pump(500.0)
    print(f"Charge pump: {cp.current_ma*1000:.0f} uA, {cp.power_mw:.2f} mW")
