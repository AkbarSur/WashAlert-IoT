import unittest

from nodes.detector_service.rules import Config, WasherDetector
from shared.messages import Telemetry

T0 = 1_790_000_000_000
CFG = Config(start_s=6, done_s=8, remind_s=20)


class WasherTests(unittest.TestCase):
    def setUp(self):
        self.d = WasherDetector(CFG)
        self.seq = {"edge1": 0, "edge2": 0}

    def send(self, device, t_s, rms, rot=0.0):
        now = T0 + int(t_s * 1000)
        msg = Telemetry(device, "boot", self.seq[device], now, rms, rot)
        self.seq[device] += 1
        return self.d.accept(msg, now_ms=now)

    def run_cycle(self):
        """Diam -> cuci -> spin -> diam. Mengembalikan semua keputusan edge1."""
        out, t = [], 0
        for rms, rot, steps in [(0.02, 0, 3), (0.4, 0.05, 6), (3.0, 0.8, 4), (0.02, 0, 8)]:
            for _ in range(steps):
                out.append(self.send("edge1", t, rms, rot))
                t += 2
        return out, t

    def test_full_cycle_reaches_done_once(self):
        out, _ = self.run_cycle()
        statuses = [d.status for d in out]
        for state in ("IDLE", "WASHING", "SPIN", "DONE"):
            self.assertIn(state, statuses)
        self.assertEqual(sum(d.alert for d in out), 1)
        self.assertGreater(out[-1].run_minutes, 0)

    def test_short_bump_does_not_start(self):
        self.send("edge1", 0, 2.0)            # HP tersenggol sekali
        for t in range(2, 20, 2):
            d = self.send("edge1", t, 0.02)
        self.assertEqual(d.status, "IDLE")

    def test_short_pause_is_not_done(self):
        t = 0
        for _ in range(6):
            self.send("edge1", t, 0.4); t += 2
        for _ in range(3):                    # jeda 4 detik < done_s
            d = self.send("edge1", t, 0.02); t += 2
        self.assertNotEqual(d.status, "DONE")
        d = self.send("edge1", t, 0.4)
        self.assertEqual(d.status, "WASHING")

    def test_reminder_then_owner_ack(self):
        out, t = self.run_cycle()
        d = self.send("edge1", t + 25, 0.02)
        self.assertTrue(d.alert)              # pengingat
        d = self.send("edge2", t + 26, 5.0)  # HP B digoyang
        self.assertEqual(d.status, "IDLE")
        self.assertEqual(self.d.state, "IDLE")

    def test_owner_shake_ignored_while_washing(self):
        for t in range(0, 14, 2):
            self.send("edge1", t, 0.4)
        d = self.send("edge2", 14, 5.0)
        self.assertFalse(d.publish)
        self.assertEqual(self.d.state, "WASHING")

    def test_disarm_resets(self):
        self.run_cycle()
        self.d.set_armed(False)
        self.assertEqual(self.d.state, "IDLE")
        self.assertEqual(self.send("edge1", 100, 0.4).status, "DISARMED")

    def test_replay_and_stale_rejected(self):
        msg = Telemetry("edge1", "boot", 5, T0, 0.4, 0)
        self.d.accept(msg, now_ms=T0)
        self.assertEqual(self.d.accept(msg, now_ms=T0).status, "REJECTED_REPLAY")
        old = Telemetry("edge1", "boot", 9, T0 - 31_000, 0.4, 0)
        self.assertEqual(self.d.accept(old, now_ms=T0).status, "REJECTED_STALE")


if __name__ == "__main__":
    unittest.main()
