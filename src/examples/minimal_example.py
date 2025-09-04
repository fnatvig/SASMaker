from sasmaker import Substation
from sasmaker.builder import snap_child_to_slot
from sasmaker.plotting import plot_one_line
# from sasmaker.simulation import Simulation, sample_cts, sample_cbs, sample_buses, inject_overcurrent_on_line_to_bus, sample_ieds
from sasmaker.simulation import Simulation, inject_overcurrent_on_line_to_bus, sample_ieds
from sasmaker.util import generate_values_df, create_interfaces, spawn_script

s = Substation("Simple substation")

# Adding busbars
bExt = s.add_busbar("S/S-230/66kV", vn_kv=66, x=4.0, y=1.0, draw_slots=1, ext_grid=True)
b1 = s.add_busbar("bus1", vn_kv=66, x=1.0, y=0.0, draw_slots=3)
b2 = s.add_busbar("remoteA", vn_kv=66, x=1.0, y=-1.0)
b3 = s.add_busbar("remoteB", vn_kv=66, x=1.0, y=-1.0)

# Placing busbars (just for plotting)
snap_child_to_slot(s, bExt, b1, slot_idx=0, drop=0.45)
snap_child_to_slot(s, b1, b2, slot_idx=0, drop=0.45)
snap_child_to_slot(s, b1, b3, slot_idx=2, drop=0.45)

# Efternal grid (reference bus)
s.add_ext_grid("Grid", bExt)

# External feeders (real lines)
l1 = s.add_line("L1", bExt, b1, length_km=10.0)
l2 = s.add_line("L2", b1, b2, length_km=5.0)
l3 = s.add_line("L3", b1, b3, length_km=5.0)


# Circuit breakers
cb1 = s.add_cb("CB1", l1, side="to", closed=True)
cb2 = s.add_cb("CB2", l2, side="from", closed=True)
cb3 = s.add_cb("CB3", l3, side="from", closed=True)


# Current transformers (measures the current in lines)
ct1 = s.add_ct("CT1", l1, side="to")
ct2 = s.add_ct("CT2", l2, side="from")
ct3 = s.add_ct("CT3", l3, side="from")


# Add loads
s.add_load("LoadA", b2, p_mw=14.5, q_mvar=9.5)
s.add_load("LoadB", b3, p_mw=14.5, q_mvar=9.5)

# Adding IEDs and connecting them to one CT and one CB each
ied1 = s.add_ied("IED1", ct=ct1, cb=cb1)
ied1.ptoc.pickup_ka = 0.45
ied2 = s.add_ied("IED2", ct=ct2, cb=cb2)
ied2.ptoc.pickup_ka = 0.2
ied3 = s.add_ied("IED3", ct=ct3, cb=cb3)
ied3.ptoc.pickup_ka = 0.2
# ied4 = s.add_ied("IED4", ct=ct3, cb=cb3)
# ied4.ptoc.pickup_ka = 0.2


# Simulation conf
sim = Simulation("step load", t_end=10, dt=0.1, vary_loads=True)



# Event scheduler
# inject_overcurrent_on_line_to_bus(sim, t0=0.6, duration=0.4, line_name="L3", factor=1.5)

# Determining what data to inspect/export
sim.add_sampler(sample_ieds())

# Runs the simulation
sim_data = sim.run(s)

# Export CSVs (for ied comm)
ieds = [ied1, ied2, ied3]

create_interfaces(numIEDs = len(ieds))

for ied in ieds:
    df = generate_values_df(sim_data, ied)
    df.to_csv(f"./toolchain/SASMaker_{ied.name}/value.csv", header=False) 




spawn_script(
        cwd="./toolchain",
        py_paths=["./toolchain"])

# Export complete simulation
# sim_data.to_csv("output/simulation.csv")

# plot last state of system
plot_one_line(s, line_color="#009B24", buslink_color="#555555", buslink_style="-",
              label_buses=True, label_lines=False, label_buslinks=False)

