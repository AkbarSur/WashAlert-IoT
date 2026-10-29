"""Demo offline: tanpa HP, broker, atau akun. Pelajari algoritmanya dulu.

PENTING: mode offline hanya menunjukkan processing + algoritma, BUKAN
komunikasi MQTT ke cloud yang diwajibkan tugas.

Jalankan dari folder utama:  python -m scripts.offline_demo
"""

import math

from nodes.detector_service.rules import Config, WasherDetector
from shared.messages import Telemetry
from shared.processing import SensorSample, extract_features

T0 = 1_790_000_000_000
STEP_S = 2  # satu jendela telemetri tiap 2 detik


def window(amplitude: float, spin: float) -> list[SensorSample]:
    """5 sampel sensor mentah -> nanti diolah jadi RMS + rotasi."""
    samples = []
    for i in range(5):
        t = i * 0.25
        accel = (amplitude * math.sin(5 * t), 0.0, 9.81 + amplitude * math.cos(4 * t))
        samples.append(SensorSample(t, accel, (spin, 0.0, 0.0)))
    return samples


def main():
    detector = WasherDetector(Config(start_s=6, done_s=8, remind_s=20))
    seq = {"edge1": 0, "edge2": 0}
    # (keterangan, device, amplitudo getar, kecepatan rotasi, jumlah jendela)
    scenario = [
        ("Mesin belum jalan", "edge1", 0.0, 0.0, 2),
        ("Mencuci (getar pelan)", "edge1", 0.5, 0.05, 5),
        ("Spin (getar keras)", "edge1", 4.0, 0.6, 3),
        ("Mesin berhenti", "edge1", 0.0, 0.0, 6),
        ("Belum diambil...", "edge1", 0.0, 0.0, 6),
        ("Pemilik menggoyang HP B", "edge2", 6.0, 0.8, 1),
    ]
    t = 0
    for title, device, amp, spin, count in scenario:
        print(f"\n== {title} ==")
        for _ in range(count):
            f = extract_features(window(amp, spin))          # processing A + B
            now = T0 + t * 1000
            msg = Telemetry(device, "offline", seq[device], now, f.motion_rms, f.rotation_rad)
            seq[device] += 1
            d = detector.accept(msg, now_ms=now)               # processing C + D + algoritma
            bell = "  <<< NOTIFIKASI KE HP B" if d.alert else ""
            print(f"t={t:3d}s {device} rms={f.motion_rms:5.2f} rot={f.rotation_rad:4.2f} "
                  f"avg={d.avg_rms:5.2f} -> {d.status:8s} {d.reason}{bell}")
            t += STEP_S
    print("\nDemo offline selesai. Berikutnya: jalankan dengan broker MQTT (lihat README).")


if __name__ == "__main__":
    main()
