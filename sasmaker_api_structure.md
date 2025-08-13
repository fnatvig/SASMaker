# SASMaker API Structure

## 1. `scl_builder` — Build & Manipulate SCL Files
Responsible for creating, cloning, and wiring IEDs, then exporting valid SCD.

**Core classes/functions:**
- **`SubstationModel`** – In-memory representation of the substation.
- **`IEDTemplate`** – Loads a generic IID or ICD, stores structure for cloning.
- **`clone_ied(template, count)`** – Returns N cloned IEDs with unique names and comms.
- **`connect_ieds(publishers, subscribers, pattern="star"|"ring"|"fullmesh")`** – Auto-generates ExtRefs and dataset subscriptions.
- **`export_scd(filename)`** – Writes the SCD XML to disk.

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
Provides high-level scenario templates for generating realistic sequences.

**Core classes/functions:**
- **`Scenario`** – Base class for event sequences.
- **`NormalOperationScenario`** – Periodic GOOSE alive, occasional events.
- **`BreakerTripScenario`** – Models a trip event, increments `stNum`, retransmission.
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

# Select a scenario
scenario = traffic_scenarios.NormalOperationScenario(pub)

# Run scenario and save to PCAP
scenario.run(duration=60)  # 60 seconds
pub.emit_pcap("synthetic_goose.pcap")
```
