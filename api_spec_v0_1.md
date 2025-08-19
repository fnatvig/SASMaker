# SASMaker v0.1 API Specification 

SASMaker generates **IEC 61850 GOOSE traffic** for **electrically realistic** scenarios by combining an SCL communication model with a **pandapower** power‑system model.

---

## 0) Design Principles & Degrees of Freedom
- **User chooses number of buses** (electrical nodes). 
- **User chooses number of IEDs** (communication nodes). 
- **User defines bus connectivity** (lines in the power model). 
- **User binds IED roles to elements** (which IED protects which line/bus). 
- **Layer-2 topology is fixed to a star** (all IEDs connect to a single virtual switch / single `<SubNetwork>`). 
- Skip subscribers/`ExtRef` wiring in v0.1; **publishers only** via GoCBs. 

---

## 1) `scl_builder` — IID-centric SCL & Network Metadata
Loads an IID template, clones N IEDs, updates `<Communication>` (ConnectedAP/GSE) for each IED, and writes back new IID files.

### Core classes
- **`IEDTemplate`** — loads a generic IID template (with `<Communication>` + GoCB structure.
- **`IED`** — concrete instance created from the template (unique name, MACm APPID, GoCBs).
- **`NetworkGraph`** — node/edge structure used only for visualization (star layout).

### API
- `clone_ied(template: IEDTemplate, count: int) -> list[IED]` 
Creates multiple IED instances with unique names and reserved addressing.

- `visualize_topology(ieds: list[IED]) -> NetworkGraph`
Returns a star layout graph for diagrams. Visualization-only; does not modify IID `<Communication>`.

- `assign_gcb(ied: IED, name: str, dataset: list[str], appid: int, tmin_ms: int=4, tmax_ms: int=1000) -> None`
Ensures the IED has a GOOSE control block (GoCB) + `<GSE>` entry.

- `auto_assign_gcbs(ieds: list[IED], dataset: list[str], appid_base: int=0x1000, name_fmt: str="GC{idx}", tmin_ms: int=4, tmax_ms: int=1000) -> None`
Attach one GoCB to each IED in a list, auto-generating unique names and APPIDs (making all IEDs publishers).

- `ensure_unique_comm(ieds: list[IED], mac_base: str="01-0C-CD-01-00-00", appid_base: int=0x1000) -> None`  
Iterates through all IEDs and makes multicast MAC + APPID unique and consistent in `<GSE>`.

- `export_iids(dirpath: str, ieds: list[IED]) -> list[str]`
Writes one IID per IED with updated `<Communication>`.



> **Note:** No VLAN/PRP/HSR in v0.1; all publishers share a single broadcast domain assumption.

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

## 6) `goose_generator` — Protocol Engine (IID-first)
Encodes dataset values into GOOSE frames and manages `stNum/sqNum` & retransmissions. libiec61850 could most likely be used here.

### API
- `GoosePublisher.from_iid((iid_path: str, ied: str, goCB: str) -> GoosePublisher`
- `GoosePublisher.publish_event(values: dict) -> None`   # stNum++, sqNum=0
- `GoosePublisher.heartbeat() -> None`                    # sqNum++
- `GoosePublisher.step(dt_ms: int) -> list[bytes]`        # run timers, return frames
- `emit_pcap(path: str, frames: list[bytes]) -> None`

**Behavior:** Reads `<GSE>` Address (multicast MAC, APPID, Min/MaxTime) from IID.

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
- IID merge/patch helpers for `<Communication>`

---

## End‑to‑End Example

```python
from sasmaker import scl_builder, power_model, mapping, protection_rules
from sasmaker import event_engine, goose_generator, traffic_scenarios, io

# 1) IEDs & SCL
tpl = scl_builder.IEDTemplate("generic.iid")           # template with <Communication> + GoCB
ieds = scl_builder.clone_ied(tpl, 10)                  # user chooses number of IEDs
_ = scl_builder.visualize_topology(ieds)         # visualization only
scl_builder.auto_assign_gcbs(ieds, dataset=["LD0/LLN0.Mod.stVal"], appid_base=0x1200)
scl_builder.ensure_unique_comm(ieds, mac_base="01-0C-CD-01-00-00", appid_base=0x1200)
iid_paths = scl_builder.export_iids("./out/iids", ieds)  # one IID per IED (updated Communication)

# 2) Power model (user chooses buses & connectivity)
g = power_model.new_grid()
b1 = power_model.add_bus(g, "B1", 110); b2 = power_model.add_bus(g, "B2", 110); b3 = power_model.add_bus(g, "B3", 110)
l12 = power_model.add_line(g, b1, b2, 10.0, "149-AL1/24-ST1A 110.0")
l23 = power_model.add_line(g, b2, b3, 8.0,  "149-AL1/24-ST1A 110.0")
power_model.add_load(g, b2, 40.0); power_model.solve_powerflow(g)

# 3) Bind IED roles
binds = [
  mapping.bind(ieds[0], "GC1", "feeder_protection", l12),
  mapping.bind(ieds[1], "GC2", "feeder_protection", l23),
  mapping.bind(ieds[2], "GC3", "busbar_protection",  b3),
]

# 4) Publishers from IID
pubs = {}
for (ied, gcb) in [(ieds[0], "GC1"), (ieds[1], "GC2"), (ieds[2], "GC3")]:
    iid_path = next(p for p in iid_paths if p.endswith(f"{ied.name}.iid"))
    pubs[mapping.bind(ied, gcb, "measurement", b3)] = goose_generator.GoosePublisher.from_iid(
        iid_path, ied=ied.name, cb=gcb
    )

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
