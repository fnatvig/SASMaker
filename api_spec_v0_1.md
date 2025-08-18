# SASMaker v0.1 API Specification 

SASMaker generates **IEC 61850 GOOSE traffic** for **electrically realistic** scenarios by combining an SCL communication model with a **pandapower** power‑system model.

---

## 0) Design Principles & Degrees of Freedom
- **User chooses number of buses** (electrical nodes). ✅
- **User chooses number of IEDs** (publishers). ✅
- **User defines bus connectivity** (lines in the power model). ✅
- **User binds IED roles to elements** (which IED protects which line/bus). ✅
- **L2 topology simplified** to **one SubNetwork** in v0.1 (star/ring only for visualization). ⚠️
- Skip subscribers/`ExtRef` wiring in v0.1; **publishers only** via GoCBs. ⚠️

---

## 1) `scl_builder` — Basic SCL & Network Graph
Load a template IED, clone N IEDs, optionally visualize star/ring, attach GoCBs, and export one SubNetwork SCD.

### Core classes
- **`IEDTemplate`** — loads a generic IID file for cloning.
- **`IED`** — concrete instance created from the template.
- **`NetworkGraph`** — simple list of nodes/edges (for star/ring visualization only).

### API
- `clone_ied(template: IEDTemplate, count: int) -> list[IED]` 
Creates multiple IEDs from the same template, each with unique names and addresses.

- `connect_ieds(ieds: list[IED], topology: Literal["star","ring"]="star") -> NetworkGraph`
Connects IEDs in a simple network shape (star or ring) and returns the resulting network graph. 

- `assign_gcb(ied: IED, name: str, dataset: list[str], appid: int, tmin_ms: int=4, tmax_ms: int=1000) -> None`
Attach a GOOSE control block (GoCB) and dataset to `IED`'s LLN0 (making `IED` a publisher).

- `auto_assign_gcbs(ieds: list[IED], dataset: list[str], appid_base: int=0x1000, name_fmt: str="GC{idx}", tmin_ms: int=4, tmax_ms: int=1000) -> None`
Attach one GOOSE control block (GoCB) to each IED in a list, auto-generating unique names and APPIDs (making all IEDs publishers).

- `export_scd(filename: str, graph: NetworkGraph, ieds: list[IED]) -> None`  
Save an SCD with one **`<SubNetwork type="8-1">`** with one `<ConnectedAP>` per IED and a `<GSE>` address per GoCB (multicast MAC, APPID, optional Min/MaxTime).

> **Note:** No VLAN/PRP/HSR in v0.1; all publishers share one broadcast domain.

---

## 2) `power_model` — Electrical Network (pandapower)
Owns the electrical single‑line model and solves flows used by protection rules.

### Core classes
- **`GridModel`** — wrapper around `pandapowerNet` with helpers.
- **`BusRef` / `LineRef` / `TrafoRef`** — typed references to elements.

### API
- `new_grid(system_mva: float=100.0, f_hz: float=50.0, seed: int|None=None) -> GridModel`
- `add_bus(g: GridModel, name: str, vn_kv: float) -> BusRef`
- `add_line(g: GridModel, frm: BusRef, to: BusRef, length_km: float, std_type: str) -> LineRef`
- `add_trafo(g: GridModel, hv: BusRef, lv: BusRef, std_type: str) -> TrafoRef`
- `add_load(g: GridModel, bus: BusRef, p_mw: float, q_mvar: float=0.0) -> None`
- `solve_powerflow(g: GridModel) -> None`

### Faults (steady‑state approx in v0.1)
- `apply_fault(g: GridModel, bus: BusRef, z_pu: complex|None=None, kind: Literal["3ph","1ph","2ph"]="3ph") -> None`
- `clear_fault(g: GridModel) -> None`

---

## 3) `mapping` — Bind IED Roles to Grid Elements
Relates publishers (GoCBs) to physical equipment.

### Types
- **`Role`** = Literal["feeder_protection","busbar_protection","trafo_protection","measurement","breaker_control"]
- **`Binding`** = `{ ied: IED, gcb: str, role: Role, element: Union[LineRef, BusRef, TrafoRef] }`

### API
- `bind(ied: IED, gcb: str, role: Role, element) -> Binding`
- `bindings_for_element(element) -> list[Binding]`
- `bindings_for_role(role: Role) -> list[Binding]`

---

## 4) `protection_rules` — Minimal Logic on Top of Power Flow
Stateless evaluators that decide which bindings publish and with what values.

### Types
- **`ProtectionResult`** = `{ publish: list[tuple[Binding, dict]], explain: str }`

### API
- `overcurrent(g: GridModel, bindings: list[Binding], multiples_of_in: float=1.2) -> ProtectionResult`
- `busbar_trip(g: GridModel, bindings: list[Binding], faulted_bus: BusRef) -> ProtectionResult`
- `custom(fn: Callable[[GridModel, list[Binding]], ProtectionResult])`

> `publish` contains `(binding, values_dict)` where `values_dict` matches dataset keys (e.g., `"LD0/LLN0.Mod.stVal": True`).

---

## 5) `event_engine` — Disturbances → Protection → GOOSE
Applies events to the power model, runs protection, and triggers publishers.

### Types
- **`Event`** ∈ { `Fault(bus, kind)`, `ClearFault`, `OpenBreaker(line)`, `CloseBreaker(line)`, `LoadStep(bus, dp_mw)` … }

### API
- `EventEngine(g: GridModel, pubs: dict[Binding, GoosePublisher])`
- `dispatch(e: Event) -> list[tuple[Binding, dict]]`  # updates grid, runs protection, returns publications
- `tick(dt_ms: int) -> None`                          # advances timers/heartbeats
- `collect_frames() -> list[bytes]`                   # all frames since last collect

---

## 6) `goose_generator` — Protocol Engine
Encodes dataset values into GOOSE frames and manages `stNum/sqNum` & retransmissions.

### API
- `GoosePublisher.from_scd(scd_path: str, ied: str, cb: str) -> GoosePublisher`
- `GoosePublisher.publish_event(values: dict) -> None`   # stNum++, sqNum=0
- `GoosePublisher.heartbeat() -> None`                    # sqNum++
- `GoosePublisher.step(dt_ms: int) -> list[bytes]`        # run timers, return frames
- `emit_pcap(path: str, frames: list[bytes]) -> None`

**Behavior:** Uses `<GSE>` Address (multicast MAC, APPID, optional Min/MaxTime). Supports BOOLEAN, INT{8,16,32}, FLOAT32, Timestamp, Quality.

---

## 7) `traffic_scenarios` — Electrically Driven Templates
Operate on the **event engine**; no hard‑coded IED lists.

- `NormalOperationScenario(engine, hb_period_ms=100)`
- `BusFaultScenario(engine, bus: BusRef, at_ms: int=5000, clear_at_ms: int|None=None)`
- `LineOverloadScenario(engine, line: LineRef, step_mw: float, at_ms: int)`

```python
s = BusFaultScenario(engine, bus=b3, at_ms=5000)
for _ in range(7000):
    s.step(1)
frames = engine.collect_frames()
```

---

## 8) `io` — Export
- `write_pcap(path: str, frames: list[bytes])`
- `write_ground_truth(path: str, events: list[Event], protection: list[ProtectionResult])`
- `write_mapping(path: str, bindings: list[Binding])`

---

## 9) `utils`
- XML helpers (namespaces, XSD validation)
- Address utilities (MAC, APPID)
- Deterministic seeding
- Per‑unit/base conversions

---

## End‑to‑End Example

```python
from sasmaker import scl_builder, power_model, mapping, protection_rules
from sasmaker import event_engine, goose_generator, traffic_scenarios, io

# 1) IEDs & SCL
tpl = scl_builder.IEDTemplate("generic.iid")
ieds = scl_builder.clone_ied(tpl, 10)               # user chooses number of IEDs
graph = scl_builder.star(ieds)                       # visualization only
scl_builder.auto_assign_gcbs(ieds, dataset=["LD0/LLN0.Mod.stVal"], appid_base=0x1200)
scl_builder.export_scd("substation.scd", graph, ieds)

# 2) Power model (user chooses number of buses & connectivity)
g = power_model.new_grid()
b1 = power_model.add_bus(g, "B1", 110); b2 = power_model.add_bus(g, "B2", 110); b3 = power_model.add_bus(g, "B3", 110)
l12 = power_model.add_line(g, b1, b2, 10.0, "149-AL1/24-ST1A 110.0")
l23 = power_model.add_line(g, b2, b3, 8.0,  "149-AL1/24-ST1A 110.0")
power_model.add_load(g, b2, 40.0); power_model.solve_powerflow(g)

# 3) Bind IED roles to grid elements (user-controlled mapping)
binds = [
  mapping.bind(ieds[0], "GC1", "feeder_protection", l12),
  mapping.bind(ieds[1], "GC2", "feeder_protection", l23),
  mapping.bind(ieds[2], "GC3", "busbar_protection",  b3),
]

# 4) Publishers from SCD
pubs = {}
for (ied, gcb) in [(ieds[0], "GC1"), (ieds[1], "GC2"), (ieds[2], "GC3")]:
    pubs[mapping.bind(ied, gcb, "measurement", b3)] = goose_generator.GoosePublisher.from_scd("substation.scd", ied=ied.name, cb=gcb)

# 5) Event engine + scenario
engine = event_engine.EventEngine(g, pubs)
scenario = traffic_scenarios.BusFaultScenario(engine, bus=b3, at_ms=5000, clear_at_ms=6500)
for _ in range(7000):
    scenario.step(1)
frames = engine.collect_frames()

# 6) Output
io.write_pcap("bus3_fault.pcap", frames)
```

---

## Notes & Limits (v0.1)
- **One SubNetwork**; no VLAN/PRP/HSR yet. IED L2 topology is not enforced by SCL export.
- **Publishers only** (GoCBs). Subscribers/`ExtRef` wiring is out of scope for v0.1.
- **Protection** is simplified (threshold-based). Extend via `protection_rules.custom`.
- Time is advanced by `step/tick` for deterministic, test‑friendly runs.
