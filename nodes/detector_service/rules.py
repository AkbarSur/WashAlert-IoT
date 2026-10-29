"""NODE 3: algoritma WashAlert (pure Python, tanpa MQTT).

Algoritma: finite state machine siklus mesin cuci.

    IDLE --(getar >= start_s detik)--> WASHING <--> SPIN
      ^                                   |
      |                       (diam >= done_s detik)
      |                                   v
      +----(HP B digoyang = konfirmasi)-- DONE  (alert + pengingat berkala)

Data processing di detector (melengkapi RMS & rotasi dari edge):
  C. Moving average RMS edge1 (n jendela terakhir) -> meredam lonjakan sesaat
  D. Timer durasi: lama getar/diam berturut-turut + total lama mesin bekerja
"""

from collections import deque
from dataclasses import dataclass
import os
import time

from shared.messages import Telemetry

IDLE, WASHING, SPIN, DONE = "IDLE", "WASHING", "SPIN", "DONE"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    start_s: float      # getar berturut-turut sebelum dianggap mulai mencuci
    done_s: float       # diam berturut-turut sebelum dianggap selesai
    remind_s: float     # jeda pengingat ulang kalau belum dikonfirmasi
    wash_threshold: float = 0.25    # m/s², RMS rata-rata = mesin bekerja
    still_threshold: float = 0.12   # m/s², di bawah ini = mesin diam (hysteresis)
    spin_threshold: float = 2.0     # m/s², getar keras = fase spin/peras
    spin_rotation: float = 0.5      # rad per jendela, goyangan khas spin
    ack_threshold: float = 3.0      # m/s², HP B digoyang sengaja

    @staticmethod
    def from_env() -> "Config":
        real = os.getenv("CUCI_MODE", "demo").lower() == "real"
        start, done, remind = (60, 120, 300) if real else (6, 8, 20)
        return Config(
            start_s=_env_float("CUCI_START_S", start),
            done_s=_env_float("CUCI_DONE_S", done),
            remind_s=_env_float("CUCI_REMIND_S", remind),
            wash_threshold=_env_float("CUCI_WASH_TH", 0.25),
            still_threshold=_env_float("CUCI_STILL_TH", 0.12),
            spin_threshold=_env_float("CUCI_SPIN_TH", 2.0),
            spin_rotation=_env_float("CUCI_SPIN_ROT", 0.5),
            ack_threshold=_env_float("CUCI_ACK_TH", 3.0),
        )


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str
    run_minutes: float = 0.0   # total lama mesin bekerja
    avg_rms: float = 0.0       # hasil moving average
    alert: bool = False        # True -> kirim notifikasi ke HP B
    publish: bool = True       # False -> jangan timpa status dashboard


class WasherDetector:
    def __init__(self, config: Config | None = None, window: int = 3):
        self.cfg = config or Config.from_env()
        self.armed = True
        self.state = IDLE
        self.rms_window: deque[float] = deque(maxlen=window)
        self.latest: dict[str, Telemetry] = {}
        self.last_seq: dict[tuple[str, str], int] = {}
        self._reset_cycle()

    # ---------- helper ----------
    def _reset_cycle(self):
        self.state = IDLE
        self.active_since: int | None = None
        self.still_since: int | None = None
        self.started_at: int | None = None
        self.finished_at: int | None = None
        self.last_alert_at: int | None = None

    def set_armed(self, armed: bool):
        self.armed = armed
        if not armed:
            self._reset_cycle()
            self.rms_window.clear()

    def _run_minutes(self, now: int) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else now
        return round((end - self.started_at) / 60_000, 2)

    def _decision(self, now: int, reason: str, alert: bool = False, publish: bool = True) -> Decision:
        avg = sum(self.rms_window) / len(self.rms_window) if self.rms_window else 0.0
        return Decision(self.state, reason, self._run_minutes(now), round(avg, 3), alert, publish)

    # ---------- entry point ----------
    def accept(self, data: Telemetry, now_ms: int | None = None) -> Decision:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        if abs(now - data.sent_at_ms) > 30_000:
            return Decision("REJECTED_STALE", "Timestamp di luar jendela 30 detik", publish=False)
        key = (data.device_id, data.boot_id)
        if data.sequence <= self.last_seq.get(key, -1):
            return Decision("REJECTED_REPLAY", "Sequence berulang/tidak urut", publish=False)
        self.last_seq[key] = data.sequence
        self.latest[data.device_id] = data

        if not self.armed:
            return Decision("DISARMED", "Pemantauan dijeda pemilik")
        if data.device_id == "edge2":
            return self._owner_phone(data, now)
        return self._machine_phone(data, now)

    # ---------- HP B (pemilik): konfirmasi dengan menggoyang HP ----------
    def _owner_phone(self, data: Telemetry, now: int) -> Decision:
        shaken = data.motion_rms >= self.cfg.ack_threshold
        if self.state == DONE and shaken:
            minutes = self._run_minutes(now)
            self._reset_cycle()
            return Decision(IDLE, f"Pemilik konfirmasi cucian diambil (siklus {minutes} menit)")
        return self._decision(now, "Referensi HP pemilik diperbarui", publish=False)

    # ---------- HP A (di atas mesin): state machine ----------
    def _machine_phone(self, data: Telemetry, now: int) -> Decision:
        self.rms_window.append(data.motion_rms)                 # processing C
        avg = sum(self.rms_window) / len(self.rms_window)
        cfg = self.cfg

        if self.state == IDLE:
            if avg >= cfg.wash_threshold:
                self.active_since = self.active_since or now    # processing D
                if now - self.active_since >= cfg.start_s * 1000:
                    self.state = WASHING
                    self.started_at = self.active_since
                    return self._decision(now, "Getaran stabil terdeteksi: mesin mulai mencuci")
                return self._decision(now, "Ada getaran, menunggu cukup lama sebelum dianggap mencuci")
            self.active_since = None
            return self._decision(now, "Mesin diam")

        if self.state in (WASHING, SPIN):
            if avg < cfg.still_threshold:
                self.still_since = self.still_since or now      # processing D
                if now - self.still_since >= cfg.done_s * 1000:
                    self.state = DONE
                    self.finished_at = self.still_since
                    self.last_alert_at = now
                    return self._decision(now, "Mesin berhenti bergetar: cucian selesai!", alert=True)
                return self._decision(now, "Mesin jeda, memastikan apakah sudah selesai")
            self.still_since = None
            spinning = avg >= cfg.spin_threshold or data.rotation_rad >= cfg.spin_rotation
            self.state = SPIN if spinning else WASHING
            return self._decision(now, "Getaran keras: fase peras (spin)" if spinning else "Mesin mencuci")

        # DONE: ingatkan ulang sampai pemilik konfirmasi
        if now - (self.last_alert_at or now) >= cfg.remind_s * 1000:
            self.last_alert_at = now
            return self._decision(now, "Pengingat: cucian belum diambil", alert=True)
        return self._decision(now, "Cucian selesai, menunggu konfirmasi pemilik")
