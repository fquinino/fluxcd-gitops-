# Lab Guide: Automated GitOps CI/CD with FluxCD & GitHub Actions

Welcome to the FluxCD GitOps & CI/CD Demo Lab! This guide walks you through setting up an automated deployment pipeline. When developers push code to GitHub, GitHub Actions will compile and build a Docker container image, push it to Docker Hub, and FluxCD will automatically detect the new image version, write the updated tag back to Git, and reconcile the Kubernetes cluster.

---

## 1. Flow Overview

### Visual Workflow (Mermaid)

```mermaid
flowchart TD
    A[Developer Commit] --> B[GitHub Repository]
    B --> C[GitHub Actions Build]
    C --> D[Docker Hub Push]
    D --> E[Flux ImageRepository Scan]
    E --> F[Flux ImagePolicy Resolve Tag]
    F --> G[Flux ImageUpdateAutomation Commit]
    G --> B
    B --> H[Flux Source Controller]
    H --> I[Flux Kustomization Apply]
    I --> J[Kubernetes Deployment Rollout]
```

This workflow shows the closed GitOps loop: CI pushes image, Flux updates Git, and cluster state converges from Git.

### Text Workflow

```text
  ┌────────────────┐
  │  Source Repo   │  (go-app-source)
  └───────┬────────┘
          │ git push (e.g. main.go update)
          ▼
  ┌────────────────┐
  │ GitHub Actions │  (CI Workflow)
  │ - Build Image  │
  │ - Push Image   │
  └───────┬────────┘
          │ image tag (e.g., v1.0.1)
          ▼
  ┌────────────────┐
  │   Docker Hub   │  (Container Registry)
  │ (docker.io)    │
  └───────┬────────┘
          │
          │ (1) Scan registry for new tags
          ▼
  ┌────────────────┐      (2) Commit & Push tag update
  │     FluxCD     ├─────────────────────────────────┐
  └───────┬────────┘                                 │
          │                                          ▼
          │ (3) Reconcile cluster state     ┌────────────────┐
          ▼                                 │  GitOps Repo   │ (yaml manifests)
  ┌────────────────┐                        └────────────────┘
  │   Kubernetes   │
  │  (Deploy App)  │
  └────────────────┘
```

### Key Components
1. **Source Code Repo (`go-app-source`)**: Contains our Go Gin application and GitHub Actions CI file.
2. **GitOps Config Repo (`flux-system-gitops`)**: Contains Kubernetes manifests and FluxCD automation configuration.
3. **Flux Image-Reflector-Controller**: Scans the Docker Hub registry for new tags matching a SemVer range.
4. **Flux Image-Automation-Controller**: Checks out the Git repository, replaces the image tag comment marker with the new tag, and commits/pushes the change back to the Git repository.

---

## 2. Prerequisites

* **Kubernetes Cluster**: A running cluster (like the Nutanix `nkp-pro` cluster).
* **Docker Hub Account**: A free account at [hub.docker.com](https://hub.docker.com). You will need your password or a Personal Access Token (recommended).
* **GitHub Account**: A GitHub account to host the two repositories.
* **GitHub App for Flux (Default in this lab)**:
  * App ID
  * Installation ID (app installed on the target repo/org)
  * App private key `.pem`

---

## 3. Step 1: Install the Flux CLI

To manage and configure Flux, download the Flux CLI on your local terminal or jumpbox:

```bash
# On macOS
brew install fluxcd/tap/flux

# On Linux (Generic)
curl -s https://fluxcd.io/install.sh | sudo bash

# Verify installation
flux --version
```

---

## 4. Step 2: Create the GitHub Repositories

Create **two** repositories on GitHub:

1. **`go-app-source`** (Public or Private) - Source repository for the Go Gin app.
2. **`fluxcd-gitops-`** (Private) - Configuration repository for GitOps declarations.

---

## 5. Step 3: Install FluxCD with GitHub App Auth (Default)

This lab uses GitHub App authentication from the first setup, not as a later migration.

### Why this default is better

* Short-lived access tokens (auto-rotated by Flux)
* Least-privilege scoped repo access
* No long-lived SSH deploy key stored in cluster

### Under the hood (GitHub App auth flow)

1. Flux `source-controller` reads `githubAppID`, `githubAppInstallationID`, and `githubAppPrivateKey` from a Kubernetes secret.
2. Flux signs a short-lived JWT locally with the private key.
3. Flux exchanges the JWT with GitHub API for an installation access token.
4. Flux uses this short-lived token over HTTPS to fetch the Git repository.
5. Before token expiration, Flux transparently refreshes and keeps reconciling.

### 5.1 Install your GitHub App on the GitOps repository

Install your app on `fquinino/fluxcd-gitops-` (or your own target repo).

### 5.2 Export kubeconfig and install Flux controllers

```bash
export KUBECONFIG=/path/to/nkp-pro.conf

flux install \
  --components-extra=image-reflector-controller,image-automation-controller
```

### 5.3 Generate installation ID and apply secret + GitRepository patch

This repo includes a helper script:
`scripts/setup_github_app_auth.py`

```bash
python3 scripts/setup_github_app_auth.py \
  --app-id "<YOUR_APP_ID>" \
  --private-key "/path/to/github-app.private-key.pem" \
  --owner "<your-github-username>" \
  --repo "fluxcd-gitops-" \
  --namespace flux-system \
  --gitrepository flux-system \
  --apply
```

What this does:
* discovers the GitHub App installation ID for the target repo,
* creates/updates secret `github-app-auth`,
* patches `GitRepository/flux-system` with:
  * `spec.provider: github`
  * `spec.secretRef.name: github-app-auth`
* triggers a Flux source reconcile.

### 5.4 Create (or update) GitRepository if it does not exist yet

If you are installing from scratch and `GitRepository/flux-system` does not exist yet, apply this manifest first:

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: flux-system
  namespace: flux-system
spec:
  interval: 1m0s
  url: https://github.com/<your-github-username>/fluxcd-gitops-
  ref:
    branch: main
  provider: github
  secretRef:
    name: github-app-auth
```

Then reconcile:
```bash
flux reconcile source git flux-system -n flux-system
```

### 5.5 Validate source auth

```bash
flux get sources git -n flux-system
```

If `READY=True`, Flux source sync is healthy and using GitHub App credentials.

### Verify the Installation
Check that all controllers, including the image reflector and image automation controllers, are up and running:

```bash
kubectl get deployments -n flux-system
```

*Expected Output:*
```text
NAME                           READY   UP-TO-DATE   AVAILABLE   AGE
helm-controller                1/1     1            1           5m
image-automation-controller    1/1     1            1           5m
image-reflector-controller     1/1     1            1           5m
kustomize-controller           1/1     1            1           5m
notification-controller        1/1     1            1           5m
source-controller              1/1     1            1           5m
```

---

## 6. Step 4: Configure the GitOps Repository

Clone the `fluxcd-gitops-` repository locally (it will contain the bootstrapped `flux-system/gotk-*` files). We will now add our templates.

```bash
# Clone the repository
git clone git@github.com:<your-github-username>/fluxcd-gitops-.git
cd fluxcd-gitops-
```

Copy the contents of the `gitops-config-repo` template folder to your clone:

```bash
cp -r /path/to/fluxcd-demo-templates/gitops-config-repo/* ./
```

### Customize Manifest Placeholders
Replace `<dockerhub_username>` with your actual Docker Hub username in the following files:
* `apps/demo.yaml`
* `flux-system/imagerepository_demo.yaml`

For example:
```bash
# Using sed to quickly replace placeholders (Linux)
sed -i 's/<dockerhub_username>/your_docker_username/g' apps/demo.yaml
sed -i 's/<dockerhub_username>/your_docker_username/g' flux-system/imagerepository_demo.yaml
```

### Understand the Image Automation Declarations

1. **`flux-system/imagerepository_demo.yaml`**: Points Flux to scan your Docker Hub repository:
   ```yaml
   spec:
     image: docker.io/your_docker_username/demo
     interval: 1m
   ```

2. **`flux-system/imagepolicy_demo.yaml`**: Tells Flux how to filter tags. We use semantic versioning targeting versions `>=1.0.0`:
   ```yaml
   spec:
     imageRepositoryRef:
       name: demo
     policy:
       semver:
         range: ">=1.0.0"
   ```

3. **`flux-system/imageupdateautomation_demo.yaml`**: Links back to the Git repo and defines where to commit changes:
   ```yaml
   spec:
     git:
       checkout:
         ref:
           branch: main
       commit:
         author:
           name: flux-bot
           email: flux-bot@nutanix.com
         messageTemplate: 'chore(gitops): update image tags [skip ci]'
       push:
         branch: main
     update:
       strategy: Setters
   ```

4. **Image Tag Marker (`apps/demo.yaml`)**:
   Notice the comment marker inline next to the container image:
   ```yaml
   image: docker.io/your_docker_username/demo:1.0.0 # {"$imagepolicy": "flux-system:demo"}
   ```
   *This comment tells Flux exactly where to write the new image tag.*

### Commit and Push to GitHub

```bash
git add .
git commit -m "Configure Flux App Kustomization and Image Automation"
git push origin main
```

Within a minute, Flux will reconcile and apply these objects. Check status:
```bash
flux get kustomizations
```

---

## 7. Step 5: Configure the Go Application & GitHub Actions CI

Now, set up the source code repository.

```bash
# Change to a separate folder, clone your source repo
git clone git@github.com:<your-github-username>/go-app-source.git
cd go-app-source
```

Copy the template files from the `app-source-repo` folder:
```bash
cp -r /path/to/fluxcd-demo-templates/app-source-repo/* ./
cp -r /path/to/fluxcd-demo-templates/app-source-repo/.github ./
```

### Set up GitHub Secrets
Before pushing, you must configure Docker Hub credentials so GitHub Actions can push your build:
1. In your GitHub repository `go-app-source`, go to **Settings** > **Secrets and variables** > **Actions**.
2. Click **New repository secret**.
3. Create the secret `DOCKERHUB_USERNAME` and set it to your Docker Hub username.
4. Create the secret `DOCKERHUB_TOKEN` and set it to your Docker Hub Personal Access Token or password.

### Configure Docker Hub Auth for Both Pull Paths (Recommended)
Use the same `dockerhub-auth` secret name in both namespaces:
* `flux-system`: used by Flux `ImageRepository` scan auth.
* `default` (or app namespace): used by kubelet to pull the app image.

```bash
# Flux side: image-reflector-controller auth (namespace flux-system)
kubectl create secret docker-registry dockerhub-auth \
  -n flux-system \
  --docker-server=https://index.docker.io/v1/ \
  --docker-username="<dockerhub_username>" \
  --docker-password="<dockerhub_token>" \
  --docker-email="you@example.com" \
  --dry-run=client -o yaml | kubectl apply -f -

# Workload side: pod image pulls (namespace default)
kubectl create secret docker-registry dockerhub-auth \
  -n default \
  --docker-server=https://index.docker.io/v1/ \
  --docker-username="<dockerhub_username>" \
  --docker-password="<dockerhub_token>" \
  --docker-email="you@example.com" \
  --dry-run=client -o yaml | kubectl apply -f -
```

The demo deployment in this template references:
```yaml
spec:
  imagePullSecrets:
  - name: dockerhub-auth
```
so pod pulls and Flux image scans stay aligned on the same registry identity.

### (Recommended) Manage Docker Hub Auth with SOPS + age
This template includes encrypted-secret manifests:
* `gitops-config-repo/flux-system/dockerhub-auth-flux-system.secret.yaml`
* `gitops-config-repo/apps/dockerhub-auth-default.secret.yaml`

Flux decryption is enabled in `flux-system/gotk-sync.yaml`:
```yaml
spec:
  decryption:
    provider: sops
    secretRef:
      name: sops-age
```

#### 1) Install tools
```bash
brew install sops age
```

#### 2) Generate an age key pair
```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
```

Get the public key:
```bash
grep "^# public key:" ~/.config/sops/age/keys.txt | awk '{print $4}'
```

Update `.sops.yaml` with that public key (replace `age1REPLACE_WITH_YOUR_PUBLIC_KEY`).

#### 3) Create Flux decryption key in cluster
```bash
kubectl create secret generic sops-age \
  -n flux-system \
  --from-file=age.agekey=~/.config/sops/age/keys.txt
```

#### 4) Fill placeholders locally and encrypt before commit
```bash
export DOCKERHUB_USERNAME="<dockerhub_username>"
export DOCKERHUB_TOKEN="<dockerhub_token>"
export DOCKERHUB_AUTH="$(printf "%s" "${DOCKERHUB_USERNAME}:${DOCKERHUB_TOKEN}" | base64)"

for f in \
  gitops-config-repo/flux-system/dockerhub-auth-flux-system.secret.yaml \
  gitops-config-repo/apps/dockerhub-auth-default.secret.yaml; do
  sed -i '' "s/REPLACE_DOCKERHUB_USERNAME/${DOCKERHUB_USERNAME}/g" "$f"
  sed -i '' "s/REPLACE_DOCKERHUB_TOKEN/${DOCKERHUB_TOKEN}/g" "$f"
  sed -i '' "s/REPLACE_BASE64_USERNAME_COLON_TOKEN/${DOCKERHUB_AUTH//\//\\/}/g" "$f"
  sops --encrypt --in-place "$f"
done
```

#### 5) Commit encrypted files and reconcile
```bash
git add .sops.yaml flux-system/gotk-sync.yaml gitops-config-repo
git commit -m "Add SOPS-encrypted Docker Hub auth secrets"
git push origin main

flux reconcile kustomization flux-system -n flux-system
flux reconcile kustomization apps -n flux-system
```

#### 6) Validate
```bash
flux get image repository demo -n flux-system
flux get image policy demo -n flux-system
kubectl get pods -n default
```

### Optional Local-Only Secret Apply
If you do not want any encrypted secret files in Git, you can still use:
`scripts/apply_dockerhub_auth.sh`

### Commit and Push to Trigger CI

```bash
git add .
git commit -m "Initialize Go application and GitHub Actions CI"
git push origin main
```

Navigate to the **Actions** tab in GitHub to watch the workflow build and push your first image tag: `1.0.1` (tagged dynamically using `${{ github.run_number }}`).

---

## 8. Step 6: Verify the Automated Pipeline

Once the GitHub Actions CI run succeeds, verify that the image is available on Docker Hub and Flux has detected it.

If needed, force immediate reconciliation:
```bash
flux reconcile image repository demo -n flux-system
flux reconcile image policy demo -n flux-system
flux reconcile image update demo -n flux-system
flux reconcile kustomization apps -n flux-system
```

### 1. Check Image Registry Scan Status
```bash
flux get image repository demo
```
*Expected Output:*
```text
NAME    LAST SCAN                   SUSPENDED   READY   MESSAGE
demo    2026-07-09T15:40:00+00:00   False       True    successful scan: found 1 tags
```

### 2. Check Tag Policy Resolution
```bash
flux get image policy demo
```
*Expected Output:*
```text
NAME    IMAGE                               TAG     READY   MESSAGE
demo    docker.io/your_docker_username/demo 1.0.1   True    Latest image tag resolved to 1.0.1
```

### 3. Check Image Automation Commit Status
Flux will write the new tag `1.0.1` into the GitOps repository. Pull the changes in your `fluxcd-gitops-` clone to inspect it:

```bash
cd /path/to/fluxcd-gitops-
git pull origin main
git log -1
```
*You will see a commit authored by `flux-bot` with the message: `chore(gitops): update image tags [skip ci]`.*

Check the contents of `apps/demo.yaml`:
```bash
cat apps/demo.yaml | grep image:
```
*Output will now show `1.0.1` instead of `1.0.0`:*
```yaml
        image: docker.io/your_docker_username/demo:1.0.1 # {"$imagepolicy": "flux-system:demo"}
```

---

## 9. Step 7: The "Demo" Action (Testing a Source Code Update)

This is the key demonstration step to show clients!

### 1. Modify the Web App Code
Open `main.go` in your `go-app-source` repo and update the message:

```go
// Replace "Hello World!" with "Hello Fluxcd!"
		c.JSON(http.StatusOK, "Hello Fluxcd!")
```

### 2. Commit and Push
```bash
git add main.go
git commit -m "Update homepage greeting to Hello Fluxcd"
git push origin main
```

### 3. Observe the Magic
1. **GitHub Actions**: Builds tag `1.0.2` and pushes it to Docker Hub.
2. **Flux Image Registry Scan**: Within 1 minute, Flux scans Docker Hub and spots tag `1.0.2`.
3. **Flux Git Commit**: Flux commits `1.0.2` back to your `fluxcd-gitops-` repo.
4. **Flux Cluster Sync**: Flux Kustomize Controller pulls the change and rolls out the deployment on Kubernetes.

### 4. Access the Application
Port-forward the demo service to verify the application has updated:

```bash
kubectl port-forward svc/demo 8080:80 -n default
```

In another terminal, curl the local port:
```bash
curl http://localhost:8080
```
*Output:*
```json
"Hello Fluxcd!"
```

---

## 10. Troubleshooting

* **Flux is not committing updates to Git**: Check write permissions on the SSH key used during `flux bootstrap`. The deployment key in GitHub must have **write access enabled**.
* **Scanning is slow**: Flux scans the registry every 1 minute as configured in `imagerepository_demo.yaml`. You can trigger an immediate manual reconciliation using:
  ```bash
  flux reconcile image repository demo
  flux reconcile image update demo
  ```
* **GitOps commits are loop-triggering CI**: Ensure your GitHub Action excludes commits from `flux-bot` or uses `[skip ci]` in the commit message template as configured.
