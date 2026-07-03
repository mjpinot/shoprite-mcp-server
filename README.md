# 🛒 Shoprite MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that exposes
**Shoprite** product data, weekly deals, and store locations as tools and resources
consumable by AI assistants such as Claude, Cursor, and any MCP-compatible client.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start (local)](#quick-start-local)
- [Docker Compose](#docker-compose)
- [Kubernetes](#kubernetes)
- [Production Deployment](#production-deployment)
- [Configuration](#configuration)
- [Available MCP Tools](#available-mcp-tools)
- [Available MCP Resources](#available-mcp-resources)
- [CI/CD](#cicd)
- [Monitoring (Prometheus + Grafana + Alertmanager)](#monitoring-prometheus--grafana--alertmanager)
- [Development](#development)
- [Project Structure](#project-structure)
- [License](#license)

---

## Features

| Capability | Description |
|---|---|
| 🔍 **Product Search** | Search Shoprite products by keyword |
| 💰 **Weekly Deals** | Fetch current weekly specials and sale prices |
| 📍 **Store Finder** | Look up store locations by ZIP code |
| 🛍️ **Product Details** | Retrieve full details from a product page |
| 🐳 **Docker Compose** | Single-command local stack with Nginx and Redis |
| ☸️ **Kubernetes** | Production-grade manifests with HPA, PDB, and NetworkPolicy |
| 🔄 **CI/CD** | GitHub Actions pipeline: lint → test → build → deploy |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     AI Client                           │
│  (Claude Desktop / Cursor / any MCP-compatible tool)   │
└────────────────────────┬────────────────────────────────┘
                         │ MCP over SSE (HTTP)
                         ▼
              ┌──────────────────┐
              │   Nginx Proxy    │  :80 / :443
              └────────┬─────────┘
                       │
              ┌────────▼─────────┐
              │   MCP Proxy      │  stdio ↔ HTTP/SSE bridge
              └────────┬─────────┘
                       │ stdio
              ┌────────▼─────────┐
              │   MCP Server     │  Python (mcp + httpx + bs4)
              │  (src/server.py) │
              └────────┬─────────┘
                       │ HTTPS
              ┌────────▼─────────┐
              │  shoprite.com    │
              └──────────────────┘
```

---

## Quick Start (local)

### Prerequisites

- Python 3.11+
- Docker 24+
- Docker Compose v2

### Run without Docker

```bash
# Clone the repository
git clone https://github.com/mjpinot/shoprite-mcp-server.git
cd shoprite-mcp-server

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Run the server (communicates over stdio)
python -m src.server
```

---

## Docker Compose

```bash
# Copy environment file and edit if needed
cp .env.example .env

# Build and start all services (mcp-server, mcp-proxy, nginx, redis)
docker compose up -d

# Follow logs
docker compose logs -f mcp-server

# Stop
docker compose down
```

### Services

| Service | Port | Description |
|---|---|---|
| `mcp-server` | — | Python MCP server (stdio) |
| `mcp-proxy` | 9090 | SSE bridge (stdio ↔ HTTP) |
| `nginx` | 80 | Reverse proxy / rate limiter |
| `redis` | 6379 | Optional caching layer |

### Connect Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "shoprite": {
      "url": "http://localhost:9090/sse"
    }
  }
}
```

---

## Kubernetes

### Prerequisites

- `kubectl` configured for your cluster
- `kustomize` (bundled with `kubectl` >= 1.14)
- Container registry access

### Deploy

```bash
# 1. Create the namespace and all resources
kubectl apply -k k8s/

# 2. Watch rollout
kubectl rollout status deployment/shoprite-mcp-server -n shoprite-mcp

# 3. Check pods
kubectl get pods -n shoprite-mcp
```

### Customize the image tag

```bash
cd k8s
kustomize edit set image \
  ghcr.io/mjpinot/shoprite-mcp-server=ghcr.io/mjpinot/shoprite-mcp-server:v1.2.0
kubectl apply -k .
```

### Included manifests

| File | Description |
|---|---|
| `namespace.yaml` | Dedicated `shoprite-mcp` namespace |
| `serviceaccount.yaml` | ServiceAccount + Role + RoleBinding |
| `configmap.yaml` | Non-secret runtime configuration |
| `secret.yaml` | Sensitive credentials (use Sealed Secrets in prod) |
| `deployment.yaml` | 2-replica Deployment with probes + security context |
| `service.yaml` | ClusterIP Service (HTTP + SSE ports) |
| `ingress.yaml` | Nginx Ingress with SSE support |
| `hpa.yaml` | HPA: scale 2–10 replicas on CPU/memory |
| `networkpolicy.yaml` | Restrict ingress/egress to required paths only |
| `pdb.yaml` | PodDisruptionBudget: minAvailable=1 |
| `kustomization.yaml` | Kustomize bundle |

---

## Production Deployment

### Docker Compose (production override)

```bash
# Start with production overrides (pulls from registry, removes volume mounts)
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d
```

### TLS with Let's Encrypt

1. Point your domain (e.g. `mcp.yourdomain.com`) to your server.
2. Install [certbot](https://certbot.eff.org/):
   ```bash
   certbot certonly --standalone -d mcp.yourdomain.com
   ```
3. Uncomment the HTTPS server block in `nginx/conf.d/mcp.conf`.
4. Restart Nginx: `docker compose restart nginx`.

### Kubernetes secrets management

For production use [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)
or [External Secrets Operator](https://external-secrets.io/) instead of plain `secret.yaml`:

```bash
# Example: seal the secret
kubeseal --format yaml < k8s/secret.yaml > k8s/sealed-secret.yaml
```

### Deploy script

```bash
# Local dev stack
./scripts/deploy.sh dev

# Build, push, and deploy to Kubernetes
./scripts/deploy.sh prod v1.0.0
```

---

## Configuration

All settings can be provided as environment variables or in a `.env` file.

| Variable | Default | Description |
|---|---|---|
| `SHOPRITE_BASE_URL` | `https://www.shoprite.com` | Base URL for scraping |
| `REQUEST_TIMEOUT` | `30` | HTTP timeout in seconds |
| `MAX_PRODUCTS` | `50` | Maximum products returned per request |
| `MCP_PORT` | `8080` | Port for the MCP server container |
| `PROXY_PORT` | `9090` | Port for the SSE proxy container |
| `REDIS_PASSWORD` | `changeme` | Redis authentication password |
| `DOCKER_REGISTRY` | `ghcr.io/mjpinot` | Image registry for production |
| `IMAGE_TAG` | `latest` | Docker image tag to deploy |

---

## Available MCP Tools

### `search_products`

Search Shoprite products by keyword.

**Input:**
```json
{
  "query": "chicken breast",
  "max_results": 10
}
```

**Output:** Formatted list with product name, price, and URL.

---

### `get_weekly_deals`

Retrieve current weekly deals and specials.

**Input:**
```json
{
  "max_results": 20
}
```

**Output:** Formatted list of sale items with prices.

---

### `get_store_locations`

Find Shoprite stores near a ZIP code.

**Input:**
```json
{
  "zip_code": "07030"
}
```

**Output:** Store names, addresses, phone numbers, and hours.

---

### `get_product_details`

Get detailed information for a specific product.

**Input:**
```json
{
  "product_url": "https://www.shoprite.com/sm/planning/rsid/3000/product/..."
}
```

**Output:** Title, price, description, and URL.

---

## Available MCP Resources

| URI | Name | Description |
|---|---|---|
| `https://www.shoprite.com` | Shoprite Homepage | Main website |
| `https://www.shoprite.com/savings/weekly-specials` | Weekly Specials | Current deals |
| `https://www.shoprite.com/store-finder` | Store Finder | Location search |

---

## CI/CD

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push to `main`
and on version tags (`v*.*.*`):

```
push to main / PR
     │
     ▼
┌──────────┐    ┌───────────────┐    ┌─────────────────┐
│  Lint &  │───▶│  Build &      │───▶│  Deploy to K8s  │
│  Test    │    │  Push Image   │    │  (tags only)    │
└──────────┘    └───────────────┘    └─────────────────┘
```

### Required secrets

| Secret | Description |
|---|---|
| `GITHUB_TOKEN` | Auto-provided by GitHub Actions for GHCR push |
| `KUBECONFIG` | Base64-encoded kubeconfig for Kubernetes deployment |

---

## Development

### Install dev dependencies

```bash
pip install -r requirements.txt ruff mypy pytest pytest-asyncio
```

### Lint

```bash
ruff check src/
```

### Type check

```bash
mypy src/ --ignore-missing-imports
```

### Run tests

```bash
pytest tests/ -v
```

### Run a single tool manually

```bash
# Using the MCP inspector (https://github.com/modelcontextprotocol/inspector)
npx @modelcontextprotocol/inspector python -m src.server
```

---

## Project Structure

```
shoprite-mcp-server/
├── src/
│   ├── __init__.py
│   └── server.py            # MCP server + Prometheus metrics endpoint
├── k8s/
│   ├── namespace.yaml
│   ├── serviceaccount.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── hpa.yaml
│   ├── networkpolicy.yaml
│   ├── pdb.yaml
│   ├── kustomization.yaml
│   └── monitoring/
│       ├── prometheus-rbac.yaml
│       ├── prometheus-configmap.yaml    # scrape config + 8 alert rules
│       ├── prometheus-deployment.yaml
│       ├── alertmanager-secret.yaml     # Slack webhook + SMTP password
│       ├── alertmanager-configmap.yaml  # routing + receiver config
│       ├── alertmanager-deployment.yaml
│       ├── grafana-secret.yaml          # admin credentials
│       ├── grafana-datasources.yaml
│       ├── grafana-dashboard.yaml       # 11-panel dashboard
│       ├── grafana-deployment.yaml
│       └── servicemonitor.yaml          # for kube-prometheus-stack
├── nginx/
│   ├── nginx.conf
│   └── conf.d/
│       └── mcp.conf
├── scripts/
│   └── deploy.sh
├── .github/
│   └── workflows/
│       └── ci.yml
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

---

## Monitoring (Prometheus + Grafana + Alertmanager)

### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Namespace: shoprite-mcp                       │
│                                                                  │
│  ┌──────────────┐   /metrics   ┌─────────────┐                  │
│  │  MCP Server  │◄─────────────│  Prometheus │──► AlertManager  │
│  │  :9090       │              │  :9090      │    :9093          │
│  └──────────────┘              └──────┬──────┘                  │
│                                       │ datasource              │
│                                ┌──────▼──────┐                  │
│                                │   Grafana   │                  │
│                                │   :3000     │                  │
│                                └─────────────┘                  │
└──────────────────────────────────────────────────────────────────┘
         AlertManager ──► Slack (#shoprite-alerts / #shoprite-critical)
                      ──► Email (oncall@yourdomain.com)
```

### Exposed Metrics

| Metric | Type | Description |
|---|---|---|
| `shoprite_mcp_tool_calls_total` | Counter | Total tool calls, labeled `tool` + `status` (success/error) |
| `shoprite_mcp_tool_call_duration_seconds` | Histogram | Latency per tool call |
| `shoprite_mcp_http_request_duration_seconds` | Histogram | Latency of outbound HTTP scrapes to shoprite.com |
| `shoprite_mcp_http_errors_total` | Counter | HTTP errors by `url_path` and `error_type` |
| `shoprite_mcp_products_returned` | Histogram | Products returned per search |
| `shoprite_mcp_active_tool_calls` | Gauge | In-flight tool calls |
| `shoprite_mcp_info` | Info | Server version and base URL |

Metrics are available at `http://<pod-ip>:9090/metrics`.

### Deploy the monitoring stack

```bash
# Deploy everything (app + monitoring) in one shot
kubectl apply -k k8s/

# Check all pods are running
kubectl get pods -n shoprite-mcp

# Port-forward to Grafana (no Ingress needed for local access)
kubectl port-forward svc/grafana 3000:3000 -n shoprite-mcp
# Open http://localhost:3000  — admin / <password from grafana-secret.yaml>

# Port-forward to Prometheus UI
kubectl port-forward svc/prometheus 9090:9090 -n shoprite-mcp
# Open http://localhost:9090

# Port-forward to Alertmanager UI
kubectl port-forward svc/alertmanager 9093:9093 -n shoprite-mcp
# Open http://localhost:9093
```

### Grafana Dashboard

The dashboard **"Shoprite MCP Server"** is auto-provisioned at startup and includes:

| Panel | Description |
|---|---|
| Tool Calls/s | Request rate per tool |
| Tool Error Rate (%) | Error % with thresholds (yellow >10%, red >30%) |
| Tool p50/p95/p99 Latency | Latency percentiles per tool |
| Active Tool Calls | Real-time in-flight gauge |
| HTTP Scrape Errors/s | Error rate toward shoprite.com |
| Outbound HTTP Latency p95 | Upstream latency by URL path |
| Products Returned (avg) | Average products per search |
| Pod Memory / CPU | Container resource usage |
| Available Replicas | Deployment health |
| Firing Alerts | Live Alertmanager alert list |

### Alert Rules

| Alert | Severity | Condition |
|---|---|---|
| `ShopriteMcpHighErrorRate` | warning | Error rate > 10% for 2 min |
| `ShopriteMcpCriticalErrorRate` | critical | Error rate > 30% for 1 min |
| `ShopriteMcpHighLatency` | warning | p95 latency > 10s for 3 min |
| `ShopriteMcpHttpErrors` | warning | Scrape errors > 0.05/s for 2 min |
| `ShopriteMcpPodDown` | critical | 0 available replicas for 1 min |
| `ShopriteMcpReplicasMismatch` | warning | Desired ≠ available replicas for 5 min |
| `ShopriteMcpHighMemory` | warning | Memory > 85% of limit for 5 min |
| `ShopriteMcpHighCPU` | warning | CPU > 80% of limit for 5 min |

### Configure alert channels

**Slack:**
1. Create an Incoming Webhook in your Slack workspace.
2. Edit `k8s/monitoring/alertmanager-secret.yaml` and set `ALERTMANAGER_SLACK_WEBHOOK_URL`.
3. Update the channel names in `alertmanager-configmap.yaml` (`#shoprite-alerts`, `#shoprite-critical`, `#shoprite-mcp-team`).

**Email:**
1. Set `ALERTMANAGER_SMTP_PASSWORD` in `alertmanager-secret.yaml`.
2. Update `smtp_from`, `smtp_auth_username`, and the `to:` address in `alertmanager-configmap.yaml`.

> In production, replace plain `Secret` objects with [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)
> or [External Secrets Operator](https://external-secrets.io/) to avoid committing credentials.

### With kube-prometheus-stack (Prometheus Operator)

If your cluster already runs **kube-prometheus-stack**, use the `ServiceMonitor` instead
of deploying standalone Prometheus:

```bash
# 1. Skip the standalone Prometheus (comment it out in kustomization.yaml)
# 2. Apply only the ServiceMonitor:
kubectl apply -f k8s/monitoring/servicemonitor.yaml

# 3. Verify it's picked up:
kubectl get servicemonitor -n shoprite-mcp
```

The `ServiceMonitor` label `release: kube-prometheus-stack` must match the
`serviceMonitorSelector` configured in your Prometheus Operator instance.

---

## License

MIT © 2026 mjpinot

> **Disclaimer:** This project is not affiliated with or endorsed by ShopRite Supermarkets.
> Scraping shoprite.com is subject to their [Terms of Service](https://www.shoprite.com/sm/planning/rsid/3000/legal).
> Use responsibly and respect `robots.txt` and rate limits.
