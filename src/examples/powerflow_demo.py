from sasmaker import Substation

# 3φ is default; you can omit the argument
s = Substation("Demo")

b1 = s.add_busbar("Bus A", vn_kv=110, x=0, y=0)
b2 = s.add_busbar("Bus B", vn_kv=110, x=1, y=0)
b3 = s.add_busbar("Bus C", vn_kv=110, x=1, y=1)

# no need to think about impedances, defaults are used
s.add_line("L1", b1, b2, length_km=5.0)

# if you really want a std_type
s.add_line("L2", b2, b3, length_km=5.0)

s.add_ext_grid("Grid", b1)

stats = s.run_powerflow()
print(stats)             # {'vmin_pu': ..., 'vmax_pu': ..., 'max_line_loading_pct': nan}
print(s.res_bus.head())  # this will be res_bus_3ph if present
print(s.res_line.head()) # this will be res_line_3ph if present
