from sasmaker import Substation
from sasmaker.builder import snap_child_to_slot
from sasmaker.plotting import plot_one_line
from sasmaker.simulation import Simulation, sample_cts, sample_cbs, sample_buses, inject_overcurrent_on_line_to_bus

s = Substation("Larger substation")

# Adding busbars
bExt = s.add_busbar("Ext. grid", vn_kv=66, x=4.0, y=1.0, draw_slots=3)
b1 = s.add_busbar("bus1", vn_kv=66, x=1.0, y=0.0, draw_slots=5)
b2 = s.add_busbar("remoteA", vn_kv=66, x=1.0, y=-1.0)
b3 = s.add_busbar("remoteB", vn_kv=66, x=1.0, y=-1.0)
b4 = s.add_busbar("remoteC", vn_kv=66, x=1.0, y=-1.0)

b5 = s.add_busbar("bus2", vn_kv=66, x=1.0, y=0.0, draw_slots=5)
b6 = s.add_busbar("remoteD", vn_kv=66, x=1.0, y=-1.0)
b7 = s.add_busbar("remoteE", vn_kv=66, x=1.0, y=-1.0)
b8 = s.add_busbar("remoteF", vn_kv=66, x=1.0, y=-1.0)

# Placing busbars (just for plotting)
snap_child_to_slot(s, bExt, b1, slot_idx=0, drop=0.45)
snap_child_to_slot(s, bExt, b5, slot_idx=2, drop=0.45)

snap_child_to_slot(s, b1, b2, slot_idx=0, drop=0.45)
snap_child_to_slot(s, b1, b3, slot_idx=2, drop=0.45)
snap_child_to_slot(s, b1, b4, slot_idx=4, drop=0.45)

snap_child_to_slot(s, b5, b6, slot_idx=0, drop=0.45)
snap_child_to_slot(s, b5, b7, slot_idx=2, drop=0.45)
snap_child_to_slot(s, b5, b8, slot_idx=4, drop=0.45)

# Efternal grid (reference bus)
s.add_ext_grid("Grid", bExt)

# External feeders (real lines)
l1 = s.add_line("L1", bExt, b1, length_km=10.0)
l2 = s.add_line("L2", b1, b2, length_km=5.0)
l3 = s.add_line("L3", b1, b3, length_km=5.0)
l4 = s.add_line("L4", b1, b4, length_km=5.0)

l5 = s.add_line("L5", bExt, b5, length_km=10.0)
l6 = s.add_line("L6", b5, b6, length_km=5.0)
l7 = s.add_line("L7", b5, b7, length_km=5.0)
l8 = s.add_line("L8", b5, b8, length_km=5.0)

# Circuit breakers
cb1 = s.add_cb("CB1", l1, side="to", closed=True)
cb2 = s.add_cb("CB2", l2, side="from", closed=True)
cb3 = s.add_cb("CB3", l3, side="from", closed=True)
cb4 = s.add_cb("CB4", l4, side="from", closed=True)

cb5 = s.add_cb("CB5", l5, side="to", closed=True)
cb6 = s.add_cb("CB6", l6, side="from", closed=True)
cb7 = s.add_cb("CB7", l7, side="from", closed=True)
cb8 = s.add_cb("CB8", l8, side="from", closed=True)

# Current transformers (measures the current in lines)
ct1 = s.add_ct("CT1", l1, side="to")
ct2 = s.add_ct("CT2", l2, side="from")
ct3 = s.add_ct("CT3", l3, side="from")
ct4 = s.add_ct("CT4", l4, side="from")

ct5 = s.add_ct("CT5", l5, side="to")
ct6 = s.add_ct("CT6", l6, side="from")
ct7 = s.add_ct("CT7", l7, side="from")
ct8 = s.add_ct("CT8", l8, side="from")

# Add a 15 MW / 3 Mvar load at MV bus, equal per phase
s.add_load("LoadA", b2, p_mw=15.0, q_mvar=3.5)
s.add_load("LoadB", b3, p_mw=15.0, q_mvar=3.5)
s.add_load("LoadC", b4, p_mw=15.0, q_mvar=3.5)

s.add_load("LoadD", b6, p_mw=15.0, q_mvar=3.5)
s.add_load("LoadE", b7, p_mw=15.0, q_mvar=3.5)
s.add_load("LoadF", b8, p_mw=15.0, q_mvar=3.5)

# Adding IEDs and connecting them to one CT and one CB each
ied1 = s.add_ied("ied1", ct=ct1, cb=cb1)
ied1.ptoc.pickup_ka = 0.45
ied2 = s.add_ied("ied2", ct=ct2, cb=cb2)
ied2.ptoc.pickup_ka = 0.2
ied3 = s.add_ied("ied3", ct=ct3, cb=cb3)
ied3.ptoc.pickup_ka = 0.2
ied4 = s.add_ied("ied4", ct=ct4, cb=cb4)
ied4.ptoc.pickup_ka = 0.2

ied5 = s.add_ied("ied5", ct=ct5, cb=cb5)
ied5.ptoc.pickup_ka = 0.45
ied6 = s.add_ied("ied6", ct=ct6, cb=cb6)
ied6.ptoc.pickup_ka = 0.2
ied7 = s.add_ied("ied7", ct=ct7, cb=cb7)
ied7.ptoc.pickup_ka = 0.2
ied8 = s.add_ied("ied8", ct=ct8, cb=cb8)
ied8.ptoc.pickup_ka = 0.2

# Simulation conf
sim = Simulation("step load", t_end=2.0, dt=0.1, vary_loads=True)


# Event scheduler
# inject_overcurrent_on_line_to_bus(sim, t0=0.6, duration=0.4, line_name="L2", factor=2.0)
inject_overcurrent_on_line_to_bus(sim, t0=0.6, duration=0.4, line_name="L3", factor=1.75)

# Determining what data to inspect/export
sim.add_sampler(sample_cts())
sim.add_sampler(sample_cbs())
sim.add_sampler(sample_buses(["bus1", "remoteA", "remoteB"]))

# Runs the simulation
df = sim.run(s)

# prints simulation data
print("\n First five rows of output: \n", df.head())

# simulation data export
df.to_excel("output/test_output.xlsx")
df.to_csv("output/test_output.csv")

# plot last state of system
plot_one_line(s, line_color="#009B24", buslink_color="#555555", buslink_style="-",
              label_buses=True, label_lines=False, label_buslinks=False)

