// ==============================================================================
// AAC Engine — Automatic Amplitude Calibration
// 6-bit SAR-style bias current control for VCO amplitude regulation
// ==============================================================================

module aac_engine #(
    parameter int BIAS_BITS    = 6,
    parameter int SETTLE_WAIT  = 32,   // Clocks to wait after each DAC step
    parameter int DEBOUNCE     = 3     // Required consecutive samples before decision
)(
    input  logic       clk,
    input  logic       rst_n,
    input  logic       enable,
    input  logic       amp_high,       // Comparator: amplitude > target
    input  logic       amp_low,        // Comparator: amplitude < target
    output logic [BIAS_BITS-1:0] bias_control,
    output logic       settled
);

    typedef enum logic [2:0] {
        S_IDLE,
        S_SETTLE,
        S_SAMPLE,
        S_DECIDE,
        S_UPDATE,
        S_LOCKED
    } state_t;

    state_t state;

    logic [BIAS_BITS-1:0] code;
    logic [$clog2(SETTLE_WAIT+1)-1:0] wait_cnt;
    logic [$clog2(DEBOUNCE+1)-1:0] high_cnt, low_cnt;
    logic [2:0] bit_idx;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= S_IDLE;
            code         <= {1'b1, {(BIAS_BITS-1){1'b0}}};  // Start at midpoint
            bias_control <= {1'b1, {(BIAS_BITS-1){1'b0}}};
            wait_cnt     <= '0;
            high_cnt     <= '0;
            low_cnt      <= '0;
            bit_idx      <= BIAS_BITS - 1;
            settled      <= 0;
        end else begin
            case (state)
                S_IDLE: begin
                    settled <= 0;
                    if (enable) begin
                        code    <= {1'b1, {(BIAS_BITS-1){1'b0}}};
                        bit_idx <= BIAS_BITS - 1;
                        state   <= S_SETTLE;
                    end
                end

                S_SETTLE: begin
                    // Wait for analog settling after DAC change
                    bias_control <= code;
                    if (wait_cnt >= SETTLE_WAIT - 1) begin
                        wait_cnt <= '0;
                        high_cnt <= '0;
                        low_cnt  <= '0;
                        state    <= S_SAMPLE;
                    end else begin
                        wait_cnt <= wait_cnt + 1;
                    end
                end

                S_SAMPLE: begin
                    // Accumulate comparator readings with debounce
                    if (amp_high) high_cnt <= high_cnt + 1;
                    if (amp_low)  low_cnt  <= low_cnt + 1;

                    if ((high_cnt >= DEBOUNCE) || (low_cnt >= DEBOUNCE)) begin
                        state <= S_DECIDE;
                    end else if (wait_cnt >= SETTLE_WAIT - 1) begin
                        // Timeout — amplitude is in the window
                        state <= S_DECIDE;
                    end else begin
                        wait_cnt <= wait_cnt + 1;
                    end
                end

                S_DECIDE: begin
                    if (low_cnt >= DEBOUNCE) begin
                        // Amplitude too low → increase bias
                        code[bit_idx] <= 1'b1;
                    end else if (high_cnt >= DEBOUNCE) begin
                        // Amplitude too high → decrease bias
                        code[bit_idx] <= 1'b0;
                    end
                    // else: amplitude in window, keep current setting
                    state <= S_UPDATE;
                end

                S_UPDATE: begin
                    if (bit_idx == 0) begin
                        bias_control <= code;
                        state        <= S_LOCKED;
                    end else begin
                        bit_idx  <= bit_idx - 1;
                        // Pre-set next bit for binary search
                        code[bit_idx - 1] <= 1'b1;
                        wait_cnt <= '0;
                        state    <= S_SETTLE;
                    end
                end

                S_LOCKED: begin
                    settled      <= 1;
                    bias_control <= code;
                    if (!enable) begin
                        state <= S_IDLE;
                    end
                end
            endcase
        end
    end

endmodule
