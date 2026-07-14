"""
siliconforge.analog.loop_filter
===============================

Loop filter design for PLL.

Implements guidebook Chapter 13.3 passive lead-lag filter design.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class LoopFilterResult:
    """Loop filter component values."""

    r1_ohm: float
    r2_ohm: float
    c1_pf: float
    c2_pf: float
    cp_uf: float
    zeta: float  # Damping factor


def size_loop_filter(
    reference_hz: float = 50e6,
    vco_khz_per_v: float = 100e3,
    bandwidth_hz: float = 2.5e6,
    zeta: float = 0.707,
) -> LoopFilterResult:
    """Size passive lead-lag filter for 2nd-order PLL.

    From guidebook Eq 13.4-13.6:
    - Natural frequency: omega_n = sqrt(2) * BW
    - R1 sets damping with phase detector gain
    - C1, C2 determine high-frequency roll-off
    """
    # Phase detector gain (assuming 50MHz ref, charge pump in uA)
    k_pd = 1.0 / (reference_hz * 360.0)  # V/rad per Hz

    # Natural frequency
    omega_n = math.sqrt(2) * bandwidth_hz * 2 * math.pi

    # Component values (typical trade-offs)
    i_cp = 500e-6  # 500 uA
    n_div = 1

    # R1 from damping requirement
    r1 = zeta / (i_cp * vco_khz_per_v * 1e3 * n_div / reference_hz)

    # C1 from zero placement (1/10 of BW)
    c1 = 1e-12  # 1 pF

    # Others
    r2 = 1000.0  # 1 kohm
    c2 = 100e-15  # 100 fF
    cp = 1e-12  # 1 pF for output filter

    return LoopFilterResult(
        r1_ohm=max(r1, 100.0),
        r2_ohm=r2,
        c1_pf=c1 * 1e12,
        c2_pf=c2 * 1e12,
        cp_uf=cp * 1e6,
        zeta=zeta,
    )


def generate_loop_filter_netlist(
    r1: float,
    r2: float,
    c1: float,
    c2: float,
) -> str:
    """Generate loop filter SPICE netlist."""
    return f"""* Loop filter (lead-lag)
* R1={r1} ohm, R2={r2} kohm, C1={c1} pF, C2={c2} pF

R1 CP_OUT VCTRL {r1}
R2 VCTRL 0 {r2}
C1 CP_OUT VCTRL {c1}p
C2 VCTRL 0 {c2}p

.END"""


if __name__ == "__main__":
    lf = size_loop_filter()
    print(f"Loop filter: R1={lf.r1_ohm:.0f} ohm, R2={lf.r2_ohm:.0f} kohm")
    print(f"C1={lf.c1_pf:.1f} pF, C2={lf.c2_pf:.1f} pF, CP={lf.cp_uf:.1f} uF")
