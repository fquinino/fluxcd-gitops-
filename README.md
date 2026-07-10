# FluxCD GitOps Lab Templates

This repository contains a complete, practical FluxCD lab that demonstrates:

- pull-based GitOps reconciliation,
- GitHub App authentication (default and recommended),
- image automation from Docker Hub back into Git, and
- end-to-end Kubernetes deployment reconciliation.

## Why FluxCD (Pull-Based GitOps)

Flux runs inside your cluster and continuously compares:

- desired state in Git, vs
- actual state in Kubernetes.

When drift is detected (manual change, deleted workload, failed rollout), Flux reconciles the cluster back to Git. This makes Git the single source of truth and avoids external CD systems pushing directly into the cluster.

## How Flux Works Under the Hood

Core loop:

1. Developer pushes code/manifests to Git.
2. `source-controller` pulls and snapshots repository content.
3. `kustomize-controller` and/or `helm-controller` apply desired state.
4. Controllers continuously reconcile and self-heal drift.
5. Optional `notification-controller` sends deployment events and can receive webhooks for fast reconcile.

## How GitHub App Auth Works with Flux

This lab uses GitHub App auth by default (no long-lived deploy key or PAT in cluster):

1. Flux reads `githubAppID`, `githubAppInstallationID`, and `githubAppPrivateKey` from a Kubernetes Secret.
2. `source-controller` signs a short-lived JWT with the private key.
3. Flux exchanges JWT with GitHub API for an installation access token.
4. Flux performs authenticated Git HTTPS fetch/clone with that token.
5. Flux refreshes tokens automatically before expiration.

Security benefits:

- short-lived scoped credentials,
- least privilege at repo/org level,
- simpler rotation by replacing app private key and reconciling.

## Repository Structure

- `app-source-repo/`
  - Demo Go app (`main.go`)
  - `Dockerfile`
  - GitHub Actions workflow for build/push
- `gitops-config-repo/`
  - App manifests (`apps/`)
  - Flux image automation manifests (`flux-system/`)
  - Federated phase-2 manifests (`federation-phase2/`)
- `scripts/`
  - optional helper scripts (manual YAML flow is primary)
- `fluxcd_lab_guide.md`
  - full step-by-step lab guide

## Quick Start

Follow `fluxcd_lab_guide.md`.

The default path in the guide is now:

1. create GitHub App secret,
2. use existing NKP Flux controllers in `kommander-flux`,
3. create lab `GitRepository`/`Kustomization` with `provider: github` and `secretRef`,
4. reconcile and validate sources/kustomizations.

For Docker image automation, the guide also configures registry auth on both paths:
- Flux scan auth (`kommander-flux/dockerhub-auth`) for `ImageRepository`
- workload pull auth (`<app-namespace>/dockerhub-auth`) for pod image pulls
- SOPS + age encryption so only encrypted secret manifests are committed
