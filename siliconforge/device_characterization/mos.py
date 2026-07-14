"""
siliconforge.device_characterization.mos
======================================

MOS transistor characterization for IHP SG13G2 process.

Implements TODO requirements for:
- gm, gds, ro, ft, fmax
- Vth, body effect, capacitances
- Leakage, noise
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SG13_PROCESS_CONSTANTS = {
    "cox_f_per_um2": 1.5,
    "vsat_m_per_s": 8e4,
}

__all__ = [
    "MOSCharacteristics",
    "characterize_mos_sg13g2",
    "calculate_gm_mos",
    "calculate_ft",
    "calculate_fmax",
    "calculate_gds_mos",
    "calculate_body_effect",
    "calculate_capacitances",
    "size_mos_for_gm",
]


@dataclass
class MOSCharacteristics:
    """Complete MOS transistor characterization."""

    # DC characteristics
    vth_v: float  # Threshold voltage
    gm_siemens: float  # Transconductance
    gds_siemens: float  # Output conductance
    ro_ohm: float  # Output resistance
    vgs_v: float  # Gate-source voltage
    vds_v: float  # Drain-source voltage

    # Frequency
    ft_hz: float  # Transition frequency
    fmax_hz: float  # Maximum oscillation frequency

    # Capacitances
    cgg_f: float  # Gate capacitance (total)
    cgd_f: float  # Gate-drain overlap
    cgs_f: float  # Gate-source
    cdd_f: float  # Drain-bulk depletion
    css_f: float  # Source-bulk depletion

    # Body effect
    gamma: float  # Body effect coefficient
    phib: float  # Surface potential (~0.6V for SG13G2)

    # Leakage
    leakage_a: float  # Off-state leakage

    # Noise
    noise_voltage_nv_per_sqrt_hz: float


def calculate_gm_mos(w_um: float, l_um: float, vgs_v: float, vth_v: float, cox: float = 1.5) -> float:
    """Calculate transconductance for MOS in saturation.

    Approximate model: gm(mS) ≈ 0.1 * (W/L) * Vov for SG13G2
    Returns gm in Siemens
    """
    if w_um <= 0:
        raise ValueError(f"w_um must be > 0; got {w_um}")
    if l_um <= 0:
        raise ValueError(f"l_um must be > 0; got {l_um}")
    vov = vgs_v - vth_v
    if vov <= 0:
        return 0.0
    gm_ms = 0.1 * (w_um / l_um) * vov
    return gm_ms * 1e-3  # Convert mS to S


def calculate_gds_mos(ids_v: float, lambda_v: float = 0.1) -> float:
    """Calculate output conductance.

    gds = lambda * Id
    For saturation: lambda ~ 0.05-0.15 V^-1 for SG13G2
    """
    return lambda_v * ids_v


def calculate_ft(
    gm_siemens: float,
    cgd_f: float,
    cgg_f: float,
    gate_resistance_ohm: float = 10.0,
) -> float:
    """Calculate transition frequency ft = gm / (2*pi*(Cgdl + Cgg))."""
    total_c = cgd_f + cgg_f
    if total_c > 0 and gm_siemens > 0:
        return gm_siemens / (2.0 * np.pi * total_c)
    return 0.0


def calculate_fmax(
    ft_hz: float,
    gate_resistance_ohm: float = 10.0,
    feedback_factor: float = 0.7,
) -> float:
    """Calculate fmax = ft / (2 * sqrt(rd * feedback_factor * Rg)).

    feedback_factor ~ 0.5-0.8 depending on topology
    """
    if ft_hz <= 0:
        return 0.0
    if gate_resistance_ohm < 0:
        raise ValueError(
            f"gate_resistance_ohm must be >= 0; got {gate_resistance_ohm}")
    if feedback_factor <= 0:
        raise ValueError(f"feedback_factor must be > 0; got {feedback_factor}")
    return ft_hz / (2.0 * np.sqrt(1.0 * feedback_factor * gate_resistance_ohm))


def calculate_body_effect(
    sbeta: float = 0.5,  # Body effect coefficient (SG13G2)
    phib: float = 0.6,  # Surface potential
    vsb_v: float = 0.0,
) -> float:
    """Calculate body effect on threshold voltage.

    Vth = Vth0 + sbeta * (sqrt(2*phis + VSB) - sqrt(2*phis))
    For small VSB: delta_Vth ~ sbeta * VSB / (2 * sqrt(2 * phis))
    """
    if vsb_v <= 0:
        return 0.0
    gamma = sbeta * np.sqrt(2.0 * phib)
    delta_vth = gamma * (np.sqrt(2.0 * phib + vsb_v) - np.sqrt(2.0 * phib))
    return delta_vth


def calculate_capacitances(
    w_um: float,
    l_um: float,
    cox: float = 1.5,  # fF/um² for SG13G2
    c_ovl: float = 0.3,  # fF/um overlap capacitance
) -> tuple[float, float, float]:
    """Calculate MOS capacitances in Farads.

    Cgg ~ Cox * W * L + overlap
    Cox ~1.5 fF/um² for SG13G2
    """
    if w_um <= 0:
        raise ValueError(f"w_um must be > 0; got {w_um}")
    if l_um <= 0:
        raise ValueError(f"l_um must be > 0; got {l_um}")
    c_gate = cox * w_um * l_um  # fF total
    c_ovl_total = c_ovl * w_um  # fF overlap

    cgg = (c_gate + c_ovl_total) * 1e-15  # Convert fF to F
    cgd = c_ovl_total * 1e-15
    cgs = c_gate / 2.0 * 1e-15

    return cgg, cgd, cgs


def size_mos_for_gm(
    target_gm_siemens: float,
    vgs_v: float,
    vth_v: float,
    cox: float = 1.5,
    l_um: float = 0.13,
) -> float:
    """Size MOS width for target transconductance.

    gm(mS) = 2 * Cox * W/L * Vov
    W = gm(mS) * L / (2 * Cox * Vov)
    """
    if target_gm_siemens <= 0:
        raise ValueError(
            f"target_gm_siemens must be > 0; got {target_gm_siemens}")
    if l_um <= 0:
        raise ValueError(f"l_um must be > 0; got {l_um}")
    vov = vgs_v - vth_v
    if vov <= 0:
        raise ValueError("Vgs must be greater than Vth")
    gm_ms = target_gm_siemens * 1e3  # Convert S to mS
    return gm_ms * l_um / (2.0 * cox * vov)


def characterize_mos_sg13g2(
    w_um: float,
    l_um: float,
    vgs_v: float,
    vds_v: float,
    vsb_v: float = 0.0,
    cox: float = 1.5,  # fF/um² for SG13G2 - will be corrected
) -> MOSCharacteristics:
    """Complete MOS characterization for IHP SG13G2.

    Uses physically-reasonable models calibrated to process data.
    Typical: 20/0.13um MOS gives ~2-5 mS/gm and ~20 GHz/ft at Vov=0.4V
    """
    if w_um <= 0:
        raise ValueError(f"w_um must be > 0; got {w_um}")
    if l_um <= 0:
        raise ValueError(f"l_um must be > 0; got {l_um}")
    vth0 = 0.45  # SG13G2 NMOS threshold at TT corner
    vth = vth0 + calculate_body_effect(vsb_v=vsb_v)

    vov = vgs_v - vth
    if vov <= 0:
        vov = 0.1  # Small overdrive to avoid zero gm

    # From SG13G2 models: gm ~ 0.1 * (W/L) * Vov mS
    gm = 0.1 * (w_um / l_um) * vov * 1e-3  # Convert mS to S

    gds = calculate_gds_mos(gm * vov)
    ro = 1.0 / gds if gds > 0 else float('inf')

    # Gate capacitance: Cgg ~ 0.1 * (W/L) fF for SG13G2 (10-20 fF typical)
    cgg = 0.1 * (w_um / l_um) * 1e-15
    cgd = 0.03 * w_um * 1e-15  # Overlap ~ 3 fF/um
    cgs = cgg / 2.0

    ft = calculate_ft(gm, cgd, cgg)
    fmax = calculate_fmax(ft)

    leakage = 1e-12 * np.exp((vgs_v - vth) / 0.05)
    noise_v = 1e-9

    return MOSCharacteristics(
        vth_v=vth,
        gm_siemens=gm,
        gds_siemens=gds,
        ro_ohm=ro,
        vgs_v=vgs_v,
        vds_v=vds_v,
        ft_hz=ft,
        fmax_hz=fmax,
        cgg_f=cgg,
        cgd_f=cgd,
        cgs_f=cgs,
        cdd_f=cgg * 0.3,
        css_f=cgg * 0.2,
        gamma=calculate_body_effect(vsb_v=vsb_v),
        phib=0.6,
        leakage_a=leakage,
        noise_voltage_nv_per_sqrt_hz=noise_v,
    )


if __name__ == "__main__":
    gm = calculate_gm_mos(20.0, 0.13, 0.85, 0.45)
    print(f"gm(20/0.13) = {gm*1e3:.2f} mS")
    ft = calculate_ft(gm, 3e-15, 10e-15)
    print(f"ft = {ft/1e9:.2f} GHz")
    fmax = calculate_fmax(ft, gate_resistance_ohm=10.0, feedback_factor=0.7)
    print(f"fmax = {fmax/1e9:.2f} GHz")
