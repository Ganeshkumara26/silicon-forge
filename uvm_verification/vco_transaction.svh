// ==============================================================================
// VCO UVM Sequence Item (Transaction)
// ==============================================================================

`ifndef VCO_TRANSACTION_SVH
`define VCO_TRANSACTION_SVH

import uvm_pkg::*;
`include "uvm_macros.svh"

class vco_transaction extends uvm_sequence_item;
    
    // Randomize the tuning voltage for sweeping constraints (computed in post_randomize)
    real v_tune;
    
    // The jitter injected by the sequence generator
    real dt_jitter;

    // Constrain the tuning voltage to a physically realistic range [0.0, 1.2V]
    // Note: $urandom provides integers, so we constrain a discrete integer and 
    // mathematically convert it to a real during post_randomize if needed,
    // or just rely on the driver/sequence to set it. For simplicity in the MVV,
    // we use a discrete representation.
    rand int v_tune_mv;
    constraint c_vtune {
        v_tune_mv inside {[0 : 1200]};
    }

    `uvm_object_utils_begin(vco_transaction)
        `uvm_field_real(v_tune, UVM_ALL_ON)
        `uvm_field_real(dt_jitter, UVM_ALL_ON)
    `uvm_object_utils_end

    function new(string name="vco_transaction");
        super.new(name);
    endfunction

    // Post-randomize hook to map the integer mV constraint to the real v_tune
    function void post_randomize();
        v_tune = real'(v_tune_mv) / 1000.0;
    endfunction

endclass

`endif // VCO_TRANSACTION_SVH
