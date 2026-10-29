"""Where raw physical sensor values come from.

'--source simulator' runs on any laptop.
'--source android' calls the real Termux:API sensors on Android.

Both sources produce the SAME SensorSample object. The processing logic
never needs to know which source generated the readings.
"""

import json
import os
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
        def find(keywords: tuple[str, ...]) -> str | None:
            # Nama sensor beda-beda per merek HP, mis. "lsm6dso_acc" (Vivo),
            # "BMI160 Accelerometer", "LSM6DSO Gyroscope". Lewati versi
            # uncalibrated dan sensor turunan (linear acceleration).
            for name in names:
                lower = name.lower()
                if "uncali" in lower or "linear" in lower:
                    continue
                if any(word in lower for word in keywords):
                    return name
            return None

        self.accel_name = os.getenv("SENSOR_ACCEL") or find(("accelerometer", "acceleration sensor", "_acc"))
        self.gyro_name = os.getenv("SENSOR_GYRO") or find(("gyroscope", "gyro"))
        if not self.accel_name or not self.gyro_name:
            raise RuntimeError(
                f"Accelerometer + gyroscope belum terdeteksi. Daftar: {names}. "
                "Pastikan kedua sensor ada di HP dan Termux:API terpasang."
            )
        print(f"[SENSOR] Accelerometer: {self.accel_name}")
        print(f"[SENSOR] Gyroscope: {self.gyro_name}")
        # Lepaskan sensor yang mungkin masih "nyangkut" dari run sebelumnya.
        try:
            subprocess.run(["termux-sensor", "-c"], capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        self.last_accel: tuple[float, float, float] | None = None
        self.last_gyro: tuple[float, float, float] | None = None
        self.failures = 0

    @staticmethod
    def _values(data: dict, sensor_name: str) -> tuple[float, float, float] | None:
        """Ambil 3 sumbu untuk satu sensor; None kalau kosong/tidak ada."""
        keys = [sensor_name] if sensor_name in data else [
            key for key in data if sensor_name.lower() in key.lower() and "uncali" not in key.lower()]
        for key in keys:
            entry = data[key]
            if isinstance(entry, dict):
                values = entry.get("values") or []
                if len(values) >= 3:
                    return tuple(float(v) for v in values[:3])
        return None

    @staticmethod
    def _call(sensors: str, count: int) -> str:
        # Tanpa -d, Termux:API menunggu ~1000 ms per sampel; -d 100 -> ~100 ms.
        try:
            return subprocess.run(
                ["termux-sensor", "-s", sensors, "-d", "100", "-n", str(count)],
                capture_output=True, text=True, timeout=12, check=False,
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            return ""

    @staticmethod
    def _parse_all(output: str) -> dict:
        """Termux bisa mencetak beberapa objek JSON berurutan, dan tiap objek
        kadang hanya berisi SATU sensor. Gabungkan semuanya."""
        merged, decoder, index = {}, json.JSONDecoder(), 0
        while True:
            index = output.find("{", index)
            if index == -1:
                return merged
            try:
                obj, index = decoder.raw_decode(output, index)
            except ValueError:
                index += 1
                continue
            if isinstance(obj, dict):
                for key, entry in obj.items():
                    if isinstance(entry, dict) and len(entry.get("values") or []) >= 3:
                        merged[key] = entry

    def read(self) -> SensorSample:
        """Satu pembacaan gagal TIDAK menghentikan program: pakai nilai terakhir."""
        output = self._call(f"{self.accel_name},{self.gyro_name}", 3)
        data = self._parse_all(output)
        # Sensor yang tidak ikut terkirim -> baca sendiri-sendiri.
        for name in (self.accel_name, self.gyro_name):
            if self._values(data, name) is None:
                data.update(self._parse_all(self._call(name, 1)))

        accel = self._values(data, self.accel_name) or self.last_accel
        gyro = self._values(data, self.gyro_name) or self.last_gyro
        if accel is None or gyro is None:
            self.failures += 1
            if self.failures >= 20:
                raise RuntimeError(
                    "Sensor tidak pernah terbaca 20x berturut-turut. Coba: termux-sensor -c, "
                    "lalu termux-sensor -s " f"{self.accel_name},{self.gyro_name} -n 1. "
                    f"Output terakhir: {output[:300]!r}"
                )
            time.sleep(0.2)
            return self.read()

        if accel is self.last_accel or gyro is self.last_gyro:
            self.failures += 1
            if self.failures % 10 == 1:
                print("[SENSOR] Satu pembacaan kosong, memakai nilai sebelumnya (aman)")
        else:
            self.failures = 0
        self.last_accel, self.last_gyro = accel, gyro
        return SensorSample(time.monotonic(), accel, gyro)


def select_source(name: str, scenario: str) -> SensorSource:
    if name == "android":
        return AndroidTermux()
    if name == "simulator":
        return Simulator(scenario)
    raise ValueError(f"Unknown sensor source: {name}")
