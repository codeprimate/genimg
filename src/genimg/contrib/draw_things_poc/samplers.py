"""``SamplerType`` enum from FlatBuffers ``config.fbs`` (Draw Things / dt-grpc-ts wire values)."""

from __future__ import annotations

from genimg.contrib.draw_things_poc.generated.SamplerType import SamplerType

# UI-style labels aligned with dt-grpc-ts ``typeConverters`` / Draw Things naming.
SAMPLER_UI_LABELS: dict[str, str] = {
    "DPMPP2MKarras": "DPM++ 2M Karras",
    "EulerA": "Euler A",
    "DDIM": "DDIM",
    "PLMS": "PLMS",
    "DPMPPSDEKarras": "DPM++ SDE Karras",
    "UniPC": "UniPC",
    "LCM": "LCM",
    "EulerASubstep": "Euler A Substep",
    "DPMPPSDESubstep": "DPM++ SDE Substep",
    "TCD": "TCD",
    "EulerATrailing": "Euler A Trailing",
    "DPMPPSDETrailing": "DPM++ SDE Trailing",
    "DPMPP2MAYS": "DPM++ 2M AYS",
    "EulerAAYS": "Euler A AYS",
    "DPMPPSDEAYS": "DPM++ SDE AYS",
    "DPMPP2MTrailing": "DPM++ 2M Trailing",
    "DDIMTrailing": "DDIM Trailing",
    "UniPCTrailing": "UniPC Trailing",
    "UniPCAYS": "UniPC AYS",
}

DEFAULT_SAMPLER_NAME: str = "DPMPP2MKarras"

# Draw Things Z-Image / distilled recipe (``--preset z-image`` in CLI).
Z_IMAGE_PRESET_SAMPLER: int = int(SamplerType.UniPCTrailing)


def sampler_enum_rows() -> tuple[tuple[int, str, str], ...]:
    """``(wire_value, wire_name, ui_label)`` sorted by ``wire_value``."""
    rows: list[tuple[int, str, str]] = []
    for name in dir(SamplerType):
        if name.startswith("_"):
            continue
        v = getattr(SamplerType, name)
        if isinstance(v, int):
            label = SAMPLER_UI_LABELS.get(name, name)
            rows.append((v, name, label))
    rows.sort(key=lambda r: r[0])
    return tuple(rows)


def sampler_wire_names() -> tuple[str, ...]:
    return tuple(n for _, n, _ in sampler_enum_rows())


def parse_sampler(value: str) -> int:
    """Resolve ``--sampler``: integer wire value or enum member name (case-insensitive)."""
    s = value.strip()
    if not s:
        raise ValueError("empty sampler")
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        v = int(s)
        valid = {r[0] for r in sampler_enum_rows()}
        if v not in valid:
            raise ValueError(f"unknown sampler integer {v}")
        return v
    key = s.lower()
    for _, name, _ in sampler_enum_rows():
        if name.lower() == key:
            return int(getattr(SamplerType, name))
    raise ValueError(f"unknown sampler name {value!r}")
