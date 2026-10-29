"""NODE 3: detector WashAlert. Subscribe MQTT, jalankan state machine, kirim alert.

Topik (prefix washalert/<PROJECT_ID>/):
  subscribe  edge/+/telemetry   telemetri HP A (mesin) dan HP B (pemilik)
  subscribe  control            ARM / DISARM dari pemilik
  publish    alerts             saat cucian selesai + pengingat (HP B bergetar)
  publish    status (retained)  status terbaru untuk dashboard
"""

import json
import time

from nodes.detector_service.rules import WasherDetector, Decision
from shared.messages import Telemetry, status_json
from shared.mqtt_connection import create_client, topic


def main():
    detector = WasherDetector()
    status_topic = topic("status")
    offline = status_json("OFFLINE", "Detector terputus", armed=False)
    client = create_client("detector", will=(status_topic, offline))
    telemetry_topic = topic("edge/+/telemetry")
    control_topic = topic("control")

    def publish_status(status: str, reason: str, decision: Decision | None = None,
                       reading: Telemetry | None = None):
        payload = status_json(
            status, reason, detector.armed,
            run_minutes=decision.run_minutes if decision else 0.0,
            avg_rms=decision.avg_rms if decision else 0.0,
            device_id=reading.device_id if reading else None,
            sequence=reading.sequence if reading else None,
        )
        client.publish(status_topic, payload, qos=1, retain=True)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[DETECTOR] Koneksi MQTT ditolak: {reason_code}")
            return
        client.subscribe([(telemetry_topic, 1), (control_topic, 1)])
        print(f"[DETECTOR] Subscribe: {telemetry_topic} dan {control_topic}")
        publish_status("ONLINE", "Detector berjalan")

    def handle_control(payload: bytes):
        command = payload.decode(errors="replace").strip().upper()
        if command not in ("ARM", "DISARM"):
            print(f"[DETECTOR] Perintah tidak dikenal: {command[:40]}")
            return
        detector.set_armed(command == "ARM")
        print(f"[DETECTOR] Perintah pemilik: {command}")
        publish_status("IDLE" if detector.armed else "DISARMED", f"Pemilik mengirim {command}")

    def on_message(client, userdata, message):
        if message.topic == control_topic:
            handle_control(message.payload)
            return
        try:
            reading = Telemetry.from_json(message.payload)
            if message.topic != topic(f"edge/{reading.device_id}/telemetry"):
                print("[DETECTOR] DITOLAK: topik dan device ID tidak cocok")
                return
            decision = detector.accept(reading)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            print(f"[DETECTOR] DITOLAK payload rusak: {exc}")
            return

        print(f"[DETECTOR] {reading.device_id} #{reading.sequence} "
              f"rms={reading.motion_rms:.3f} avg={decision.avg_rms:.3f}: "
              f"{decision.status} — {decision.reason}")
        if decision.publish:
            publish_status(decision.status, decision.reason, decision, reading)
        if decision.alert:
            alert = {
                "event": "laundry_done",
                "run_minutes": decision.run_minutes,
                "reason": decision.reason,
                "detected_at_ms": int(time.time() * 1000),
            }
            client.publish(topic("alerts"), json.dumps(alert), qos=1, retain=False)
            print("[DETECTOR] >>> ALERT dikirim ke HP B")

    client.on_connect = on_connect
    client.on_message = on_message
    print("[DETECTOR] Mulai. Ctrl+C untuk berhenti")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("[DETECTOR] Berhenti")
    finally:
        client.loop_start()
        try:
            info = client.publish(status_topic, status_json("OFFLINE", "Detector dihentikan", armed=False),
                                  qos=1, retain=True)
            info.wait_for_publish(timeout=3)
        except (RuntimeError, ValueError):
            pass
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
