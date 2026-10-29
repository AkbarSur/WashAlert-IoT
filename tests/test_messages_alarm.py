import json
import unittest
from unittest import mock

from shared import alarm
from shared.messages import status_json


class StatusMessageTests(unittest.TestCase):
    def test_status_payload_fields(self):
        body = json.loads(status_json("DONE", "selesai", armed=True, run_minutes=42.5,
                                      avg_rms=0.05, device_id="edge1", sequence=4, now_ms=123))
        self.assertEqual(body, {
            "status": "DONE", "reason": "selesai", "armed": True, "run_minutes": 42.5,
            "avg_rms": 0.05, "device_id": "edge1", "sequence": 4, "at_ms": 123,
        })


class AlarmTests(unittest.TestCase):
    def test_laptop_only_prints(self):
        with mock.patch("shared.alarm.shutil.which", return_value=None), \
             mock.patch("shared.alarm.subprocess.run") as run:
            alarm.ring_alarm({"run_minutes": 40, "reason": "test"})
        run.assert_not_called()

    def test_android_vibrates_and_notifies(self):
        with mock.patch("shared.alarm.shutil.which", return_value="/bin/x"), \
             mock.patch("shared.alarm.subprocess.run") as run:
            alarm.ring_alarm({"run_minutes": 40, "reason": "test"})
        commands = [call.args[0][0] for call in run.call_args_list]
        self.assertEqual(commands, ["termux-vibrate", "termux-notification"])


if __name__ == "__main__":
    unittest.main()
