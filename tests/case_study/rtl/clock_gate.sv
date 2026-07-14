// ==============================================================================
// Clock Gate — Integrated Clock Gating (ICG) Cell
// Latch-based design to prevent glitches on gated output
// ==============================================================================

module clock_gate (
    input  logic clk_in,
    input  logic enable,
    input  logic test_mode,    // Bypass gating during scan test
    output logic clk_gated
);

    // Latch enable on negative edge of clock → prevents glitches
    logic en_latched;

    always_latch begin
        if (!clk_in)
            en_latched = enable | test_mode;
    end

    assign clk_gated = clk_in & en_latched;

endmodule
