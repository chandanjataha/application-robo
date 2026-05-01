"""
Unit tests for Robot Sensor Monitor.
Run with:  pytest tests/ -v --tb=short
"""

import json
import sys
import os
import threading
import time
import unittest
from http.server import HTTPServer
from urllib.request import urlopen
from urllib.error import URLError

# Make app importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app.main as app_module


class TestSensorState(unittest.TestCase):
    """Tests for sensor simulation logic."""

    def test_initial_temperature_in_range(self):
        temp = app_module._state["temperature"]
        self.assertGreater(temp, 0)
        self.assertLess(temp, 120)

    def test_initial_battery_in_range(self):
        bat = app_module._state["battery"]
        self.assertGreaterEqual(bat, 0)
        self.assertLessEqual(bat, 100)

    def test_state_keys_exist(self):
        required = {"temperature", "battery", "velocity", "heading", "lidar_points", "msg_count"}
        self.assertTrue(required.issubset(set(app_module._state.keys())))


class TestHTTPEndpoints(unittest.TestCase):
    """Integration tests: spin up the real server and hit each endpoint."""

    server: HTTPServer
    port: int = 18081

    @classmethod
    def setUpClass(cls):
        # Start sensor simulation
        t = threading.Thread(target=app_module._simulate_sensors, daemon=True)
        t.start()
        # Start HTTP server on a test port
        cls.server = HTTPServer(("127.0.0.1", cls.port), app_module.Handler)
        thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.3)   # let the server start

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _get(self, path, timeout=5):
        url = f"http://127.0.0.1:{self.port}{path}"
        with urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers

    # ── / ────────────────────────────────────────────────────────────────────
    def test_root_returns_200(self):
        status, body, _ = self._get("/")
        self.assertEqual(status, 200)

    def test_root_is_html(self):
        _, body, headers = self._get("/")
        self.assertIn(b"Robot Sensor Monitor", body)
        self.assertIn("text/html", headers.get("Content-Type", ""))

    # ── /health ───────────────────────────────────────────────────────────────
    def test_health_returns_200(self):
        status, _, _ = self._get("/health")
        self.assertEqual(status, 200)

    def test_health_json_structure(self):
        _, body, _ = self._get("/health")
        data = json.loads(body)
        self.assertEqual(data["status"], "ok")
        self.assertIn("uptime_s", data)
        self.assertIn("timestamp", data)

    def test_health_uptime_positive(self):
        _, body, _ = self._get("/health")
        data = json.loads(body)
        self.assertGreater(data["uptime_s"], 0)

    # ── /api/sensors ──────────────────────────────────────────────────────────
    def test_sensors_returns_200(self):
        status, _, _ = self._get("/api/sensors")
        self.assertEqual(status, 200)

    def test_sensors_json_fields(self):
        _, body, _ = self._get("/api/sensors")
        data = json.loads(body)
        for field in ("temperature_c", "battery_pct", "velocity_ms", "heading_deg",
                      "lidar_points", "ros2_msg_count", "timestamp"):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_sensors_temperature_range(self):
        _, body, _ = self._get("/api/sensors")
        data = json.loads(body)
        self.assertGreater(data["temperature_c"], 0)
        self.assertLess(data["temperature_c"], 120)

    def test_sensors_battery_range(self):
        _, body, _ = self._get("/api/sensors")
        data = json.loads(body)
        self.assertGreaterEqual(data["battery_pct"], 0)
        self.assertLessEqual(data["battery_pct"], 100)

    # ── /metrics ──────────────────────────────────────────────────────────────
    def test_metrics_returns_200(self):
        status, _, _ = self._get("/metrics")
        self.assertEqual(status, 200)

    def test_metrics_contains_prometheus_format(self):
        _, body, _ = self._get("/metrics")
        text = body.decode()
        # Prometheus exposition format always has "# HELP" lines
        self.assertIn("# HELP", text)
        self.assertIn("robot_sensor_temperature_celsius", text)
        self.assertIn("robot_battery_level_percent", text)

    # ── 404 ───────────────────────────────────────────────────────────────────
    def test_unknown_path_returns_404(self):
        try:
            self._get("/does-not-exist")
            self.fail("Expected URLError (HTTP 404)")
        except URLError as e:
            self.assertIn("404", str(e))


if __name__ == "__main__":
    unittest.main()
