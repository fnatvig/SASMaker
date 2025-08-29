from sasmaker import Substation
from sasmaker.builder import snap_child_to_slot
from sasmaker.plotting import plot_one_line
from sasmaker.simulation import Simulation, sample_cts, sample_lines, sample_buses, evt_set_load

s = Substation("1-bar substation")

# Adding busbars
bExt = s.add_busbar("Ext. grid", vn_kv=66, x=4.0, y=1.0, draw_slots=1, draw_length=0.2)
b1 = s.add_busbar("bus1", vn_kv=66, x=1.0, y=0.0, draw_slots=3)
b2 = s.add_busbar("remoteA", vn_kv=66, x=1.0, y=-1.0)
b3 = s.add_busbar("remoteB", vn_kv=66, x=1.0, y=-1.0)

# Placing busbars (just for plotting)
snap_child_to_slot(s, bExt, b1, slot_idx=0, drop=0.45, busbar_length=0.8)
snap_child_to_slot(s, b1, b2, slot_idx=0, drop=0.45, busbar_length=0.2)
snap_child_to_slot(s, b1, b3, slot_idx=2, drop=0.45, busbar_length=0.2)

# Efternal grid (reference bus)
s.add_ext_grid("Grid", bExt)

# External feeders (real lines)
l1 = s.add_line("L1", bExt, b1, length_km=10.0)
l2 = s.add_line("L2", b1, b2, length_km=5.0)
l3 = s.add_line("L3", b1, b3, length_km=5.0)

# Circuit breakers
cb1 = s.add_cb("CB1", l1, side="to", closed=True)
cb2=s.add_cb("CB2", l2, side="from", closed=True)
cb3=s.add_cb("CB3", l3, side="from", closed=True)

# Current transformers (measures the current in lines)
ct1 = s.add_ct("CT1", l1, side="to")
ct2=s.add_ct("CT2", l2, side="from")
ct3=s.add_ct("CT3", l3, side="from")

# Add a 15 MW / 3 Mvar load at MV bus, equal per phase
s.add_load("LoadA", b2, p_mw=20.0, q_mvar=5.0)
s.add_load("LoadB", b3, p_mw=15.0, q_mvar=3.5)

# Adding IEDs and connecting them to one CT and one CB each
ied1 = s.add_ied("ied1", ct=ct1, cb=cb1)
ied2 = s.add_ied("ied2", ct=ct2, cb=cb2)
ied3 = s.add_ied("ied3", ct=ct3, cb=cb3)

# Simulation conf
sim = Simulation("step load", t_end=2.0, dt=0.1, vary_loads=True)

# Event scheduler
sim.at(1.0, evt_set_load(load_name="LoadB", p_mw=40.0, q_mvar=7.0), "increase load")

# Determining what to inspect
sim.add_sampler(sample_cts())
sim.add_sampler(sample_lines(["L1"]))
sim.add_sampler(sample_buses(["bus1", "remoteA"]))

df = sim.run(s)         # or s.run_simulation(sim)
print(df.head())
df.to_excel("output/test_output.xlsx")
plot_one_line(s, line_color="#009B24", buslink_color="#555555", buslink_style="-",
              label_buses=True, label_lines=False, label_buslinks=False)

