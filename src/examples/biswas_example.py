from sasmaker import Substation
from sasmaker.builder import snap_child_to_slot
from sasmaker.plotting import plot_one_line
from sasmaker.simulation import Simulation, inject_overcurrent_on_line_to_bus, inject_overcurrent_on_tx_side, sample_ieds
from sasmaker.util import generate_values_df, create_interfaces, spawn_script

import warnings
from scipy.sparse.linalg import MatrixRankWarning

warnings.filterwarnings("ignore", category=MatrixRankWarning)

s = Substation("Simple substation")

# --- busbars ---
bExt1 = s.add_busbar("S/S-230/66kV-1", vn_kv=66, x=4.0, y=1.0, draw_slots=1, ext_grid=True)
bExt2 = s.add_busbar("S/S-230/66kV-2", vn_kv=66, x=6.5, y=1.0, draw_slots=1, ext_grid=True)

b1   = s.add_busbar("66kV bus-1", vn_kv=66, x=1.0, y=0.0, draw_slots=7)
b2   = s.add_busbar("66kV bus-2", vn_kv=66, x=1.0, y=0.0, draw_slots=7)

b3   = s.add_busbar("11kV bus-1", vn_kv=11, x=1.0, y=-1.0, draw_slots=5)
b4   = s.add_busbar("11kV bus-2", vn_kv=11, x=1.0, y=-1.0, draw_slots=5)

b5   = s.add_busbar("S/S 3-1", vn_kv=11, x=1.0, y=-1.0)
b6   = s.add_busbar("S/S 2-1", vn_kv=11, x=1.0, y=-1.0)

b7   = s.add_busbar("S/S 2-2", vn_kv=11, x=1.0, y=-1.0)
b8   = s.add_busbar("S/S 3-2", vn_kv=11, x=1.0, y=-1.0)

b9   = s.add_busbar("Priority 1", vn_kv=11, x=1.0, y=-1.0, draw_label=False)
b10   = s.add_busbar("Priority 2", vn_kv=11, x=1.0, y=-1.0, draw_label=False)
b11   = s.add_busbar("Priority 3", vn_kv=11, x=1.0, y=-1.0, draw_label=False)

b12   = s.add_busbar("Priority 4", vn_kv=11, x=1.0, y=-1.0, draw_label=False)
b13   = s.add_busbar("Priority 5", vn_kv=11, x=1.0, y=-1.0, draw_label=False)
b14   = s.add_busbar("Priority 6", vn_kv=11, x=1.0, y=-1.0, draw_label=False)


# --- placement (for plotting only) ---
vgap = 0.4
snap_child_to_slot(s, bExt1, b1, slot_idx=0, drop=vgap)
snap_child_to_slot(s, bExt2, b2, slot_idx=0, drop=vgap)

snap_child_to_slot(s, b1, b3, slot_idx=6, drop=2*vgap)
snap_child_to_slot(s, b2, b4, slot_idx=0, drop=2*vgap)

snap_child_to_slot(s, b1, b5, slot_idx=0, drop=3*vgap)
snap_child_to_slot(s, b1, b6, slot_idx=2, drop=3*vgap)

snap_child_to_slot(s, b2, b7, slot_idx=4, drop=3*vgap)
snap_child_to_slot(s, b2, b8, slot_idx=6, drop=3*vgap)

snap_child_to_slot(s, b3, b9, slot_idx=0, drop=vgap)
snap_child_to_slot(s, b3, b10, slot_idx=2, drop=vgap)
snap_child_to_slot(s, b3, b11, slot_idx=4, drop=vgap)

snap_child_to_slot(s, b4, b12, slot_idx=0, drop=vgap)
snap_child_to_slot(s, b4, b13, slot_idx=2, drop=vgap)
snap_child_to_slot(s, b4, b14, slot_idx=4, drop=vgap)


# --- sources/lines ---

s.add_ext_grid("S/S-1", bExt1)
s.add_ext_grid("S/S-2", bExt2)


bl1 = s.add_buslink("BL1", b1, b2)
cb_bl1 = s.add_cb_buslink("CB-100", bl1)
ct_bl1 = s.add_ct_buslink("CT-100", bl1, side="from")
bl2 = s.add_buslink("BL2", b3, b4)
cb_bl2 = s.add_cb_buslink("CB-200", bl2)

l1 = s.add_line("L1", bExt1, b1, length_km=0.5)
l2 = s.add_line("L2", bExt2, b2, length_km=0.5)

l3 = s.add_line("L3", b1, b5,  length_km=0.5)
l4 = s.add_line("L4", b1, b6,  length_km=0.5)

l5 = s.add_line("L5", b2, b7,  length_km=0.5)
l6 = s.add_line("L6", b2, b8,  length_km=0.5)

l7 = s.add_line("L7", b3, b9,  length_km=3.0)
l8 = s.add_line("L8", b3, b10,  length_km=3.0)
l9 = s.add_line("L9", b3, b11,  length_km=3.0)

l10 = s.add_line("L10", b4, b12,  length_km=3.0)
l11 = s.add_line("L11", b4, b13,  length_km=3.0)
l12 = s.add_line("L12", b4, b14,  length_km=3.0)


# --- CBs/CTs/IEDs (unchanged) ---
cb1 = s.add_cb("CB-10", l1, side="to",   closed=True)
cb2 = s.add_cb("CB-20", l2, side="to", closed=True)
cb3 = s.add_cb("CB-11", l3, side="from", closed=True)
cb4 = s.add_cb("CB-12", l4, side="from", closed=True)
cb5 = s.add_cb("CB-22", l5, side="from", closed=True)
cb6 = s.add_cb("CB-21", l6, side="from", closed=True)
cb7 = s.add_cb("CB-31", l7, side="from", closed=True)
cb8 = s.add_cb("CB-32", l8, side="from", closed=True)
cb9 = s.add_cb("CB-33", l9, side="from", closed=True)
cb10 = s.add_cb("CB-41", l10, side="from", closed=True)
cb11 = s.add_cb("CB-42", l11, side="from", closed=True)
cb12 = s.add_cb("CB-43", l12, side="from", closed=True)

ct1 = s.add_ct("CT-10", l1, side="to")
ct2 = s.add_ct("CT-20", l2, side="to")
ct3 = s.add_ct("CT-11", l3, side="from")
ct4 = s.add_ct("CT-12", l4, side="from")
ct5 = s.add_ct("CT-22", l5, side="from")
ct6 = s.add_ct("CT-21", l6, side="from")
ct7 = s.add_ct("CT-31", l7, side="from")
ct8 = s.add_ct("CT-32", l8, side="from")
ct9 = s.add_ct("CT-33", l9, side="from")
ct10 = s.add_ct("CT-41", l10, side="from")
ct11 = s.add_ct("CT-42", l11, side="from")
ct12 = s.add_ct("CT-43", l12, side="from")




ied1 = s.add_ied("LIED10", ct=ct1, cb=cb1); ied1.ptoc.pickup_ka = 0.9
ied2 = s.add_ied("LIED20", ct=ct2, cb=cb2); ied2.ptoc.pickup_ka = 2.0
ied3 = s.add_ied("LIED11", ct=ct3, cb=cb3); ied3.ptoc.pickup_ka = 0.5
ied4 = s.add_ied("LIED12", ct=ct4, cb=cb4); ied4.ptoc.pickup_ka = 0.5
ied5 = s.add_ied("LIED22", ct=ct5, cb=cb5) #; ied5.ptoc.pickup_ka = 0.20
ied6 = s.add_ied("LIED21", ct=ct6, cb=cb6) #; ied6.ptoc.pickup_ka = 0.20
ied7 = s.add_ied("LIED31", ct=ct7, cb=cb7) #; ied7.ptoc.pickup_ka = 0.20
ied8 = s.add_ied("LIED32", ct=ct8, cb=cb8) #; ied8.ptoc.pickup_ka = 0.35
ied9 = s.add_ied("LIED33", ct=ct9, cb=cb9) #; ied9.ptoc.pickup_ka = 0.20
ied10 = s.add_ied("LIED41", ct=ct10, cb=cb10) #; ied10.ptoc.pickup_ka = 0.20
ied11 = s.add_ied("LIED42", ct=ct11, cb=cb11) #; ied11.ptoc.pickup_ka = 0.20
ied12 = s.add_ied("LIED43", ct=ct12, cb=cb12) #; ied12.ptoc.pickup_ka = 0.20

ied100 = s.add_ied("BIED100", ct=ct_bl1, cb=cb_bl1); ied100.ptoc.pickup_ka = 0.3
ied200 = s.add_ied("UFIED", ct=None, cb=cb_bl2)


vt = s.add_vt("VT-UF", bl2, side="to", ied=ied200, link_buses=[b3, b4])


# --- transformer via STD TYPE ---
tx1 = s.add_transformer_auto("T1", hv_bus=b1, lv_bus=b3, sn_mva=63.0)
tx2 = s.add_transformer_auto("T2", hv_bus=b2, lv_bus=b4, sn_mva=63.0)

ctx1 = s.add_ct_tx("CT-13", tx1, side="hv")
ctx2 = s.add_ct_tx("CT-30", tx1, side="lv")
ctx3 = s.add_ct_tx("CT-23", tx2, side="hv")
ctx4 = s.add_ct_tx("CT-40", tx2, side="lv")

cbx1 = s.add_cb_tx("CB-13", tx1, side="hv")
cbx2 = s.add_cb_tx("CB-30", tx1, side="lv")
cbx3 = s.add_cb_tx("CB-23", tx2, side="hv")
cbx4 = s.add_cb_tx("CB-40", tx2, side="lv")

iedx1 = s.add_ied("TIED13", ct=ctx1, cb=cbx1); iedx1.ptoc.pickup_ka = 0.17
iedx2 = s.add_ied("LIED30", ct=ctx2, cb=cbx2); iedx2.ptoc.pickup_ka = 2.0
iedx3 = s.add_ied("TIED23", ct=ctx3, cb=cbx3) #; iedx3.ptoc.pickup_ka = 0.20
iedx4 = s.add_ied("LIED40", ct=ctx4, cb=cbx4) #; iedx4.ptoc.pickup_ka = 0.20


# p_mw_factor = 2.0
# q_mvar_factor=1.0
# --- loads (incl. LV side) ---
s.add_load("S/S 3-1", b5,   p_mw=30, q_mvar=18.5, draw_label = False)
s.add_load("S/S 2-1", b6,   p_mw=30, q_mvar=18.5, draw_label = False)

s.add_load("S/S 2-2", b7,   p_mw=30, q_mvar=18.5, draw_label = False)
s.add_load("S/S 3-2", b8,   p_mw=30, q_mvar=18.5, draw_label = False)



s.add_load("Feeder 1\nPriority 1", b9,   p_mw=5.8, q_mvar=3.4)
s.add_load("Feeder 2\nPriority 4", b10,   p_mw=3.8, q_mvar=2.2)
s.add_load("Feeder 3\nPriority 3", b11,   p_mw=4.9, q_mvar=2.8)

s.add_load("Feeder 4\nPriority 2", b12,   p_mw=5.8, q_mvar=3.4)
s.add_load("Feeder 5\nPriority 5", b13,   p_mw=3.8, q_mvar=2.2)
s.add_load("Feeder 6\nPriority 6", b14,   p_mw=4.9, q_mvar=2.8)
# s.add_load("LoadB", b3,   p_mw=14.5, q_mvar=9.5)
# s.add_load("LV_Load", b20, p_mw=6.0,  q_mvar=2.0)


# --- sim ---
sim = Simulation("step load", t_end=600, dt=1, vary_loads=True)
inject_overcurrent_on_line_to_bus(sim, t0=10, duration=3, line_name="L3", factor=2)
inject_overcurrent_on_line_to_bus(sim, t0=11, duration=3, line_name="L4", factor=2)
inject_overcurrent_on_tx_side(sim, t0=11, duration=3, tx_name="T1", side="hv", factor = 10.0)
sim.add_sampler(sample_ieds())
sim_data = sim.run(s)

# Export CSVs (for ied comm)
ieds = [ied1, ied2, ied3, ied4,
        ied5, ied6, ied7, ied8,
        ied9, ied10, ied11, ied12,
        iedx1, iedx2, iedx3, iedx4,
        ied100, ied200] 

create_interfaces(ieds)

for ied in ieds:
    df = generate_values_df(sim_data, ied)

    # df.to_csv(f"./tempdir/{ied.name}.csv", header=False, index=False)

    df.to_csv(f"./toolchain/{ied.name}/value.csv", header=False, index=False) 

args=[ied.name for ied in ieds]
args.append("600")
spawn_script(
        cwd="./toolchain",
        py_paths=["./toolchain"],
        args=args)

# --- plot ---
ax = plot_one_line(s, line_color="#009B24", buslink_color="#555555", buslink_style="-",
              label_buses=True, label_lines=True, label_buslinks=False)

