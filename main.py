"""
ROS2-style Robot Sensor Monitor
A demo application simulating a ROS2 robot sensor data publisher/web dashboard.
Exposes:
  - /         → HTML dashboard
  - /health   → health check (JSON)
  - /metrics  → Prometheus metrics
  - /api/sensors → live sensor data (JSON)
"""

import time
import math
import random
import logging
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ── Prometheus client ────────────────────────────────────────────────────────
from prometheus_client import (
    Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("robot-sensor-monitor")

# ── Metrics ──────────────────────────────────────────────────────────────────
REQUEST_COUNT   = Counter("http_requests_total",      "Total HTTP requests",      ["method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency",   ["path"])
SENSOR_TEMP     = Gauge("robot_sensor_temperature_celsius",  "Robot CPU temperature")
SENSOR_BATTERY  = Gauge("robot_battery_level_percent",       "Robot battery level")
SENSOR_VELOCITY = Gauge("robot_velocity_ms",                 "Robot linear velocity m/s")
SENSOR_MESSAGES = Counter("robot_ros2_messages_total",       "Simulated ROS2 messages published")
UPTIME_SECONDS  = Gauge("robot_uptime_seconds",              "Application uptime in seconds")

START_TIME = time.time()

# ── Sensor simulation ────────────────────────────────────────────────────────
_state = {
    "temperature": 42.0,
    "battery":     87.0,
    "velocity":    0.0,
    "heading":     0.0,
    "msg_count":   0,
    "lidar_points": 360,
}

def _simulate_sensors():
    """Background thread: update simulated sensor values every second."""
    t = 0
    while True:
        _state["temperature"] = 42.0 + 8.0 * math.sin(t / 30) + random.uniform(-0.5, 0.5)
        _state["battery"]     = max(0.0, min(100.0, _state["battery"] - 0.01 + random.uniform(-0.02, 0.015)))
        _state["velocity"]    = max(0.0, 1.5 * abs(math.sin(t / 10)) + random.uniform(-0.1, 0.1))
        _state["heading"]     = (_state["heading"] + 2.5) % 360
        _state["lidar_points"] = random.randint(340, 380)
        _state["msg_count"]   += 1

        SENSOR_TEMP.set(_state["temperature"])
        SENSOR_BATTERY.set(_state["battery"])
        SENSOR_VELOCITY.set(_state["velocity"])
        SENSOR_MESSAGES.inc()
        UPTIME_SECONDS.set(time.time() - START_TIME)

        t += 1
        time.sleep(1)

# ── HTML dashboard ────────────────────────────────────────────────────────────
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Robot Sensor Monitor</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@500;700&display=swap');
  :root {
    --bg: #0a0e1a; --card: #111827; --border: #1e3a5f;
    --accent: #00d4ff; --warn: #ff6b35; --ok: #39ff14;
    --text: #c8d8f0; --dim: #4a6080;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Share Tech Mono', monospace; min-height: 100vh; padding: 24px; }
  header { text-align: center; margin-bottom: 32px; }
  header h1 { font-family: 'Orbitron', sans-serif; font-size: 1.8rem; color: var(--accent); letter-spacing: 4px; text-transform: uppercase; }
  header p { color: var(--dim); font-size: 0.8rem; margin-top: 6px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; max-width: 1000px; margin: 0 auto; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; position: relative; overflow: hidden; }
  .card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, transparent, var(--accent), transparent); }
  .card-label { font-size: 0.7rem; color: var(--dim); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; }
  .card-value { font-family: 'Orbitron', sans-serif; font-size: 2rem; color: var(--accent); }
  .card-unit  { font-size: 0.75rem; color: var(--dim); margin-left: 4px; }
  .bar-wrap { background: #0d1b2a; border-radius: 4px; height: 8px; margin-top: 12px; overflow: hidden; }
  .bar { height: 100%; border-radius: 4px; transition: width 0.8s ease; }
  .bar-temp { background: linear-gradient(90deg, #00d4ff, #ff6b35); }
  .bar-bat  { background: linear-gradient(90deg, #ff2244, #39ff14); }
  #status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 8px var(--ok); animation: pulse 2s infinite; margin-right: 6px; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  footer { text-align: center; margin-top: 32px; font-size: 0.7rem; color: var(--dim); }
  a { color: var(--accent); text-decoration: none; }
</style>
</head>
<body>
<header>
  <h1>🤖 Robot Sensor Monitor</h1>
  <p><span id="status-dot"></span>LIVE – ROS2 Jazzy Demo &nbsp;|&nbsp; <span id="clock"></span></p>
</header>
<div class="grid">
  <div class="card">
    <div class="card-label">CPU Temperature</div>
    <div><span class="card-value" id="temp">--</span><span class="card-unit">°C</span></div>
    <div class="bar-wrap"><div class="bar bar-temp" id="temp-bar" style="width:0%"></div></div>
  </div>
  <div class="card">
    <div class="card-label">Battery Level</div>
    <div><span class="card-value" id="battery">--</span><span class="card-unit">%</span></div>
    <div class="bar-wrap"><div class="bar bar-bat" id="bat-bar" style="width:0%"></div></div>
  </div>
  <div class="card">
    <div class="card-label">Linear Velocity</div>
    <div><span class="card-value" id="velocity">--</span><span class="card-unit">m/s</span></div>
  </div>
  <div class="card">
    <div class="card-label">Heading</div>
    <div><span class="card-value" id="heading">--</span><span class="card-unit">°</span></div>
  </div>
  <div class="card">
    <div class="card-label">LiDAR Points/Scan</div>
    <div><span class="card-value" id="lidar">--</span><span class="card-unit">pts</span></div>
  </div>
  <div class="card">
    <div class="card-label">ROS2 Messages</div>
    <div><span class="card-value" id="msgs">--</span><span class="card-unit">total</span></div>
  </div>
</div>
<footer>
  <a href="/metrics">/metrics</a> &nbsp;·&nbsp;
  <a href="/health">/health</a> &nbsp;·&nbsp;
  <a href="/api/sensors">/api/sensors</a>
</footer>
<script>
async function refresh() {
  try {
    const r = await fetch('/api/sensors');
    const d = await r.json();
    document.getElementById('temp').textContent     = d.temperature_c.toFixed(1);
    document.getElementById('battery').textContent  = d.battery_pct.toFixed(1);
    document.getElementById('velocity').textContent = d.velocity_ms.toFixed(2);
    document.getElementById('heading').textContent  = d.heading_deg.toFixed(0);
    document.getElementById('lidar').textContent    = d.lidar_points;
    document.getElementById('msgs').textContent     = d.ros2_msg_count;
    document.getElementById('temp-bar').style.width   = Math.min(100, (d.temperature_c / 80) * 100) + '%';
    document.getElementById('bat-bar').style.width    = d.battery_pct + '%';
  } catch(e) { console.error(e); }
}
function clock() {
  document.getElementById('clock').textContent = new Date().toUTCString();
}
refresh(); clock();
setInterval(refresh, 1500);
setInterval(clock, 1000);
</script>
</body>
</html>"""

# ── HTTP handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):   # redirect to our logger
        log.info("HTTP %s %s", self.address_string(), fmt % args)

    def _respond(self, status, content_type, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        t0   = time.time()

        if path == "/":
            body = DASHBOARD_HTML.encode()
            self._respond(200, "text/html; charset=utf-8", body)
            status = "200"

        elif path == "/health":
            import json
            data   = {"status": "ok", "uptime_s": round(time.time() - START_TIME, 1),
                      "timestamp": datetime.now(timezone.utc).isoformat()}
            body   = json.dumps(data).encode()
            self._respond(200, "application/json", body)
            status = "200"

        elif path == "/api/sensors":
            import json
            data = {
                "temperature_c": round(_state["temperature"], 2),
                "battery_pct":   round(_state["battery"],     2),
                "velocity_ms":   round(_state["velocity"],    3),
                "heading_deg":   round(_state["heading"],     1),
                "lidar_points":  _state["lidar_points"],
                "ros2_msg_count": _state["msg_count"],
                "timestamp":     datetime.now(timezone.utc).isoformat(),
            }
            body = json.dumps(data).encode()
            self._respond(200, "application/json", body)
            status = "200"

        elif path == "/metrics":
            body = generate_latest()
            self._respond(200, CONTENT_TYPE_LATEST, body)
            status = "200"

        else:
            body = b"404 Not Found"
            self._respond(404, "text/plain", body)
            status = "404"

        elapsed = time.time() - t0
        REQUEST_COUNT.labels(method="GET", path=path, status=status).inc()
        REQUEST_LATENCY.labels(path=path).observe(elapsed)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))

    log.info("Starting sensor simulation thread …")
    t = threading.Thread(target=_simulate_sensors, daemon=True)
    t.start()

    log.info("Robot Sensor Monitor listening on port %d", port)
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()
