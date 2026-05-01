# 🤖 Robot Sensor Monitor – DevOps Assignment

A production-grade CI/CD demonstration using a **ROS2-style** robot sensor monitoring application.

## Architecture Overview

```
GitHub Push
    │
    ▼
┌──────────────────────────────────────────────────┐
│              GitHub Actions CI/CD                │
│  lint → test → build-docker → security-scan      │
└────────────────────┬─────────────────────────────┘
                     │ push image
                     ▼
              GHCR (Container Registry)
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│           Kubernetes (k8s/deployment.yaml)       │
│  Deployment | Service | Ingress (TLS) | HPA      │
└───────────┬──────────────────────────────────────┘
            │ scrape /metrics
            ▼
┌──────────────────────────────────────────────────┐
│              Monitoring Stack                    │
│  Prometheus → Grafana dashboards                 │
│  Loki + Promtail → Log aggregation               │
└──────────────────────────────────────────────────┘
```

## Project Structure

```
ros2-devops/
├── .github/
│   └── workflows/
│       └── ci-cd.yml          ← GitHub Actions pipeline
├── app/
│   ├── main.py                ← Robot Sensor Monitor app
│   ├── requirements.txt
│   └── tests/
│       └── test_main.py       ← 12 unit + integration tests
├── docker/
│   └── Dockerfile             ← Multi-stage, non-root, minimal
├── k8s/
│   └── deployment.yaml        ← Full K8s spec (Deployment, Service, Ingress, HPA, NetworkPolicy)
├── monitoring/
│   ├── prometheus/
│   │   └── prometheus.yml     ← Prometheus scrape config
│   ├── loki/
│   │   └── promtail.yml       ← Log shipping config
│   └── grafana/
│       ├── datasources/       ← Auto-provisioned Prometheus + Loki
│       ├── dashboards/        ← Pre-built robot dashboard JSON
│       └── dashboards.yaml
├── scripts/
│   └── local-run.sh           ← Quick local run script
├── docker-compose.yml         ← Full local stack (app + monitoring)
└── README.md
```

## Quick Start (Local)

### Option 1 – Run app only
```bash
pip install -r app/requirements.txt
python app/main.py
# Open: http://localhost:8080
```

### Option 2 – Full stack with monitoring
```bash
docker compose up --build
# App:        http://localhost:8080
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000  (admin/admin)
```

### Run tests
```bash
pip install -r app/requirements.txt
pytest app/tests/ -v --cov=app
```

## CI/CD Pipeline (GitHub Actions)

| Job | Trigger | What it does |
|-----|---------|-------------|
| `lint` | Every push/PR | flake8 static analysis |
| `test` | After lint | pytest (12 tests) + coverage XML + JUnit XML artifacts |
| `build-and-push` | Push to `main` only | Multi-arch Docker build (amd64 + arm64), push to GHCR |
| `security-scan` | After push | Trivy vulnerability scan → GitHub Security tab |
| `notify` | On any failure | Slack webhook alert |

### Secrets required
| Secret | Purpose |
|--------|---------|
| `GITHUB_TOKEN` | Auto-provided; used for GHCR push |
| `SLACK_WEBHOOK_URL` | Optional; failure notifications |

## Application Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Live HTML sensor dashboard |
| `GET /health` | JSON health check (used by K8s probes) |
| `GET /metrics` | Prometheus metrics exposition |
| `GET /api/sensors` | Raw JSON sensor data |

## Kubernetes Deployment

```bash
# Replace image name in k8s/deployment.yaml, then:
kubectl apply -f k8s/deployment.yaml

# Verify
kubectl get all -n robotics
kubectl describe ingress robot-sensor-monitor -n robotics
```

### TLS Handling
The Ingress is configured for **cert-manager + Let's Encrypt**:
1. Install cert-manager: `helm install cert-manager jetstack/cert-manager --set installCRDs=true`
2. Create a `ClusterIssuer` for Let's Encrypt
3. Update `host:` in `k8s/deployment.yaml` to your domain
4. cert-manager auto-provisions the certificate; nginx redirects HTTP→HTTPS

## Monitoring

### Metrics (Prometheus + Grafana)
- `robot_sensor_temperature_celsius` – CPU temperature gauge
- `robot_battery_level_percent` – Battery level gauge
- `robot_velocity_ms` – Linear velocity gauge
- `robot_ros2_messages_total` – Counter of simulated ROS2 messages
- `http_requests_total` – HTTP request counter by path/status
- `http_request_duration_seconds` – Latency histogram

Pre-built Grafana dashboard is auto-provisioned at startup (Grafana → Robotics folder).

### Logs (Loki + Promtail)
All Docker container logs are shipped to Loki via Promtail.
Query in Grafana: `{job="robot-sensor-monitor"}`

## Security Design

- **Non-root container**: `USER robot` in Dockerfile
- **Read-only filesystem**: `readOnlyRootFilesystem: true` in K8s
- **Dropped capabilities**: `capabilities.drop: [ALL]`
- **NetworkPolicy**: Default-deny; only ingress-nginx and Prometheus can reach the pod
- **Multi-stage Dockerfile**: No build tools in runtime image
- **Trivy scan**: CRITICAL/HIGH CVEs fail the pipeline
- **TLS everywhere**: HTTPS enforced by Ingress, HSTS header set

## What I Would Add for Production

1. **GitOps with ArgoCD** – Declarative deployment; git is the source of truth
2. **Alertmanager rules** – PagerDuty/Slack alerts on battery < 20%, temp > 70°C
3. **OpenTelemetry tracing** – Distributed traces alongside metrics + logs
4. **SBOM generation** – Syft in CI pipeline for software bill of materials
5. **Signed images** – Cosign to cryptographically sign Docker images
6. **Secret management** – External Secrets Operator + HashiCorp Vault
7. **Multi-environment** – dev / staging / prod namespaces via Kustomize overlays
8. **ROS2 colcon build** – Real `colcon build --symlink-install` + `colcon test` in CI
9. **Integration tests in K8s** – Spin up a test namespace, run integration suite, tear down
10. **SLO dashboards** – Error budget tracking in Grafana

## AI Usage Disclosure

This solution was designed collaboratively with Claude (Anthropic). AI was used to:
- Scaffold the project structure and boilerplate YAML
- Generate Grafana dashboard JSON
- Draft documentation

All architectural decisions, technology choices, and security design were reviewed and validated by the developer.
