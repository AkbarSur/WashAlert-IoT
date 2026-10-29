"""DATA PROCESSING (used by BOTH edge devices).

Processing A: acceleration RMS, measuring changes in acceleration magnitude.
Processing B: total angular movement, integrating gyroscope readings.
"""

from dataclasses import dataclass
from math import sqrt

GRAVITY = 9.81


@dataclass(frozen=True)
class SensorSample:
    seconds: float
    acceleration: tuple[float, float, float]
    gyroscope: tuple[float, float, float]


@dataclass(frozen=True)
class Features:
    motion_rms: float
    rotation_rad: float


def extract_features(samples: list[SensorSample]) -> Features:
    if len(samples) < 2:
        raise ValueError("At least 2 sensor samples are required")

    acceleration_errors = []
    for sample in samples:
        x, y, z = sample.acceleration
        acceleration_magnitude = sqrt(x * x + y * y + z * z)
        acceleration_errors.append(acceleration_magnitude - GRAVITY)

    motion_rms = sqrt(sum(value ** 2 for value in acceleration_errors) / len(samples))

    rotation_rad = 0.0
    for previous, current in zip(samples, samples[1:]):
        delta_seconds = max(0.0, current.seconds - previous.seconds)
        gx, gy, gz = current.gyroscope
        angular_speed = sqrt(gx * gx + gy * gy + gz * gz)
        rotation_rad += angular_speed * delta_seconds

    return Features(motion_rms=round(motion_rms, 4), rotation_rad=round(rotation_rad, 4))
