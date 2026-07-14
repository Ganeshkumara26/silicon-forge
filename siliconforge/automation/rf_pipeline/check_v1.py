import numpy as np
import sys

try:
    with open('../tb_v1_vco_xyce.cir.prn') as f:
        lines = f.readlines()

    start = 0
    for i, l in enumerate(lines):
        if l.startswith('Index'):
            start = i + 1
            break

    t, v = [], []
    for l in lines[start:]:
        try:
            p = l.split()
            if len(p) >= 4:
                t.append(float(p[1]))
                v.append(float(p[2]) - float(p[3]))
        except:
            pass

    t = np.array(t)
    v = np.array(v)

    # Restrict to last 10%
    t_max = t[-1]
    mask = t > (t_max - 2e-9)
    t_end = t[mask]
    v_end = v[mask]

    vpp = np.max(v_end) - np.min(v_end)
    if vpp < 0.1:
        print(f"FAILED: Oscillator dead. Vpp = {vpp:.3f} V")
        sys.exit(1)

    crossings = np.where(np.diff(np.sign(v_end)) > 0)[0]

    if len(crossings) > 1:
        T_avg = (t_end[crossings[-1]] - t_end[crossings[0]]) / \
            (len(crossings)-1)
        f0 = 1/T_avg / 1e9
        print(
            f"SUCCESS: Oscillator alive. Vpp = {vpp:.3f} V, f0 = {f0:.3f} GHz")
    else:
        print("FAILED: Not enough crossings.")

except Exception as e:
    print(f"Error: {e}")
