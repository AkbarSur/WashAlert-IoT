"""Common edge pipeline, the same for protected and owner phones.

Real sensor -> two feature extractions -> MQTT Cloud. Simulator is opt-in
and MUST NOT be described as a real IoT physical-edge demonstration.
"""

import argparse
import json
import time
import uuid
from collections.abc import Callable

from shared.messages import Telemetry
from shared.mqtt_connection import create_client, topic
from shared.processing import extract_features
from shared.sensors import select_source

AlertHandler = Callable[[dict], None]


def _parse_args(device_id: str, default_scenario: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"WashAlert {device_id}")
    parser.add_argument(
        "--source", choices=["android", "simulator"], default="android",
        help="Default: sensor Android asli. Simulator hanya untuk pengujian.",
    )
    parser.add_argument(
        "--scenario", choices=["still", "washer", "ack"], default=default_scenario,
        help="Hanya dipakai dengan --source simulator",
    )
    parser.add_argument("--interval", type=float, default=None)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument(
        "--debug-sensors", action="store_true",
        help="Print raw accelerometer/gyroscope values before processing.",
    )
    args = parser.parse_args()
    if args.interval is None:
        args.interval = 0.1 if args.source == "android" else 0.35
    if args.interval <= 0 or args.samples < 2:
        parser.error("--interval must be positive and --samples >= 2")
    return args


def run_edge(device_id: str, on_alert: AlertHandler | None = None, default_scenario: str = "still"):
    args = _parse_args(device_id, default_scenario)
    label = device_id.upper()
    source = select_source(args.source, args.scenario)
    client = create_client(device_id)

    if on_alert is not None:
        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                print(f"[{label}] MQTT connection rejected: {reason_code}")
                return
            client.subscribe(topic("alerts"), qos=1)
            print(f"[{label}] Subscribed to {topic('alerts')}")

        def on_message(client, userdata, message):
            try:
                alert = json.loads(message.payload)
                if not isinstance(alert, dict):
                    raise ValueError("Alert must be a JSON object")
            except ValueError:
                print(f"[{label}] Ignored malformed alert")
                return
            on_alert(alert)

        client.on_connect = on_connect
        client.on_message = on_message

    client.loop_start()
    boot_id = uuid.uuid4().hex
    sequence = 0
    telemetry_topic = topic(f"edge/{device_id}/telemetry")
    print(f"[{label}] Source: {args.source}")
    print(f"[{label}] Publishes to: {telemetry_topic}")

    try:
        while True:
            samples = []
            for sample_index in range(args.samples):
                sample = source.read()
                samples.append(sample)
                if args.debug_sensors:
                    print(
                        f"[{label} | RAW] accel={sample.acceleration} m/s² "
                        f"gyro={sample.gyroscope} rad/s",
                        flush=True,
                    )
                if sample_index < args.samples - 1:
                    time.sleep(args.interval)
            features = extract_features(samples)
            telemetry = Telemetry.make(
                device_id, boot_id, sequence,
                features.motion_rms, features.rotation_rad,
            )
            info = client.publish(telemetry_topic, telemetry.to_json(), qos=1)
            info.wait_for_publish(timeout=10)
            print(
                f"[{label}] #{sequence} "
                f"motion={features.motion_rms:.3f} m/s², "
                f"rotation={features.rotation_rad:.3f} rad"
            )
            sequence += 1
    except KeyboardInterrupt:
        print(f"[{label}] Stopped")
    finally:
        client.loop_stop()
        client.disconnect()
