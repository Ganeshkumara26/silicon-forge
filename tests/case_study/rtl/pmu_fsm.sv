// ==============================================================================
// PMU FSM — Power Management Unit
// Controls clock domain selection, gating, and AAC mode based on workload
// ==============================================================================

module pmu_fsm (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [7:0] timing_slack,      // Slack from timing analysis (0=critical, 255=lots of slack)
    input  logic       perf_request,      // External performance boost request
    input  logic       pll_locked,        // PLL lock indicator
    output logic [1:0] div_sel,           // Divider domain select (0=÷1, 1=÷2, 2=÷4, 3=÷8)
    output logic [3:0] gate_enable,       // Per-domain clock gate enables
    output logic [1:0] aac_mode,          // AAC operating mode
    output logic [1:0] pmu_state_out      // Current state for debug
);

    typedef enum logic [1:0] {
        BOOST  = 2'b00,   // Max performance: ÷1, all domains active
        ACTIVE = 2'b01,   // Nominal: ÷2, most domains active
        IDLE   = 2'b10,   // Light workload: ÷4, reduced domains
        SLEEP  = 2'b11    // Standby: ÷8, minimal activity
    } pmu_state_t;

    pmu_state_t state;

    // Hysteresis thresholds to prevent rapid toggling
    localparam logic [7:0] BOOST_ENTER  = 8'd16;   // Enter BOOST when slack < 16
    localparam logic [7:0] BOOST_EXIT   = 8'd48;   // Exit BOOST when slack > 48
    localparam logic [7:0] ACTIVE_ENTER = 8'd64;
    localparam logic [7:0] IDLE_ENTER   = 8'd128;
    localparam logic [7:0] SLEEP_ENTER  = 8'd200;

    // Dwell timer: minimum time in each state before transition allowed
    logic [7:0] dwell_cnt;
    localparam logic [7:0] DWELL_MIN = 8'd32;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= ACTIVE;
            div_sel   <= 2'd1;
            gate_enable <= 4'b1111;
            aac_mode  <= 2'b01;
            dwell_cnt <= '0;
        end else if (!pll_locked) begin
            // If PLL unlocked, stay in ACTIVE and don't transition
            state       <= ACTIVE;
            div_sel     <= 2'd1;
            gate_enable <= 4'b1111;
            aac_mode    <= 2'b01;
            dwell_cnt   <= '0;
        end else begin
            if (dwell_cnt < DWELL_MIN) begin
                dwell_cnt <= dwell_cnt + 1;
            end else begin
                case (state)
                    BOOST: begin
                        if (!perf_request && timing_slack > BOOST_EXIT) begin
                            state     <= ACTIVE;
                            dwell_cnt <= '0;
                        end
                    end

                    ACTIVE: begin
                        if (perf_request || timing_slack < BOOST_ENTER) begin
                            state     <= BOOST;
                            dwell_cnt <= '0;
                        end else if (timing_slack > IDLE_ENTER) begin
                            state     <= IDLE;
                            dwell_cnt <= '0;
                        end
                    end

                    IDLE: begin
                        if (perf_request || timing_slack < ACTIVE_ENTER) begin
                            state     <= ACTIVE;
                            dwell_cnt <= '0;
                        end else if (timing_slack > SLEEP_ENTER) begin
                            state     <= SLEEP;
                            dwell_cnt <= '0;
                        end
                    end

                    SLEEP: begin
                        if (perf_request || timing_slack < IDLE_ENTER) begin
                            state     <= IDLE;
                            dwell_cnt <= '0;
                        end
                    end
                endcase
            end

            // Output mapping based on state
            case (state)
                BOOST: begin
                    div_sel     <= 2'd0;     // ÷1 (10.25 GHz)
                    gate_enable <= 4'b1111;  // All domains active
                    aac_mode    <= 2'b11;    // Max bias
                end
                ACTIVE: begin
                    div_sel     <= 2'd1;     // ÷2 (5.125 GHz)
                    gate_enable <= 4'b1111;  // All domains active
                    aac_mode    <= 2'b01;    // Nominal bias
                end
                IDLE: begin
                    div_sel     <= 2'd2;     // ÷4 (2.5625 GHz)
                    gate_enable <= 4'b0011;  // Only domains 0-1 active
                    aac_mode    <= 2'b00;    // Low bias
                end
                SLEEP: begin
                    div_sel     <= 2'd3;     // ÷8 (1.28125 GHz)
                    gate_enable <= 4'b0001;  // Only domain 0 active
                    aac_mode    <= 2'b00;    // Low bias
                end
            endcase
        end
    end

    assign pmu_state_out = state;

endmodule
