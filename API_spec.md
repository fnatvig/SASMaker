# SASMaker API Specification

## 1. `scl_builder` — Create Basic SCL Files
Handles loading an IED template, creating copies, connecting them together, and exporting an SCD file.

### Core classes
- **`IEDTemplate`** — Loads a generic IID file for cloning.
- **`IED`** — A concrete IED created from the template.
- **`NetworkGraph`** — Stores a simple list of IEDs and how they're connected.


### Main functions
- **`clone_ied(template: IEDTemplate, count: int) -> list[IED]`**  
  Creates multiple IEDs from the same template, each with unique names and addresses.

- **`connect_ieds(ieds: list[IED], topology: Literal["star", "ring"] = "star") -> NetworkGraph`**  
  Connects IEDs in a simple network shape (star or ring) and returns the resulting network graph. 

- **`export_scd(filename: str) -> None`**  
  Saves the configuration as an SCD file.

### Helper shortcuts
- **`star(ieds)`** — Connects all IEDs to a single switch.
- **`ring(ieds)`** — Connects IEDs in a ring.

---

## 2. `goose_generator` — Create Synthetic GOOSE Messages from SCD
Implements the GOOSE state machine and encoding according to IEC 61850-8-1.

**Core classes/functions:**
- **`GoosePublisher`** – Takes a GoCB definition and sends frames (live or PCAP).
- **`GooseDatasetEncoder`** – Encodes dataset members into ASN.1/BER payload.
- **`GooseScheduler`** – Controls retransmission profile, `stNum`/`sqNum` behavior.
- **`emit_pcap(filename)`** – Saves generated frames to PCAP.

---

## 3. `traffic_scenarios` — Define Normal & Abnormal Behavior
Provides high-level scenario templates for generating plausible sequences without requiring a full power system simulator. Uses role/zone–based rules to keep events logically consistent across any number of IEDs and topologies.

**Core classes/functions:**
- **`Scenario`** – Base class for event sequences.
- **`NormalOperationScenario`** – Periodic GOOSE alive, occasional events.
- **`BreakerTripScenario`** – Trip logic tied to specific role/zone; increments `stNum`, retransmission.
- **`BusbarFaultScenario`** – Multi-breaker trips with staggered timing, based on zone membership.
- **`FloodAttackScenario`** – High-rate publish to simulate DoS.
- **`SpoofScenario`** – Replays stale `stNum`/`sqNum`.

---

## 4. `utils` — Common Helper Functions
General utilities used by other modules.

**Core functions:**
- XML read/write helpers (namespaces, XSD validation).
- MAC/IP/VLAN/APPID generation.
- Time and scheduling utilities.
- Ground truth labeling functions.

---

## Example Usage

```python
from sasmaker import scl_builder, goose_generator, traffic_scenarios

# Load a generic IID template
template = scl_builder.IEDTemplate("generic.iid")

# Create 5 IEDs based on template
ieds = scl_builder.clone_ied(template, count=5)

# Connect them in a star topology
scl_builder.connect_ieds(publishers=[ieds[0]], subscribers=ieds[1:], pattern="star")

# Export system SCD
scl_builder.export_scd("synthetic_substation.scd")

# Load SCD into GOOSE generator
pub = goose_generator.GoosePublisher("synthetic_substation.scd")

# Generate a "normal scenario" for 5 IEDs connected in a star topology
scenario = traffic_scenarios.NormalOperationScenario(pub)

# Run scenario and save to PCAP
scenario.run(duration=60)  # 60 seconds
pub.emit_pcap("synthetic_goose.pcap")
```
