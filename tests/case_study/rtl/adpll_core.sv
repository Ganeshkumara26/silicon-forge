// ==============================================================================
// ADPLL Core — All-Digital Phase-Locked Loop
// Type-II with proportional-integral (PI) controller
// ==============================================================================

module adpll_core #(
    parameter int DIV_RATIO  = 205,     // N = f_vco / f_ref = 10.25G / 50M
    parameter int CTRL_WIDTH = 16,      // Frequency control word width
    parameter int PHASE_WIDTH = 24      // Phase accumulator width
)(
    input  logic       clk_ref,         // 50 MHz reference
    input  logic       clk_vco,         // VCO output (or divided version)
    input  logic       rst_n,
    input  logic       enable,
    output logic [CTRL_WIDTH-1:0] freq_control,
    output logic       pll_locked
);

    // -------------------------------------------------------------------------
    // Feedback divider: divide clk_vco by N
    // -------------------------------------------------------------------------
    logic [$clog2(DIV_RATIO+1)-1:0] div_cnt;
    logic clk_fb;

    always_ff @(posedge clk_vco or negedge rst_n) begin
        if (!rst_n) begin
            div_cnt <= '0;
            clk_fb  <= 0;
        end else begin
            if (div_cnt >= DIV_RATIO - 1) begin
                div_cnt <= '0;
                clk_fb  <= ~clk_fb;
            end else begin
                div_cnt <= div_cnt + 1;
            end
        end
    end

    // -------------------------------------------------------------------------
    // Synchronize feedback into reference domain
    // -------------------------------------------------------------------------
    logic fb_sync_0, fb_sync_1, fb_edge;
    always_ff @(posedge clk_ref or negedge rst_n) begin
        if (!rst_n) begin
            fb_sync_0 <= 0;
            fb_sync_1 <= 0;
        end else begin
            fb_sync_0 <= clk_fb;
            fb_sync_1 <= fb_sync_0;
        end
    end
    assign fb_edge = fb_sync_0 & ~fb_sync_1;

    // -------------------------------------------------------------------------
    // Phase detector: measure time difference between ref and feedback edges
    // -------------------------------------------------------------------------
    logic [PHASE_WIDTH-1:0] ref_phase, fb_phase;
    logic signed [PHASE_WIDTH-1:0] phase_error;
    logic ref_edge_d;

    always_ff @(posedge clk_ref or negedge rst_n) begin
        if (!rst_n) begin
            ref_phase  <= '0;
            ref_edge_d <= 0;
        end else begin
            ref_phase  <= ref_phase + 1;
            ref_edge_d <= 1;
        end
    end

    always_ff @(posedge clk_ref or negedge rst_n) begin
        if (!rst_n) begin
            fb_phase <= '0;
        end else if (fb_edge) begin
            fb_phase <= ref_phase;
        end
    end

    assign phase_error = signed'(ref_phase - fb_phase);

    // -------------------------------------------------------------------------
    // PI Loop Filter
    // -------------------------------------------------------------------------
    // Kp and Ki tuned for ωn = 1 MHz, ζ = 0.707
    // At 50 MHz ref: Kp = 8, Ki = 1 (shift-based for hardware efficiency)
    localparam int KP_SHIFT = 3;  // Kp = 1/8 → right shift 3
    localparam int KI_SHIFT = 8;  // Ki = 1/256 → right shift 8

    logic signed [CTRL_WIDTH-1:0] prop_term;
    logic signed [CTRL_WIDTH+8:0] integ_accum;
    logic signed [CTRL_WIDTH-1:0] integ_term;
    logic signed [CTRL_WIDTH-1:0] loop_output;

    // Clamp helper
    function automatic logic signed [CTRL_WIDTH-1:0] clamp(
        input logic signed [CTRL_WIDTH+8:0] val
    );
        if (val > $signed({1'b0, {(CTRL_WIDTH-1){1'b1}}}))
            return {1'b0, {(CTRL_WIDTH-1){1'b1}}};
        else if (val < $signed({1'b1, {(CTRL_WIDTH-1){1'b0}}}))
            return {1'b1, {(CTRL_WIDTH-1){1'b0}}};
        else
            return val[CTRL_WIDTH-1:0];
    endfunction

    always_ff @(posedge clk_ref or negedge rst_n) begin
        if (!rst_n) begin
            prop_term    <= '0;
            integ_accum  <= '0;
            integ_term   <= '0;
            loop_output  <= '0;
            freq_control <= {1'b1, {(CTRL_WIDTH-1){1'b0}}};  // Midpoint
        end else if (enable) begin
            // Proportional path
            prop_term <= phase_error >>> KP_SHIFT;

            // Integral path with accumulator
            integ_accum <= integ_accum + {{8{phase_error[PHASE_WIDTH-1]}}, phase_error};
            integ_term  <= clamp(integ_accum >>> KI_SHIFT);

            // Loop output
            loop_output  <= prop_term + integ_term;
            freq_control <= $unsigned(loop_output + $signed({1'b1, {(CTRL_WIDTH-1){1'b0}}}));
        end
    end

    // -------------------------------------------------------------------------
    // Lock detector: phase error within tolerance for N consecutive cycles
    // -------------------------------------------------------------------------
    localparam int LOCK_THRESHOLD = 4;
    localparam int LOCK_COUNT_REQ = 16;

    logic [$clog2(LOCK_COUNT_REQ+1)-1:0] lock_cnt;

    always_ff @(posedge clk_ref or negedge rst_n) begin
        if (!rst_n) begin
            lock_cnt   <= '0;
            pll_locked <= 0;
        end else if (enable) begin
            if (phase_error > -LOCK_THRESHOLD && phase_error < LOCK_THRESHOLD) begin
                if (lock_cnt >= LOCK_COUNT_REQ - 1)
                    pll_locked <= 1;
                else
                    lock_cnt <= lock_cnt + 1;
            end else begin
                lock_cnt   <= '0;
                pll_locked <= 0;
            end
        end else begin
            lock_cnt   <= '0;
            pll_locked <= 0;
        end
    end

endmodule
