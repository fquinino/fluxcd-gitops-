#!/usr/bin/env bash
set -euo pipefail

# Creates/updates Docker Hub registry auth secrets required by:
# 1) Flux image-reflector-controller in flux-system
# 2) Workload pulls in default namespace
#
# Required env vars:
#   DOCKERHUB_USERNAME
#   DOCKERHUB_TOKEN
#
# Optional env vars:
#   KUBECONFIG
#   APP_NAMESPACE (default: default)

APP_NAMESPACE="${APP_NAMESPACE:-default}"

if [[ -z "${DOCKERHUB_USERNAME:-}" || -z "${DOCKERHUB_TOKEN:-}" ]]; then
  echo "ERROR: set DOCKERHUB_USERNAME and DOCKERHUB_TOKEN in your shell first."
  echo "Example:"
  echo "  export DOCKERHUB_USERNAME=fquinino"
  echo "  export DOCKERHUB_TOKEN='<token>'"
  exit 1
fi

create_secret() {
  local namespace="$1"
  kubectl create secret docker-registry dockerhub-auth \
    -n "${namespace}" \
    --docker-server=https://index.docker.io/v1/ \
    --docker-username="${DOCKERHUB_USERNAME}" \
    --docker-password="${DOCKERHUB_TOKEN}" \
    --docker-email="you@example.com" \
    --dry-run=client -o yaml | kubectl apply -f -
}

echo "Applying dockerhub-auth in namespaces: flux-system and ${APP_NAMESPACE}"
create_secret flux-system
create_secret "${APP_NAMESPACE}"

echo "Reconciling Flux image resources..."
flux reconcile image repository demo -n flux-system
flux reconcile image policy demo -n flux-system
flux reconcile image update demo -n flux-system
flux reconcile kustomization apps -n flux-system

echo "Done. Current status:"
flux get image repository demo -n flux-system || true
flux get image policy demo -n flux-system || true
kubectl get pods -n "${APP_NAMESPACE}" || true
