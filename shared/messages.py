"""MQTT message schema: the contract between the two edge nodes and detector."""

from dataclasses import asdict, dataclass
import json
import math
import time


@dataclass(frozen=True)
class Telemetry:
    device_id: str
    boot_id: str
    sequence: int
    sent_at_ms: int
    motion_rms: float
    rotation_rad: float

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(payload: str | bytes) -> "Telemetry":
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("Telemetry must be a JSON object")
        for key in ("device_id", "boot_id"):
            if not isinstance(value.get(key), str) or not value[key]:
                raise ValueError(f"Invalid {key}")
        if value["device_id"] not in ("edge1", "edge2"):
            raise ValueError("Unknown edge device")
        sequence = value.get("sequence")
        timestamp = value.get("sent_at_ms")
        if type(sequence) is not int or sequence < 0:
            raise ValueError("Invalid sequence")
        if type(timestamp) is not int or timestamp < 0:
            raise ValueError("Invalid timestamp")
        features = []
        for key in ("motion_rms", "rotation_rad"):
            number = value.get(key)
            if type(number) not in (float, int) or not math.isfinite(number) or number < 0:
                raise ValueError(f"Invalid {key}")
            features.append(float(number))
        return Telemetry(value["device_id"], value["boot_id"], sequence, timestamp, *features)

    @staticmethod
    def make(device_id: str, boot_id: str, sequence: int, motion_rms: float, rotation_rad: float) -> "Telemetry":
        return Telemetry(device_id, boot_id, sequence, int(time.time() * 1000), motion_rms, rotation_rad)


def status_json(status: str, reason: str, armed: bool, run_minutes: float = 0.0,
                avg_rms: float = 0.0, device_id: str | None = None,
                sequence: int | None = None, now_ms: int | None = None) -> str:
    """Status terbaru detector, dipublish (retained) untuk dashboard."""
    return json.dumps({
        "status": status,
        "reason": reason,
        "armed": armed,
        "run_minutes": run_minutes,
        "avg_rms": avg_rms,
        "device_id": device_id,
        "sequence": sequence,
        "at_ms": now_ms if now_ms is not None else int(time.time() * 1000),
    })
