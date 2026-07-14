// ==============================================================================
// AFC Engine — Automatic Frequency Calibration
// Binary search across 32 varactor bands to find target frequency
// ==============================================================================

module afc_engine #(
    parameter int CAP_BITS     = 5,
    parameter int REF_CYCLES   = 64,    // Reference cycles per measurement window
    parameter int TARGET_RATIO = 205    // f_vco / f_ref = 10.25G / 50M = 205
)(
    input  logic       clk_ref,       // 50 MHz reference clock
    input  logic       clk_vco_div,   // VCO output divided by N (should match clk_ref when locked)
    input  logic       rst_n,
    input  logic       enable,
    output logic [CAP_BITS-1:0] band_select,
    output logic       locked
);

    typedef enum logic [2:0] {
        S_IDLE,
        S_CLEAR,
        S_COUNT,
        S_COMPARE,
        S_NEXT_BIT,
        S_DONE
    } state_t;

    state_t state;

    logic [CAP_BITS-1:0] code;
    logic [$clog2(REF_CYCLES+1)-1:0] ref_cnt;
    logic [$clog2(TARGET_RATIO * REF_CYCLES + 1)-1:0] vco_cnt;
    logic [2:0] bit_idx;
    logic lock_detect;

    // Synchronize clk_vco_div into clk_ref domain
    logic vco_div_sync_0, vco_div_sync_1, vco_div_edge;
    always_ff @(posedge clk_ref or negedge rst_n) begin
        if (!rst_n) begin
            vco_div_sync_0 <= 0;
            vco_div_sync_1 <= 0;
        end else begin
            vco_div_sync_0 <= clk_vco_div;
            vco_div_sync_1 <= vco_div_sync_0;
        end
    end
    assign vco_div_edge = vco_div_sync_0 & ~vco_div_sync_1;

    // Target count: how many VCO edges we expect in REF_CYCLES reference periods
    localparam int EXPECTED_VCO_COUNT = TARGET_RATIO * REF_CYCLES;
    // Tolerance band: ±2% of expected
    localparam int TOL = EXPECTED_VCO_COUNT / 50;

    always_ff @(posedge clk_ref or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            code        <= '0;
            band_select <= '0;
            ref_cnt     <= '0;
            vco_cnt     <= '0;
            bit_idx     <= CAP_BITS - 1;
            lock_detect <= 0;
            locked      <= 0;
        end else begin
            case (state)
                S_IDLE: begin
                    locked <= lock_detect;
                    if (enable && !lock_detect) begin
                        code    <= '0;
                        bit_idx <= CAP_BITS - 1;
                        state   <= S_CLEAR;
                    end
                end

                S_CLEAR: begin
                    // Set the current bit under test
                    code[bit_idx] <= 1'b1;
                    band_select   <= code | (1 << bit_idx);
                    ref_cnt       <= '0;
                    vco_cnt       <= '0;
                    state         <= S_COUNT;
                end

                S_COUNT: begin
                    if (vco_div_edge)
                        vco_cnt <= vco_cnt + 1;

                    if (ref_cnt >= REF_CYCLES - 1) begin
                        state <= S_COMPARE;
                    end else begin
                        ref_cnt <= ref_cnt + 1;
                    end
                end

                S_COMPARE: begin
                    // If VCO is too slow (count < target), frequency is below target
                    // → keep the bit set (adds capacitance, but search polarity depends on design)
                    // For a varactor VCO: more cap → lower freq. So if too slow, clear the bit.
                    if (vco_cnt < EXPECTED_VCO_COUNT - TOL) begin
                        // VCO too slow → clear this cap bit to raise frequency
                        code[bit_idx] <= 1'b0;
                    end
                    // else keep bit set (VCO too fast, add cap to slow down)
                    state <= S_NEXT_BIT;
                end

                S_NEXT_BIT: begin
                    if (bit_idx == 0) begin
                        band_select <= code;
                        lock_detect <= 1;
                        state       <= S_DONE;
                    end else begin
                        bit_idx <= bit_idx - 1;
                        state   <= S_CLEAR;
                    end
                end

                S_DONE: begin
                    locked      <= 1;
                    band_select <= code;
                    if (!enable) begin
                        lock_detect <= 0;
                        state       <= S_IDLE;
                    end
                end
            endcase
        end
    end

endmodule
