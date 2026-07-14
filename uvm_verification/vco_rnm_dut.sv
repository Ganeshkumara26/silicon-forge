// ==============================================================================
// VCO Real-Number Model (RNM) Device Under Test
// Parameters are dynamically aligned by generate_assets.py from characterization
// ==============================================================================

module vco_rnm_dut (
    input  logic clk,
    input  logic rst_n,
    input  real  v_tune,
    input  real  dt_jitter,
    output real  v_out
);

    // Internal state for phase accumulation
    real phase;
    
    // Physical constants — overwritten by generate_assets.py from characterization JSON
    localparam real F_0 = 10248776304.520353;  // 10.2488 GHz (from characterization)  // 10.2488 GHz (from characterization)
    localparam real K_VCO = 100000000.0;  // 100 MHz/V  // 100 MHz/V
    localparam real V_AMPLITUDE = 0.82;  // 0.820V p-p  // 0.820V p-p
    localparam real DC_OFFSET = 0.79;
    localparam real PI = 3.14159265359;
    localparam real TS = 1e-11; // Discrete simulation time step (10ps)

    // Startup blanking: suppress output for first few cycles after reset
    integer startup_cnt;
    localparam integer STARTUP_CYCLES = 5;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            phase <= 0.0;
            v_out <= DC_OFFSET;  // Initialize within SVA bounds, not 0.0
            startup_cnt <= 0;
        end else begin
            // Calculate instantaneous frequency: f_inst = f0 + Kvco * v_tune
            automatic real f_inst = F_0 + (K_VCO * v_tune);
            
            // Accumulate phase based on the discrete timestep and injected jitter
            phase <= phase + (2.0 * PI * f_inst * (TS + dt_jitter));
            
            if (startup_cnt < STARTUP_CYCLES) begin
                startup_cnt <= startup_cnt + 1;
                v_out <= DC_OFFSET;  // Hold at DC during startup
            end else begin
                // Calculate output voltage: centered at DC_OFFSET with V_AMPLITUDE swing
                v_out <= (V_AMPLITUDE / 2.0) * $sin(phase) + DC_OFFSET;
            end
        end
    end

endmodule
