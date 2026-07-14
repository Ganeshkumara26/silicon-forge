import numpy as np
import matplotlib.pyplot as plt

try:
    print("Loading data...")
    with open('../tb_v1_vco_xyce.cir.prn') as f:
        lines = f.readlines()

    start = 0
    for i, l in enumerate(lines):
        if l.startswith('Index'):
            start = i + 1
            break

    t, vp, vn = [], [], []
    for l in lines[start:]:
        try:
            p = l.split()
            if len(p) >= 4:
                t.append(float(p[1]))
                vp.append(float(p[2]))
                vn.append(float(p[3]))
        except:
            pass

    t = np.array(t) * 1e9  # ns
    vp = np.array(vp)
    vn = np.array(vn)

    # Plot the last 0.5 ns
    t_end_val = t[-1]
    mask = t > (t_end_val - 0.5)
    t_plot = t[mask]
    vp_plot = vp[mask]
    vn_plot = vn[mask]

    plt.style.use('dark_background')
    plt.figure(figsize=(10, 5), dpi=150)
    plt.plot(t_plot, vp_plot, color='#00ffcc', linewidth=2, label='V(out_p)')
    plt.plot(t_plot, vn_plot, color='#ff007f', linewidth=2, label='V(out_n)')

    plt.title('V1 Varactor VCO: Steady-State Transient Oscillation (10.25 GHz)',
              fontsize=14, pad=15, fontweight='bold', color='white')
    plt.xlabel('Time (ns)', fontsize=12, color='lightgrey')
    plt.ylabel('Voltage (V)', fontsize=12, color='lightgrey')
    plt.grid(True, alpha=0.2, color='gray')
    plt.legend(loc='upper right', facecolor='black', edgecolor='gray')

    plt.tight_layout()
    plt.savefig('v1_transient.png', facecolor='black')
    print("Saved v1_transient.png")

except Exception as e:
    print(f"Error: {e}")
