import numpy as np
import matplotlib.pyplot as plt
import json
import os

plt.style.use('dark_background')
colors = {'out_p': '#00ffcc', 'out_n': '#ff007f', 'vtune': '#f0e68c'}

print("Loading data...")
# Load PPV data
with open('ppv_data.json', 'r') as f:
    ppv_data = json.load(f)

# Load Phase Noise data
with open('phase_noise_breakdown.json', 'r') as f:
    pn_data = json.load(f)

# Load Transient data
t_tran, vp, vn = [], [], []
with open('../tb_v1_vco_xyce.cir.prn', 'r') as f:
    lines = f.readlines()
    start = 0
    for i, l in enumerate(lines):
        if l.startswith('Index'):
            start = i + 1
            break
    for l in lines[start:]:
        try:
            p = l.split()
            if len(p) >= 4:
                t_tran.append(float(p[1]))
                vp.append(float(p[2]))
                vn.append(float(p[3]))
        except:
            pass

t_tran = np.array(t_tran)
vp = np.array(vp)
vn = np.array(vn)
mask = t_tran > (t_tran[-1] - 0.5e-9)
vp_ss = vp[mask]
vn_ss = vn[mask]

# 1. ISF Curves Plot
plt.figure(figsize=(10, 5), dpi=150)
T0 = ppv_data['T0']
for node in ['out_p', 'out_n', 'vtune']:
    if node in ppv_data['nodes']:
        phases = np.array(ppv_data['nodes'][node]['time'])
        # normalize phases to 0-1 (t/T0)
        norm_phases = phases / T0
        isf = np.array(ppv_data['nodes'][node]['isf'])
        # ISF values are very large (1e18), let's normalize them for plotting
        isf_norm = isf / np.max(np.abs(isf))

        # Sort by phase
        idx = np.argsort(norm_phases)

        plt.plot(norm_phases[idx], isf_norm[idx], '-o',
                 color=colors[node], linewidth=2, label=f'ISF: {node}')

plt.title('Stage 5-7: Phase Perturbation Vector (ISF) Extraction',
          fontsize=14, pad=15, fontweight='bold', color='white')
plt.xlabel(r'Normalized Phase ($\phi / 2\pi$)', fontsize=12, color='lightgrey')
plt.ylabel(r'Normalized ISF ($\Gamma$)', fontsize=12, color='lightgrey')
plt.grid(True, alpha=0.2)
plt.legend(facecolor='black')
plt.tight_layout()
plt.savefig('v1_isf_plot.png', facecolor='black')

# 2. Phase Portrait (Limit Cycle)
plt.figure(figsize=(6, 6), dpi=150)
plt.plot(vp_ss, vn_ss, color='#b366ff', linewidth=2)
plt.title('Stage 2: Non-Linear Limit Cycle (Phase Portrait)',
          fontsize=14, pad=15, fontweight='bold', color='white')
plt.xlabel('$V_{out,p}$ (V)', fontsize=12, color='lightgrey')
plt.ylabel('$V_{out,n}$ (V)', fontsize=12, color='lightgrey')
plt.grid(True, alpha=0.2)
plt.tight_layout()
plt.savefig('v1_limit_cycle.png', facecolor='black')

# 3. Phase Noise Breakdown (Pie Chart)
plt.figure(figsize=(8, 6), dpi=150)
labels = []
sizes = []
pie_colors = []
# Calculate contribution percentages from total_lin values
total = sum(entry['total_lin'] for entry in pn_data['breakdown'])
for entry in pn_data['breakdown']:
    labels.append(entry['node'])
    sizes.append(entry['total_lin'] / total * 100)
    pie_colors.append(colors.get(entry['node'], '#ffffff'))

if sizes:
    plt.pie(sizes, labels=labels, colors=pie_colors, autopct='%1.1f%%',
            startangle=140, textprops={'color': "w", 'weight': 'bold'})
    plt.title('Stage 8: Phase Noise Power Contribution (@ 1MHz)',
              fontsize=14, pad=15, fontweight='bold', color='white')
    plt.tight_layout()
    plt.savefig('v1_pn_pie.png', facecolor='black')

# 4. Flicker Upconversion Susceptibility
plt.figure(figsize=(8, 5), dpi=150)
nodes_bar = []
gamma_ratios = []
for entry in pn_data.get('breakdown', []):
    nodes_bar.append(entry['node'])
    gamma_ratios.append(entry['gamma_dc_ratio'])

if nodes_bar:
    bars = plt.bar(nodes_bar, gamma_ratios, color=[
                   colors.get(x, 'w') for x in nodes_bar], alpha=0.8)
    plt.axhline(y=0.5, color='r', linestyle='--', label='High Risk Threshold')
    plt.title(
        r'Stage 8: Flicker Noise Upconversion Susceptibility ($\Gamma_{dc}/\Gamma_{rms}$)', fontsize=14, pad=15, fontweight='bold', color='white')
    plt.ylabel('Ratio (Closer to 1 = Worse 1/f upconversion)',
               fontsize=12, color='lightgrey')
    plt.ylim(0, 1.1)
    plt.grid(True, axis='y', alpha=0.2)
    plt.legend(facecolor='black')

    # Add values on top of bars
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2.0, yval + 0.02,
                 f'{yval:.3f}', ha='center', va='bottom', color='white', fontweight='bold')

    plt.tight_layout()
    plt.savefig('v1_flicker_upconversion.png', facecolor='black')

print("All plots generated successfully.")
