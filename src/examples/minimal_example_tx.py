from sasmaker import Substation
from sasmaker.builder import snap_child_to_slot
from sasmaker.plotting import plot_one_line
# from sasmaker.simulation import Simulation, sample_cts, sample_cbs, sample_buses, inject_overcurrent_on_line_to_bus, sample_ieds
from sasmaker.simulation import Simulation, inject_overcurrent_on_line_to_bus, sample_ieds
from sasmaker.util import generate_values_df, create_interfaces, spawn_script

s = Substation("Simple substation")

# --- busbars ---
bExt = s.add_busbar("S/S-230/66kV-1", vn_kv=66, x=4.0, y=1.0, draw_slots=1, ext_grid=True)
b1   = s.add_busbar("bus1", vn_kv=66, x=1.0, y=0.0, draw_slots=3)
b2   = s.add_busbar("remoteA", vn_kv=66, x=1.0, y=-1.0)
b3   = s.add_busbar("remoteB", vn_kv=66, x=1.0, y=-1.0, draw_slots=2)

# NEW: a 20 kV LV bus under bus1 (for the transformer LV side)
b20  = s.add_busbar("bus20", vn_kv=20, x=1.0, y=-2.0)


# --- placement (for plotting only) ---
snap_child_to_slot(s, bExt, b1, slot_idx=0, drop=0.45)
snap_child_to_slot(s, b1, b2,  slot_idx=0, drop=0.45)
snap_child_to_slot(s, b1, b3,  slot_idx=2, drop=0.45)
snap_child_to_slot(s, b3, b20, slot_idx=1, drop=0.45)   # LV bar hangs below bus1

# --- sources/lines ---
s.add_ext_grid("Grid", bExt)
l1 = s.add_line("L1", bExt, b1, length_km=10.0)
l2 = s.add_line("L2", b1, b2,  length_km=5.0)
l3 = s.add_line("L3", b1, b3,  length_km=5.0)


# --- CBs/CTs/IEDs (unchanged) ---
cb1 = s.add_cb("CB1", l1, side="to",   closed=True)
cb2 = s.add_cb("CB2", l2, side="from", closed=True)
cb3 = s.add_cb("CB3", l3, side="from", closed=True)

ct1 = s.add_ct("CT1", l1, side="to")
ct2 = s.add_ct("CT2", l2, side="from")
ct3 = s.add_ct("CT3", l3, side="from")

ied1 = s.add_ied("IED1", ct=ct1, cb=cb1); ied1.ptoc.pickup_ka = 0.45
ied2 = s.add_ied("IED2", ct=ct2, cb=cb2); ied2.ptoc.pickup_ka = 0.20
ied3 = s.add_ied("IED3", ct=ct3, cb=cb3); ied3.ptoc.pickup_ka = 0.20

# --- transformer via STD TYPE ---
tx1 = s.add_transformer_auto("T1", hv_bus=b3, lv_bus=b20, sn_mva=25.0)

# --- loads (incl. LV side) ---
s.add_load("LoadA", b2,   p_mw=14.5, q_mvar=9.5)
# s.add_load("LoadB", b3,   p_mw=14.5, q_mvar=9.5)
s.add_load("LV_Load", b20, p_mw=6.0,  q_mvar=2.0)

# --- sim ---
sim = Simulation("step load", t_end=2, dt=0.1, vary_loads=True)
# inject_overcurrent_on_line_to_bus(sim, t0=0.6, duration=0.4, line_name="L3", factor=1.75)
sim.add_sampler(sample_ieds())
sim_data = sim.run(s)


# --- plot ---
ax = plot_one_line(s, line_color="#009B24", buslink_color="#555555", buslink_style="-",
              label_buses=True, label_lines=False, label_buslinks=False)

