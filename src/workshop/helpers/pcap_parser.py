"""Parse IEC 61850 GOOSE traffic from PCAP or PCAPNG files."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import tempfile

import pandas as pd
import pyshark


def vlan_pcp_from_raw(raw_hex: str) -> int | None:
    """Extract the IEEE 802.1Q priority code point from a raw frame."""
    if not isinstance(raw_hex, str) or len(raw_hex) < 32:
        return None

    raw_hex = raw_hex.lower()
    tpid_index = raw_hex.find("8100")

    if tpid_index == -1:
        return None

    tci_start = tpid_index + 4
    tci_end = tci_start + 4

    if tci_end > len(raw_hex):
        return None

    try:
        tci = int(raw_hex[tci_start:tci_end], 16)
    except ValueError:
        return None

    return (tci >> 13) & 0x7


def _integer_field(layer, name: str) -> int:
    """Read an integer protocol field, using zero when absent."""
    return int(getattr(layer, name, 0) or 0)


def _boolean_field(layer, name: str) -> bool:
    """Read a boolean protocol field from PyShark."""
    value = getattr(layer, name, None)
    return str(value).lower() in {"true", "1"}

def _epoch_arrival_time(packet) -> float:
    """Return the packet arrival time as Unix seconds."""
    value = getattr(packet, "sniff_timestamp", None)

    if value is None:
        raise ValueError("Packet has no capture timestamp")

    try:
        return float(value)
    except (TypeError, ValueError):
        # Newer TShark versions may return an ISO 8601 timestamp,
        # for example: 2026-08-03T14:59:49.871540391Z
        return pd.Timestamp(str(value)).timestamp()

def _get_field(layer, *names, default=None):
    """Read a field using any of its possible PyShark attribute names."""
    for name in names:
        value = getattr(layer, name, None)

        if value is not None:
            return value

    return default


def _integer_field(layer, *names) -> int:
    """Read an integer protocol field, using zero when absent."""
    value = _get_field(layer, *names)

    if value is None:
        return 0

    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return 0


def _boolean_field(layer, *names) -> bool:
    """Read a boolean protocol field from PyShark."""
    value = _get_field(layer, *names)

    if value is None:
        return False

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
        "set",
    }

def _extract_goose_fields(packet) -> dict | None:
    """Extract relevant GOOSE and Ethernet fields from one packet."""
    if not hasattr(packet, "goose") or not hasattr(packet, "eth"):
        return None

    goose_layer = packet.goose
    goose = getattr(goose_layer, "goosePdu_element", None)
    ethernet = packet.eth

    if goose is None:
        return None

    timestamp = _get_field(goose, "t")

    return {
        "gocbRef": _get_field(
            goose,
            "gocbRef",
            "gocbref",
        ),
        "timeAllowedtoLive": _integer_field(
            goose,
            "timeAllowedtoLive",
            "timeallowedtolive",
        ),
        "datSet": _get_field(
            goose,
            "datSet",
            "dataset",
        ),
        "goID": _get_field(
            goose,
            "goID",
            "goid",
        ),
        "t": str(timestamp) if timestamp is not None else None,
        "stNum": _integer_field(
            goose,
            "stNum",
            "stnum",
        ),
        "sqNum": _integer_field(
            goose,
            "sqNum",
            "sqnum",
        ),
        "simulation": _boolean_field(
            goose,
            "simulation",
        ),
        "confRev": _integer_field(
            goose,
            "confRev",
            "confrev",
        ),
        "ndsCom": _boolean_field(
            goose,
            "ndsCom",
            "ndscom",
        ),
        "numDatSetEntries": _integer_field(
            goose,
            "numDatSetEntries",
            "numdatasetentries",
        ),
        "Source": _get_field(ethernet, "src"),
        "Destination": _get_field(ethernet, "dst"),
        "Length": int(getattr(packet, "length", 0) or 0),
        "EpochArrivalTime": _epoch_arrival_time(packet),
    }


def _extract_raw_bytes(packet) -> str | None:
    """Return the complete Ethernet frame as hexadecimal text."""
    try:
        raw_data = packet.get_raw_packet()
    except Exception:
        return None

    return raw_data.hex() if raw_data else None


def _read_capture(capture_path: Path) -> list[dict]:
    """
    Parse a temporary copy of the capture.

    TShark is confined by AppArmor on the workshop VM and cannot read
    captures directly from the project directory, but it can read /tmp.
    Running in a worker thread also avoids Jupyter's asyncio event loop.
    """
    rows = []
    event_loop = asyncio.new_event_loop()

    with tempfile.TemporaryDirectory(
        prefix="sasmaker_pcap_"
    ) as temporary_directory:
        temporary_path = (
            Path(temporary_directory) / capture_path.name
        )

        shutil.copy2(capture_path, temporary_path)

        capture = pyshark.FileCapture(
            str(temporary_path),
            display_filter="goose",
            include_raw=True,
            use_json=True,
            keep_packets=False,
            eventloop=event_loop,
        )

        try:
            for packet in capture:
                row = _extract_goose_fields(packet)

                if row is None:
                    continue

                row["raw_bytes"] = _extract_raw_bytes(packet)
                rows.append(row)

        finally:
            try:
                capture.close()
            finally:
                event_loop.close()

    return rows


def parse_goose_pcap(
    pcap_file: str | Path,
) -> pd.DataFrame:
    """
    Parse all GOOSE packets in a PCAP or PCAPNG file.

    Parameters
    ----------
    pcap_file:
        Path to the capture file.

    Returns
    -------
    pandas.DataFrame
        One row per captured GOOSE packet.

        ``RelativeTime`` is measured from the first captured GOOSE
        packet. ``timeInterval`` is the interval since the preceding
        captured GOOSE packet, regardless of GOOSE stream.
    """
    capture_path = Path(pcap_file).expanduser()

    if not capture_path.is_file():
        raise FileNotFoundError(
            f"Capture file not found: {capture_path}"
        )

    # PyShark's synchronous interface conflicts with Jupyter's active
    # asyncio loop. Running it in a worker thread avoids that conflict.
    with ThreadPoolExecutor(max_workers=1) as executor:
        rows = executor.submit(
            _read_capture,
            capture_path,
        ).result()

    if not rows:
        raise ValueError(
            f"No GOOSE packets found in capture: {capture_path}"
        )

    dataframe = pd.DataFrame(rows)

    dataframe = dataframe.sort_values(
        "EpochArrivalTime"
    ).reset_index(drop=True)

    # Interval since the preceding captured GOOSE packet.
    dataframe["timeInterval"] = (
        dataframe["EpochArrivalTime"]
        .diff()
        .fillna(0.0)
    )

    # Time relative to the first captured GOOSE packet.
    dataframe["RelativeTime"] = (
        dataframe["EpochArrivalTime"]
        - dataframe["EpochArrivalTime"].iloc[0]
    )

    dataframe["vlan_pcp"] = dataframe["raw_bytes"].apply(
        vlan_pcp_from_raw
    )

    # Preserve the labeling convention from the original parser.
    dataframe["label"] = dataframe["vlan_pcp"].eq(0)

    return dataframe