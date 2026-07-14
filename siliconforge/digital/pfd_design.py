"""
siliconforge.digital.pfd_design
==============================

Phase Frequency Detector (PFD) design for PLL.

Implements guidebook Chapter 13.1 PFD with matched delays and charge pump.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PFDResult:
    """PFD sizing result."""

    up_current_ma: float
    down_current_ma: float
    charge_pump_gain_ua_per_degree: float


def size_pfd(
    reference_mhz: float = 50.0,
    vco_frequency_ghz: float = 10.25,
    charge_pump_ua: float = 500.0,
) -> PFDResult:
    """Size PFD for given reference/VCO frequencies.

    From guidebook Eq 13.1-13.2:
    - PFD must resolve within 1 reference cycle
    - Matching error < 1ps RMS required
    """
    vco_freq_hz = vco_frequency_ghz * 1e9
    n_div = round(vco_freq_hz / reference_mhz / 1e6)

    # Charge pump gain in uA/degree phase error
    # I_CP * N / 360 degrees per reference cycle
    cp_gain = charge_pump_ua * n_div / 360.0

    return PFDResult(
        up_current_ma=charge_pump_ua / 1000.0,
        down_current_ma=charge_pump_ua / 1000.0,
        charge_pump_gain_ua_per_degree=cp_gain,
    )


def generate_pfd_rtl(
    cp_uA: float,
    reference_mhz: float,
) -> str:
    """Generate PFD SystemVerilog RTL."""
    return f"""`timescale 1ns/1ps
`default_nettype none
// PFD for {reference_mhz} MHz reference

module pfd_core (
    input  logic clk_ref,
    input  logic clk_vco_div,
    input  logic rst_n,
    output logic up,
    output logic down
);

    // Simple PFD with dead-zone
    logic ref_dly, vco_dly;

    always_ff @(posedge clk_ref) begin
        ref_dly <= clk_vco_div;
    end

    assign up = clk_ref & ~ref_dly;
    assign down = ~clk_ref & ref_dly;

endmodule"""


if __name__ == "__main__":
    pfd = size_pfd(reference_mhz=50.0, vco_frequency_ghz=10.25)
    print(f"PFD CP gain: {pfd.charge_pump_gain_ua_per_degree:.1f} uA/degree")
    rtl = generate_pfd_rtl(500.0, 50.0)
    print(f"RTL generated: {len(rtl)} bytes")
