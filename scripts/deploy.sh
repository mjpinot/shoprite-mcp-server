#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy.sh – Build, push, and deploy the Shoprite MCP Server
# Usage: ./scripts/deploy.sh [dev|prod] [image-tag]
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV="${1:-dev}"
TAG="${2:-latest}"
REGISTRY="${DOCKER_REGISTRY:-ghcr.io/mjpinot}"
IMAGE="${REGISTRY}/shoprite-mcp-server:${TAG}"

cd "${PROJECT_DIR}"

echo "▶  Environment : ${ENV}"
echo "▶  Image       : ${IMAGE}"

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
echo ""
echo "==> Building Docker image…"
docker build \
    --tag "${IMAGE}" \
    --tag "${REGISTRY}/shoprite-mcp-server:latest" \
    --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --build-arg VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" \
    .

# ---------------------------------------------------------------------------
# Push (only in prod mode)
# ---------------------------------------------------------------------------
if [[ "${ENV}" == "prod" ]]; then
    echo ""
    echo "==> Pushing image to registry…"
    docker push "${IMAGE}"
    docker push "${REGISTRY}/shoprite-mcp-server:latest"
fi

# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------
if [[ "${ENV}" == "dev" ]]; then
    echo ""
    echo "==> Starting development stack…"
    docker compose -f docker-compose.yml up -d --force-recreate

elif [[ "${ENV}" == "prod" ]]; then
    echo ""
    echo "==> Deploying to Kubernetes…"
    kubectl apply -k k8s/
    kubectl rollout status deployment/shoprite-mcp-server \
        -n shoprite-mcp --timeout=5m

else
    echo "ERROR: Unknown environment '${ENV}'. Use 'dev' or 'prod'."
    exit 1
fi

echo ""
echo "✅  Deploy complete."
