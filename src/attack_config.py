# attack_config.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
import copy
import re
import xml.etree.ElementTree as ET


DEFAULT_REL_PATH = Path("toolchain")
DEFAULT_FILENAME = "AttackScenarioConfiguration.xml"   # <-- match your real file


class AttackConfigError(RuntimeError):
    pass


# ----------------- small xml helpers -----------------
def _bool_to_xml(v: bool) -> str:
    return "true" if v else "false"


def _xml_to_bool(s: str) -> bool:
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")


def _find_child(parent: ET.Element, tag: str) -> Optional[ET.Element]:
    for ch in parent:
        if ch.tag == tag:
            return ch
    return None


def _ensure_child(parent: ET.Element, tag: str) -> ET.Element:
    ch = _find_child(parent, tag)
    if ch is None:
        ch = ET.SubElement(parent, tag)
    return ch


def _set_value_attr(parent: ET.Element, tag: str, value: Any) -> ET.Element:
    """
    Set/create <tag value="..."/> under parent.
    """
    e = _ensure_child(parent, tag)
    e.set("value", str(value))
    return e


def _get_value_attr(parent: ET.Element, tag: str) -> Optional[str]:
    """
    Read <tag value="..."/> under parent. Returns None if missing.
    """
    ch = _find_child(parent, tag)
    if ch is None:
        return None
    return ch.get("value")


# ----------------- dos "translation" helpers -----------------
_STREAMS = ("CTRL", "PROT", "MEAS")


def _ied_index(ied_name: str) -> int:
    m = re.fullmatch(r"IED(\d+)", ied_name.strip())
    if not m:
        raise AttackConfigError(f"Can't parse IED index from ied_name='{ied_name}' (expected e.g. 'IED4').")
    return int(m.group(1))


def _interface_for_ied(ied_name: str) -> str:
    # Your convention: IED4 -> veth1.4, IED2 -> veth1.2, ...
    return f"veth1.{_ied_index(ied_name)}"


def _dos_fields_for_stream(ied_name: str, stream: str) -> Dict[str, str]:
    """
    The only fields we "translate" per IED:
      interface, gcbName, dataSet, goID, gocbRef

    This matches your CTRL example exactly and assumes analogous naming
    for PROT and MEAS (as in your IED4 templates).
    """
    s = stream.strip().upper()

    if s == "CTRL":
        return {
            "interface": _interface_for_ied(ied_name),
            "gcbName": f"{ied_name}/CTRL/LLN0/Status",
            "dataSet": f"{ied_name}CTRL/LLN0$Status",
            "goID": f"{ied_name}/CTRL/LLN0/Status",
            "gocbRef": f"{ied_name}CTRL/LLN0$GO$Status",
        }
    if s == "PROT":
        return {
            "interface": _interface_for_ied(ied_name),
            "gcbName": f"{ied_name}/PROT/LLN0/Alarm",
            "dataSet": f"{ied_name}PROT/LLN0$Alarm",
            "goID": f"{ied_name}/PROT/LLN0/Alarm",
            "gocbRef": f"{ied_name}PROT/LLN0$GO$Alarm",
        }
    if s == "MEAS":
        return {
            "interface": _interface_for_ied(ied_name),
            "gcbName": f"{ied_name}/MEAS/LLN0/Meas",
            "dataSet": f"{ied_name}MEAS/LLN0$Meas",
            "goID": f"{ied_name}/MEAS/LLN0/Meas",
            "gocbRef": f"{ied_name}MEAS/LLN0$GO$Meas",
        }

    raise AttackConfigError(f"Unknown stream='{stream}'. Expected one of: CTRL, PROT, MEAS.")


def _infer_stream_from_dos_attack_node(attack_node: ET.Element) -> Optional[str]:
    """
    All dos attacks must have name="dosAttack" (toolchain constraint).
    So we infer which template (CTRL/PROT/MEAS) a block represents from payload fields.
    """
    payload = _find_child(attack_node, "payload")
    if payload is None:
        return None

    # Check a few tags; in your templates these exist and embed the stream.
    for tag in ("gocbRef", "gcbName", "dataSet", "goID"):
        v = _get_value_attr(payload, tag)
        if not v:
            continue

        # "IED4/CTRL/LLN0/Status" style
        m = re.search(r"/(CTRL|PROT|MEAS)/", v)
        if m:
            return m.group(1)

        # "IED4CTRL/LLN0$GO$Status" style (contains CTRL/LLN0...)
        m = re.search(r"(CTRL|PROT|MEAS)/", v)
        if m:
            return m.group(1)

        # fallback substring
        for s in _STREAMS:
            if s in v:
                return s

    return None


@dataclass
class AttackHandle:
    node: ET.Element

    @property
    def name(self) -> str:
        return self.node.get("name", "")

    @property
    def enabled(self) -> bool:
        return _xml_to_bool(self.node.get("enable", "false"))

    def set_enabled(self, enabled: bool) -> None:
        self.node.set("enable", _bool_to_xml(enabled))

    def condition_node(self) -> ET.Element:
        c = _find_child(self.node, "condition")
        if c is None:
            raise AttackConfigError(f"attack '{self.name}': missing <condition>")
        return c

    def payload_node(self) -> ET.Element:
        p = _find_child(self.node, "payload")
        if p is None:
            raise AttackConfigError(f"attack '{self.name}': missing <payload>")
        return p

    def stop_node(self) -> ET.Element:
        s = _find_child(self.node, "stop_condition")
        if s is None:
            raise AttackConfigError(f"attack '{self.name}': missing <stop_condition>")
        return s

    # ---- convenience setters ----
    def set_condition_time(self, t_seconds: float) -> None:
        _set_value_attr(self.condition_node(), "time", t_seconds)

    def set_stop(self, packets_num: Optional[int] = None, pps: Optional[float] = None) -> None:
        s = self.stop_node()
        if packets_num is not None:
            _set_value_attr(s, "packetsNum", int(packets_num))
        if pps is not None:
            _set_value_attr(s, "pps", float(pps))

    def set_payload_field(self, field_tag: str, value: Any) -> None:
        _set_value_attr(self.payload_node(), field_tag, value)

    def set_payload_fields(self, **fields: Any) -> None:
        for k, v in fields.items():
            self.set_payload_field(k, v)


class AttackScenarioConfig:
    def __init__(self, xml_path: Path, *, ied_name: Optional[str] = None):
        self.xml_path = Path(xml_path)
        self.ied_name = ied_name  # recommended; used for translation helpers
        if not self.xml_path.exists():
            raise FileNotFoundError(f"XML not found: {self.xml_path}")

        self.tree = ET.parse(self.xml_path)
        self.root = self.tree.getroot()
        if self.root.tag != "attacks":
            raise AttackConfigError(f"Unexpected root <{self.root.tag}>, expected <attacks>")

    @staticmethod
    def path_for_ied(
        ied_name: str,
        base_dir: Path = DEFAULT_REL_PATH,
        filename: str = DEFAULT_FILENAME,
    ) -> Path:
        return Path(base_dir) / ied_name / filename

    @classmethod
    def load_for_ied(
        cls,
        ied_name: str,
        base_dir: Path = DEFAULT_REL_PATH,
        filename: str = DEFAULT_FILENAME,
    ) -> "AttackScenarioConfig":
        return cls(cls.path_for_ied(ied_name, base_dir=base_dir, filename=filename), ied_name=ied_name)

    # --------- query helpers ---------
    def list_attacks(self) -> List[Tuple[str, bool]]:
        out: List[Tuple[str, bool]] = []
        for a in self.root.findall("attack"):
            out.append((a.get("name", ""), _xml_to_bool(a.get("enable", "false"))))
        return out

    def get_attacks(self, name: str) -> List[AttackHandle]:
        return [AttackHandle(a) for a in self.root.findall("attack") if a.get("name") == name]

    def get_attack(self, name: str) -> AttackHandle:
        matches = self.get_attacks(name)
        if not matches:
            raise AttackConfigError(
                f"Attack not found: name='{name}' in {self.xml_path}\n"
                f"Available: {[n for (n, _) in self.list_attacks()]}"
            )
        return matches[0]

    # --------- mutation helpers ---------
    def disable_all(self) -> None:
        for a in self.root.findall("attack"):
            a.set("enable", "false")

    def clear_attacks(self, name: str) -> int:
        """
        Remove ALL <attack name="..."> entries. Returns count removed.
        """
        removed = 0
        for a in list(self.root.findall("attack")):
            if a.get("name") == name:
                self.root.remove(a)
                removed += 1
        return removed

    def add_attack_copy(self, template_name: str, *, new_name: Optional[str] = None) -> AttackHandle:
        """
        Deep-copy the FIRST <attack name="template_name"> and append it.
        Optionally rename the clone (new_name). Clone starts disabled.
        """
        template = self.get_attack(template_name).node
        new_node = copy.deepcopy(template)

        if new_name is not None:
            new_node.set("name", new_name)

        new_node.set("enable", "false")
        self.root.append(new_node)
        return AttackHandle(new_node)

    def save(self, backup: bool = True) -> None:
        if backup:
            bak = self.xml_path.with_suffix(self.xml_path.suffix + ".bak")
            bak.write_bytes(self.xml_path.read_bytes())
        self.tree.write(self.xml_path, encoding="utf-8", xml_declaration=True)

    # --------- dos template selection (name is always exactly 'dosAttack') ---------
    def _dos_nodes(self) -> List[ET.Element]:
        return [a for a in self.root.findall("attack") if a.get("name") == "dosAttack"]

    def get_dos_template_for_stream(self, stream: str) -> AttackHandle:
        stream_u = stream.strip().upper()
        if stream_u not in _STREAMS:
            raise AttackConfigError(f"Unknown stream='{stream}'. Expected CTRL/PROT/MEAS.")

        candidates = self._dos_nodes()
        if not candidates:
            raise AttackConfigError(f"No <attack name='dosAttack'> found in {self.xml_path}")

        for a in candidates:
            s = _infer_stream_from_dos_attack_node(a)
            if s == stream_u:
                return AttackHandle(a)

        inferred = [(_infer_stream_from_dos_attack_node(a), _get_value_attr(_find_child(a, "payload") or a, "gocbRef"))
                    for a in candidates]
        raise AttackConfigError(
            f"Found dosAttack blocks, but none match stream '{stream_u}'. "
            f"Inferred candidates (stream, gocbRef): {inferred}"
        )

    def add_dos_attack_copy_from_stream_template(self, stream: str) -> AttackHandle:
        tpl = self.get_dos_template_for_stream(stream).node
        new_node = copy.deepcopy(tpl)
        new_node.set("name", "dosAttack")     # enforce toolchain requirement
        new_node.set("enable", "false")       # start disabled
        self.root.append(new_node)
        return AttackHandle(new_node)

    def clear_dos_attacks_keep_one_template_per_stream(self) -> int:
        """
        Removes all <attack name="dosAttack"> blocks except keeps ONE per inferred stream
        CTRL/PROT/MEAS (i.e., keeps 3 templates). Deletes all clones.
        Raises if it can't identify all 3 streams (to avoid deleting the wrong stuff).
        """
        dos = self._dos_nodes()
        if not dos:
            return 0

        keep_indices: set[int] = set()
        seen_streams: set[str] = set()

        for idx, a in enumerate(dos):
            s = _infer_stream_from_dos_attack_node(a)
            if s in _STREAMS and s not in seen_streams:
                keep_indices.add(idx)
                seen_streams.add(s)

        missing = [s for s in _STREAMS if s not in seen_streams]
        if missing:
            inferred = [( _infer_stream_from_dos_attack_node(a),
                         _get_value_attr(_find_child(a, "payload") or a, "gocbRef"))
                        for a in dos]
            raise AttackConfigError(
                f"Can't safely clear dosAttack clones: missing templates for streams {missing}. "
                f"Inferred (stream, gocbRef): {inferred}"
            )

        removed = 0
        # Remove in reverse order so indices don't shift (or just iterate list copy)
        for idx, a in reversed(list(enumerate(dos))):
            if idx in keep_indices:
                continue
            self.root.remove(a)
            removed += 1

        return removed

    # --------- high-level API ---------
    def configure_dos_attack(
        self,
        *,
        stream: str,                   # "CTRL" | "PROT" | "MEAS"
        ied_name: Optional[str] = None, # overrides self.ied_name
        enable: bool = True,
        t0: Optional[float] = None,
        sum: Optional[int] = None,
        pps: Optional[float] = None,
        stNum: int = 0,
        sqNum: int = 0,
        payload_overrides: Optional[Dict[str, Any]] = None,
        allow_multiple: bool = True,
        reuse_first_template: bool = False,
    ) -> AttackHandle:
        """
        Toolchain constraint: all DoS attacks must have name="dosAttack".

        We therefore keep 3 templates (also named dosAttack) and select the correct one by
        stream inference (CTRL/PROT/MEAS) based on payload fields.

        If allow_multiple=True and reuse_first_template=False:
            each call clones the matching stream template and appends a new dosAttack block.
        Else:
            it reuses (and mutates) the matching template itself.
        """
        actual_ied = ied_name or self.ied_name
        if not actual_ied:
            raise AttackConfigError(
                "configure_dos_attack needs ied_name (pass it, or load config via load_for_ied)."
            )

        stream_u = stream.strip().upper()
        if stream_u not in _STREAMS:
            raise AttackConfigError(f"Unknown stream='{stream}'. Expected CTRL/PROT/MEAS.")

        if allow_multiple and not reuse_first_template:
            h = self.add_dos_attack_copy_from_stream_template(stream_u)
        else:
            h = self.get_dos_template_for_stream(stream_u)

        # Always enforce required name
        h.node.set("name", "dosAttack")
        h.set_enabled(enable)

        # Translate only the IED-specific fields you listed
        translated = _dos_fields_for_stream(actual_ied, stream_u)
        h.set_payload_fields(
            interface=translated["interface"],
            gcbName=translated["gcbName"],
            dataSet=translated["dataSet"],
            goID=translated["goID"],
            gocbRef=translated["gocbRef"],
        )

        # Timing/stop knobs
        if t0 is not None:
            h.set_condition_time(t0)
        if sum is not None or pps is not None:
            h.set_stop(packets_num=sum, pps=pps)

        # Caller overrides last
        if payload_overrides:
            h.set_payload_fields(**payload_overrides)

        return h

    # (Kept for backwards compatibility, but NOT safe for DoS anymore.)
    def clear_attacks_keep_first(self, name: str) -> int:
        matches = [a for a in self.root.findall("attack") if a.get("name") == name]
        if len(matches) <= 1:
            return 0
        removed = 0
        for a in matches[1:]:
            self.root.remove(a)
            removed += 1
        return removed


if __name__ == "__main__":
    # Example usage:
    # 1) Your XML must contain THREE templates, all named "dosAttack",
    #    one that targets CTRL, one PROT, one MEAS (distinguished by gocbRef/gcbName/etc).
    cfg = AttackScenarioConfig.load_for_ied("IED4", base_dir=Path("toolchain"))
    print("Before:", cfg.list_attacks())

    # Start clean: disable everything + delete all dosAttack clones but keep 3 templates
    cfg.disable_all()
    cfg.clear_dos_attacks_keep_one_template_per_stream()

    # Add attacks by cloning the right template and translating fields to this IED
    cfg.configure_dos_attack(stream="CTRL", t0=10, sum=750, pps=100, payload_overrides={"stNum": -1, "sqNum": -1}, allow_multiple=True)
    # cfg.configure_dos_attack(stream="MEAS", t0=20, sum=750, pps=80, allow_multiple=True)
    # cfg.configure_dos_attack(stream="PROT", t0=30, sum=750, pps=120, allow_multiple=True)

    cfg.save()