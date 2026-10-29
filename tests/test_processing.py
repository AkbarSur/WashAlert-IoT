import unittest

from shared.processing import SensorSample, extract_features


class ProcessingTests(unittest.TestCase):
    def test_stationary_phone(self):
        samples = [SensorSample(i * 0.5, (0, 0, 9.81), (0, 0, 0)) for i in range(5)]
        result = extract_features(samples)
        self.assertAlmostEqual(result.motion_rms, 0, places=3)
        self.assertAlmostEqual(result.rotation_rad, 0, places=3)

    def test_movement_increases_features(self):
        samples = [SensorSample(i * 0.5, (0, 0, 12), (0.5, 0, 0)) for i in range(5)]
        result = extract_features(samples)
        self.assertGreater(result.motion_rms, 2)
        self.assertGreater(result.rotation_rad, 0.9)

    def test_need_multiple_samples(self):
        with self.assertRaises(ValueError):
            extract_features([SensorSample(0, (0, 0, 9.81), (0, 0, 0))])


if __name__ == "__main__":
    unittest.main()
