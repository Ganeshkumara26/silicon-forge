"""
siliconforge.digital.divider_design
==================================

Integer-N divider design for PLL.

Implements guidebook Chapter 14 prescaler-based division.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PrescalerDesign:
    """Prescaler design container."""

    n_stages: int
    div_type: str = "EVEN"

    def power_estimate(self, mhz: float, vdd: float) -> float:
        """Estimate power consumption."""
        p_dyn = mhz * vdd * 0.5 * self.n_stages * 0.02
        return p_dyn


@dataclass
class DividerStageResult:
    """Single divider stage parameters."""

    n_type: int  # 1: divide-by-2, 2: divide-by-3/4, etc.
    delay_ps: float
    power_uw: float


def size_prescaler_stages(
    input_frequency_ghz: float = 10.25,
    target_division: int = 5,
) -> list[DividerStageResult]:
    """Size CML prescaler stages for high-frequency division.

    From guidebook: Prescaler must resolve within 1/(2*N*f_in) timing.
    For 10 GHz -> 2 GHz intermediate: need 1:2 divider first.
    """
    stages = []
    remaining = target_division

    while remaining > 1:
        if remaining >= 3:
            stages.append(DividerStageResult(
                n_type=3,
                delay_ps=10.0 * (input_frequency_ghz / 10.0),
                power_uw=50.0,
            ))
            remaining -= 3
        elif remaining == 2:
            stages.append(DividerStageResult(
                n_type=2,
                delay_ps=5.0 * (input_frequency_ghz / 10.0),
                power_uw=30.0,
            ))
            remaining = 1

    if target_division % 2 == 0 or target_division > 1:
        stages.append(DividerStageResult(
            n_type=1,
            delay_ps=3.0 * (input_frequency_ghz / 10.0),
            power_uw=20.0,
        ))

    return stages


def generate_divider_rtl(
    n_total: int,
    n_stages: int,
) -> str:
    """Generate integer-N divider RTL."""
    return f"""`timescale 1ns/1ps
`default_nettype none
// Integer-{n_total} divider with {n_stages} stages

module int_div_{n_total} (
    input  logic clk_in,
    input  logic rst_n,
    output logic clk_out
);

    // Prescaler stages
    logic q1, q2, q3;

    // Stage 1: divide-by-{n_total // 2}
    always_ff @(posedge clk_in) begin
        q1 <= ~q1;
    end

    // Stage 2: divide-by-2
    always_ff @(posedge q1) begin
        q2 <= ~q2;
    end

    assign clk_out = q2;

endmodule"""


if __name__ == "__main__":
    stages = size_prescaler_stages(10.25, 5)
    total_power = sum(s.power_uw for s in stages)
    print(f"Divider stages: {len(stages)}, total power: {total_power:.0f} uW")
