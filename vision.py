"""Claude Vision nameplate extractor.

Sends a photo of a motor nameplate to Claude and returns a structured dict
with every readable field plus a list of fields that could not be confidently
read so the bot can ask the operator for manual input.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from anthropic import Anthropic

_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")

_SYSTEM = """You are an expert at reading electric motor nameplates (WEG, Baldor, GE,
Siemens, ABB, US Motors, Toshiba, etc.). The operator photographs the nameplate
during intake at a motor repair shop. Your job is to transcribe every field
visible on the plate exactly as printed.

Rules:
- Copy text VERBATIM (preserve slashes, dashes, units, capitalization).
- Do not invent values. If a field is not visible, missing, or you cannot read
  it with high confidence, set its value to null and add the field key to
  `unreadable_fields` with a short reason ("glare", "scratched", "out of frame",
  "not present on plate", etc.).
- Numeric values stay as strings to preserve formatting (e.g. "77.2", "1787").
- For the enclosure field, return the exact code (TEFC, ODP, WPI, WPII, TENV...).
- For multi-bearing data put DE / NDE in separate keys.
"""

_TOOL = {
    "name": "record_nameplate",
    "description": "Record every field transcribed from the motor nameplate photo.",
    "input_schema": {
        "type": "object",
        "properties": {
            "marque": {"type": ["string", "null"], "description": "Manufacturer brand, e.g. WEG, Baldor"},
            "hp": {"type": ["string", "null"], "description": "Horsepower / kW / kVA value as printed"},
            "rpm": {"type": ["string", "null"]},
            "volts": {"type": ["string", "null"], "description": "Voltage as printed"},
            "hz": {"type": ["string", "null"], "description": "Frequency in Hz"},
            "phase": {"type": ["string", "null"], "description": "Number of phases (1 or 3)"},
            "amps": {"type": ["string", "null"], "description": "Full load amps"},
            "frame": {"type": ["string", "null"], "description": "Frame / BATI size"},
            "model": {"type": ["string", "null"], "description": "Model or part number (often labelled MODEL, PART #, VJP PART #)"},
            "serial": {"type": ["string", "null"], "description": "Serial number"},
            "type": {"type": ["string", "null"], "description": "TYPE field if present"},
            "service_factor": {"type": ["string", "null"], "description": "SF, e.g. 1.15"},
            "power_factor": {"type": ["string", "null"], "description": "P.F., e.g. 0.86"},
            "efficiency": {"type": ["string", "null"], "description": "Nominal efficiency in %"},
            "insulation_class": {"type": ["string", "null"], "description": "INS. CL., e.g. F"},
            "ambient_temp": {"type": ["string", "null"], "description": "Ambient temperature in C"},
            "duty": {"type": ["string", "null"], "description": "Duty cycle, e.g. CONT"},
            "code": {"type": ["string", "null"], "description": "NEMA code letter"},
            "design": {"type": ["string", "null"], "description": "NEMA design letter"},
            "enclosure": {
                "type": ["string", "null"],
                "description": "Enclosure type. Must be one of TEFC, ODP/DP, WPI, WPII, TENV, or other code as printed.",
            },
            "bearing_de": {"type": ["string", "null"], "description": "Drive end bearing designation"},
            "bearing_nde": {"type": ["string", "null"], "description": "Non-drive end bearing designation"},
            "lubricant": {"type": ["string", "null"]},
            "altitude": {"type": ["string", "null"]},
            "manufacture_date": {"type": ["string", "null"], "description": "Date stamped on plate, verbatim"},
            "raw_text": {
                "type": "string",
                "description": "All other text visible on the plate that was not mapped to a field above, one item per line.",
            },
            "unreadable_fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["field", "reason"],
                },
                "description": "Fields that are damaged, obscured or out of frame and need manual entry.",
            },
        },
        "required": ["raw_text", "unreadable_fields"],
    },
}


# Fields that map onto the printed form. Used by the bot to drive the
# clarification dialogue. Order matters - this is the order operators get
# asked.
FORM_FIELDS: list[tuple[str, str]] = [
    ("marque", "MARQUE"),
    ("hp", "HP / KW / KVA"),
    ("rpm", "RPM"),
    ("volts", "VOLTS"),
    ("hz", "CY (Hz)"),
    ("phase", "PHASE"),
    ("amps", "AMPS"),
    ("frame", "BATI (Frame)"),
    ("model", "MODELE"),
    ("serial", "SERIE"),
    ("type", "TYPE"),
    ("enclosure", "Enclosure (TEFC / DP / WPI / WPII)"),
]


def _encode_image(path: str | Path) -> tuple[str, str]:
    p = Path(path)
    suffix = p.suffix.lower().lstrip(".")
    media = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(
        suffix, "image/jpeg"
    )
    return media, base64.standard_b64encode(p.read_bytes()).decode()


def extract_nameplate(image_path: str | Path, client: Anthropic | None = None) -> dict:
    """Read the nameplate photo and return the structured dict.

    The dict always contains `unreadable_fields` (possibly empty) and
    `raw_text`. All form-mapped keys appear with value None when not present.
    """
    client = client or Anthropic()
    media_type, data = _encode_image(image_path)

    resp = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        system=_SYSTEM,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "record_nameplate"},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": "Transcribe this motor nameplate."},
                ],
            }
        ],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "record_nameplate":
            payload = dict(block.input)
            break
    else:
        raise RuntimeError(f"Vision call did not return tool_use: {resp.content!r}")

    # Normalise: every form-mapped key must exist.
    for key, _label in FORM_FIELDS:
        payload.setdefault(key, None)
    payload.setdefault("unreadable_fields", [])
    payload.setdefault("raw_text", "")
    return payload


if __name__ == "__main__":  # quick manual test
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    result = extract_nameplate(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
