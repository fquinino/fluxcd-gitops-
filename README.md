# FluxCD GitOps with CI/CD Demo Templates

This directory contains the templates and files required to set up a FluxCD GitOps demo for your clients.

## Directory Structure

* **`app-source-repo/`**: The source code repository containing:
  - A simple Go web application using Gin (`main.go`).
  - A multi-stage `Dockerfile` to build the app image.
  - A GitHub Actions workflow (`.github/workflows/docker-image.yml`) to automatically build and push new images to Docker Hub.
* **`gitops-config-repo/`**: The GitOps repository containing:
  - The application manifests (`apps/demo.yaml`) with policy comment markers.
  - The FluxCD Image Automation manifests (`flux-system/`): `imagerepository_demo.yaml`, `imagepolicy_demo.yaml`, and `imageupdateautomation_demo.yaml`.
  - A Flux Kustomization (`flux-system/apps.yaml`) that binds the app sync to the cluster.

## Getting Started

Please see **`fluxcd_lab_guide.md`** in this folder for the step-by-step instructions on setting up and running this lab demo.
# fluxcd-gitops-
# fluxcd-lab
