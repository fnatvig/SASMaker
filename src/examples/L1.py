# ================================================ #
# TO REPRODUCE L3: python -B examples      
# ================================================ #

from sasmaker import Substation
from sasmaker.builder import snap_child_to_slot
from sasmaker.plotting import plot_one_line
from sasmaker.simulation import Simulation, sample_ieds, trigger_busbar_protection, trigger_ied_cb_trip, trigger_ied_cb_close
from sasmaker.util import generate_values_df, create_interfaces, spawn_script
from benign_switching import *
from attack_scheduler import *

import warnings
import sys
from scipy.sparse.linalg import MatrixRankWarning

warnings.filterwarnings("ignore", category=MatrixRankWarning)



substation={"A1": ('A',3), "A2": ('A',6), "A3": ('A',12), "A4": ('A',18),
            "B1": ('B',5), "B2": ('B',9), "B3": ('B',13), "B4": ('B',17),}

# key = str(sys.argv[1])
key = "B2"

family = substation[key][0]
numIEDs = substation[key][1]

# --- Substation ---
s = Substation(f"Substation {key} ({numIEDs} IEDs)")

if family == 'A': 
    bExt1 = s.add_busbar("Upstream HV network 1", vn_kv=20, x=4.0, y=1.0, draw_slots=1, ext_grid=True)
    b1   = s.add_busbar("20 kV bus section 1", vn_kv=20, x=1.0, y=0.0, draw_slots=2*numIEDs-3) 
    vgap = 0.4
    snap_child_to_slot(s, bExt1, b1, slot_idx=0, drop=vgap)
    s.add_ext_grid("S/S-1", bExt1)
    l1 = s.add_line("L1", bExt1, b1, length_km=0.5)
    cb1 = s.add_cb("CB-1", l1, side="to", closed=True)
    ct1 = s.add_ct("CT-1", l1, side="to")
    ied1 = s.add_ied("IED1", ct=ct1, cb=cb1); ied1.ptoc.pickup_ka = 20.0

    j = 0
    for i in range(1, numIEDs):
        bus = s.add_busbar(f"LV bus {i}", vn_kv=20, x=1.0, y=-1.0, draw_slots=1, draw_label=False)
        snap_child_to_slot(s, b1, bus, slot_idx=j)
        j = j+2

        line = s.add_line(f"L{i+1}", b1, bus, length_km=0.5)
        cb = s.add_cb(f"CB-{i+1}", line, side="from", closed=True)
        ct = s.add_ct(f"CT-{i+1}", line, side="from")
        ied = s.add_ied(f"IED{i+1}", ct=ct, cb=cb)
        s.add_load(f"Feeder {i}", bus,   p_mw=15, q_mvar=10)
elif family == 'B':
    xgap = 1.0
    if numIEDs == 9:
        xgap = 2
    elif numIEDs == 13:
        xgap = 2.5
    elif numIEDs == 17:
        xgap = 3.5
    bExt1 = s.add_busbar("Upstream HV network 1", vn_kv=20, x=4.0, y=1.0, draw_slots=1, ext_grid=True)
    bExt2 = s.add_busbar("Upstream HV network 2", vn_kv=20, x=4.0+xgap, y=1.0, draw_slots=1, ext_grid=True)
    numIEDperBusbar = (numIEDs-3)/2
    b1   = s.add_busbar("20 kV bus section 1", vn_kv=20, x=1.0, y=0.0, draw_slots=2*numIEDs-(7+2*numIEDperBusbar))
    b2   = s.add_busbar("20 kV bus section 2", vn_kv=20, x=1.0, y=0.0, draw_slots=2*numIEDs-(7+2*numIEDperBusbar))

    vgap = 0.4
    snap_child_to_slot(s, bExt1, b1, slot_idx=0, drop=vgap)
    snap_child_to_slot(s, bExt2, b2, slot_idx=0, drop=vgap)
    s.add_ext_grid("S/S-1", bExt1)
    s.add_ext_grid("S/S-2", bExt2)
    bl1 = s.add_buslink("BL1", b1, b2)
    cb3 = s.add_cb_buslink("CB-3", bl1, closed=False)
    ct3 = s.add_ct_buslink("CT-3", bl1, side="from")
    l1 = s.add_line("L1", bExt1, b1, length_km=0.5)
    l2 = s.add_line("L2", bExt2, b2, length_km=0.5)
    cb1 = s.add_cb("CB-1", l1, side="to", closed=True)
    cb2 = s.add_cb("CB-2", l2, side="to", closed=True)
    ct1 = s.add_ct("CT-1", l1, side="to")
    ct2 = s.add_ct("CT-2", l2, side="to")
    ied1 = s.add_ied("IED1", ct=ct1, cb=cb1); ied1.ptoc.pickup_ka = 10.0
    ied2 = s.add_ied("IED2", ct=ct2, cb=cb2); ied2.ptoc.pickup_ka = 10.0
    ied3 = s.add_ied("IED3", ct=ct3, cb=cb3); ied3.ptoc.pickup_ka = 10.0
    
    j = 0
    n = 0
    parent = b1
    for i in range(3, numIEDs):
        bus = s.add_busbar(f"LV bus {i}", vn_kv=20, x=1.0, y=-1.0, draw_slots=1, draw_label=False)
        snap_child_to_slot(s, parent, bus, slot_idx=j)
        j = j+2
        n = n+1
        line = s.add_line(f"L{i+1}", parent, bus, length_km=0.5)
        cb = s.add_cb(f"CB-{i+1}", line, side="from", closed=True)
        ct = s.add_ct(f"CT-{i+1}", line, side="from")
        ied = s.add_ied(f"IED{i+1}", ct=ct, cb=cb)
        s.add_load(f"Feeder {n}", bus,   p_mw=15, q_mvar=10)

        if n < (numIEDs-3)/2:
            parent = b1
        elif n == (numIEDs-3)/2:
            parent = b2
            j=0

# --- simulation ---
sim_len = 1200

sim = Simulation("step load", t_end=sim_len, dt=1.0, vary_loads=True, vary_loads_every=180, vary_loads_min_gap=90, seed=12) # "test"=seed 12 |"train"= seed 11 |"val"= seed 10

t_switching = benign_switching(sim, s, "test", sim_len)

schedule_attacks(s, attacker="naive", t_end = sim_len, switching_times=t_switching)

# --- sample components ---
sim.add_sampler(sample_ieds())


# --- run simulation ---
sim_data = sim.run(s)


# --- list of ieds to create virtual interfaces for ---
ieds = list(s.ieds.values())

# --- create virtual interfaces ---
create_interfaces(ieds)

# # --- generate CSV files for each IED in the ied-list --- 
for ied in ieds:
    df = generate_values_df(sim_data, ied)
    df.to_csv(f"./toolchain/{ied.name}/value.csv", header=False, index=False) 

# # # # # --- start communication-system simulation ---
args=[ied.name for ied in ieds]
args.append(str(sim_len))
spawn_script(
        cwd="./toolchain",
        py_paths=["./toolchain"],
        args=args)

# --- plot the substation's one-line diagram (in its final state) ---
ax = plot_one_line(s, line_color="#009B24", buslink_color="#555555", buslink_style="-",
              label_buses=True, label_lines=False, label_buslinks=False)

