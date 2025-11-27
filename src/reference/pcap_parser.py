import json
import sys
import os
import pyshark
import pandas as pd

# ---------- per-packet extractors ----------

def extract_goose_fields(pkt):
    """Grab parsed GOOSE fields (camelCase preserved) plus timing/MACs."""
    if not hasattr(pkt, "goose"):
        return None

    g = pkt.goose
    ether = pkt.eth
    frame = getattr(pkt, "frame_info", None)

    row = {
        "gocbRef": getattr(g, "gocbRef", None),
        "timeAllowedtoLive": int(getattr(g, "timeAllowedtoLive", 0) or 0),
        "datSet": getattr(g, "datSet", None),
        "goID": getattr(g, "goID", None),
        "t": str(getattr(g, "t", None)),
        "stNum": int(getattr(g, "stNum", 0) or 0),
        "sqNum": int(getattr(g, "sqNum", 0) or 0),
        "simulation": (getattr(g, "simulation", None) == "True"),
        "confRev": int(getattr(g, "confRev", 0) or 0),
        "ndsCom": (getattr(g, "ndsCom", None) == "True"),
        "numDatSetEntries": int(getattr(g, "numDatSetEntries", 0) or 0),
        "Source": getattr(ether, "src", None),
        "Destination": getattr(ether, "dst", None),
        "Length": int(getattr(pkt, "length", 0) or 0),
        "EpochArrivalTime": pkt.sniff_time.timestamp(),
        "timeInterval": getattr(frame, "time_delta", None),
    }
    return row

def extract_raw_bytes(pkt):
    """Return full frame bytes as hex string."""
    try:
        data = pkt.get_raw_packet()
        return data.hex() if data else None
    except Exception:
        return None

# ---------- main conversion ----------

def pcapng_to_json(pcapng_file):
    rows = []

    # A: parsed GOOSE fields
    cap_fields = pyshark.FileCapture(
        pcapng_file,
        display_filter="goose",
        keep_packets=False
    )

    # B: raw bytes (JSON backend required when include_raw=True)
    cap_raw = pyshark.FileCapture(
        pcapng_file,
        include_raw=True,
        use_json=True,
        display_filter="goose",
        keep_packets=False
    )

    for pkt_fields, pkt_raw in zip(cap_fields, cap_raw):
        row = extract_goose_fields(pkt_fields)
        if row is None:
            continue
        row["raw_bytes"] = extract_raw_bytes(pkt_raw)
        rows.append(row)

    cap_fields.close()
    cap_raw.close()

    df = pd.DataFrame(rows)

    # Ensure EpochArrivalTime exists (kept for parity with your original)
    df["EpochArrivalTime"] = df["EpochArrivalTime"]

    # Malign indices
    # ids = [2734-1, 2764-1, 7847-1, 7901-1, 7955-1, 8009-1, 8063-1]
    ids=[]
    labels = [True if i in ids else False for i in range(len(df.index))]
    df = df.assign(label=labels)

    # Save to Excel
    output_file = sys.argv[2]
    df.to_excel(output_file, index=False)

# ---------- run ----------

pcapng_file = str(sys.argv[1])
pcapng_to_json(pcapng_file)
