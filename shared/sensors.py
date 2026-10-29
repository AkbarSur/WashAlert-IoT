"""Where raw physical sensor values come from.

'--source simulator' runs on any laptop.
'--source android' calls the real Termux:API sensors on Android.

Both sources produce the SAME SensorSample object. The processing logic
never needs to know which source generated the readings.
"""

import json
import math
import random
import shutil
import subprocess
import time
from typing import Protocol

from shared.processing import SensorSample


class SensorSource(Protocol):
    def read(self) -> SensorSample: ...


class Simulator:
    def __init__(self, scenario: str = "still", seed: int = 42):
        self.scenario = scenario
        self.started = time.monotonic()
        self.random = random.Random(seed)

    def _profile(self, elapsed: float) -> tuple[float, float]:
        """(amplitudo getar m/s², kecepatan rotasi rad/s) menurut skenario."""
        if self.scenario == "washer":        # HP A di atas mesin cuci
            if 4 <= elapsed < 16:
                return 0.5, 0.05              # fase mencuci: getar pelan
            if 16 <= elapsed < 24:
                return 4.0, 0.6               # fase spin: getar keras
            return 0.0, 0.0                   # sebelum mulai / sesudah selesai
        if self.scenario == "ack":           # HP B digoyang pemilik
            return (6.0, 0.8) if 40 <= elapsed < 44 else (0.0, 0.0)
        return 0.0, 0.0                       # still

    def read(self) -> SensorSample:
        elapsed = time.monotonic() - self.started
        amplitude, spin = self._profile(elapsed)
        noise = lambda scale: self.random.gauss(0, scale)

        if amplitude > 0:
            acceleration = (
                amplitude * math.sin(5 * elapsed) + noise(0.07),
                noise(0.07),
                9.81 + amplitude * math.cos(4 * elapsed) + noise(0.07),
            )
            gyroscope = (spin + noise(0.03), 0.05, 0.03)
        else:
            acceleration = (noise(0.03), noise(0.03), 9.81 + noise(0.03))
            gyroscope = (noise(0.01), noise(0.01), noise(0.01))

        return SensorSample(time.monotonic(), acceleration, gyroscope)


class AndroidTermux:
    def __init__(self):
        if not shutil.which("termux-sensor"):
            raise RuntimeError("termux-sensor is missing. Install Termux:API and run: pkg install termux-api")
        names_output = subprocess.run(
            ["termux-sensor", "-l"], capture_output=True, text=True, timeout=10, check=True
        ).stdout
        names = json.loads(names_output)
        if isinstance(names, dict):
            names = names.get("sensors", [])
        if not isinstance(names, list):
            raise RuntimeError("Unexpected sensor listing. Run termux-sensor -l and inspect the result")
        self.accel_name = next(
            (name for name in names if
             ("accelerometer" in name.lower() or "acceleration sensor" in name.lower())
             and "uncalibrated" not in name.lower()),
            None,
        )
        self.gyro_name = next(
            (name for name in names if "gyroscope" in name.lower()
             and "uncalibrated" not in name.lower()),
            None,
        )
        if not self.accel_name or not self.gyro_name:
            raise RuntimeError(
                f"Accelerometer + gyroscope belum terdeteksi. Daftar: {names}. "
                "Pastikan kedua sensor ada di HP dan Termux:API terpasang."
            )
        print(f"[SENSOR] Accelerometer: {self.accel_name}")
        print(f"[SENSOR] Gyroscope: {self.gyro_name}")

    def read(self) -> SensorSample:
        # Without -d, Termux:API waits ~1000 ms before each sample.
        # -d 100 shortens it to ~100 ms so a brief pickup is not missed.
        try:
            output = subprocess.run(
                [
                    "termux-sensor", "-s", f"{self.accel_name},{self.gyro_name}",
                    "-d", "100", "-n", "1",
                ],
                capture_output=True, text=True, timeout=12, check=True,
            ).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                "Termux:API gagal membaca sensor. Uji: termux-sensor -l "
                "dan termux-sensor -a -d 100 -n 1; cek instalasi/izin Termux:API."
            ) from exc
        try:
            data = json.loads(output)
            accel = tuple(float(v) for v in data[self.accel_name]["values"][:3])
            gyro = tuple(float(v) for v in data[self.gyro_name]["values"][:3])
            if len(accel) != 3 or len(gyro) != 3:
                raise ValueError("Sensors must each provide three axes")
            return SensorSample(time.monotonic(), accel, gyro)
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(f"Cannot read Termux sensor output: {output[:300]}") from exc


def select_source(name: str, scenario: str) -> SensorSource:
    if name == "android":
        return AndroidTermux()
    if name == "simulator":
        return Simulator(scenario)
    raise ValueError(f"Unknown sensor source: {name}")
