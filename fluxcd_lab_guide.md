# Lab Guide: Automated GitOps CI/CD with FluxCD & GitHub Actions

Welcome to the FluxCD GitOps & CI/CD Demo Lab! This guide walks you through setting up an automated deployment pipeline. When developers push code to GitHub, GitHub Actions will compile and build a Docker container image, push it to Docker Hub, and FluxCD will automatically detect the new image version, write the updated tag back to Git, and reconcile the Kubernetes cluster.

---

## 1. Flow Overview

### Visual Workflow (Mermaid)

```mermaid
flowchart TD
    A[Source Repo<br/>go-app-source] -->|git push e.g. main.go update| B[GitHub Actions<br/>CI Workflow<br/>Build + Push Image]
    B -->|image tag e.g. v1.0.1| C[Docker Hub<br/>Container Registry]
    C -->|1) Scan registry for new tags| D[FluxCD]
    D -->|2) Commit and push tag update| E[GitOps Repo<br/>YAML manifests]
    E -->|Flux source-controller pulls desired state| D
    D -->|3) Reconcile cluster state| F[Kubernetes<br/>Deploy App]
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
2. **GitOps Config Repo (`fluxcd-gitops-`)**: Contains Kubernetes manifests and FluxCD automation configuration.
3. **Flux Image-Reflector-Controller**: Scans the Docker Hub registry for new tags matching a SemVer range.
4. **Flux Image-Automation-Controller**: Checks out the Git repository, replaces the image tag comment marker with the new tag, and commits/pushes the change back to the Git repository.

---

## 2. Prerequisites

* **Kubernetes Cluster**: A running cluster (like the Nutanix `nkp-pro` cluster).
* **Docker Hub Account**: A free account at [hub.docker.com](https://hub.docker.com). You will need your password or a Personal Access Token (recommended).
* **GitHub Account**: A GitHub account to host the two repositories.
* **NKP / Kommander Flux controllers already running** in namespace `kommander-flux`.
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

## 5. Step 3: Integrate with Existing NKP Flux (`kommander-flux`)

This lab demonstrates integration with the existing NKP Flux installation in `kommander-flux` (no additional Flux install required).

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

### 5.2 Export kubeconfig and validate NKP Flux controllers

```bash
export KUBECONFIG=/path/to/nkp-pro.conf

kubectl get deployments -n kommander-flux | rg "source-controller|kustomize-controller|helm-controller|image-reflector-controller|image-automation-controller|notification-controller"
```

### 5.2.1 NKP / D2iQ references

Kommander (NKP) deploys Flux controllers in `kommander-flux` and supports reusing that instance for custom GitRepository and Kustomization resources. Use these references for platform-aligned behavior and troubleshooting:

* [D2iQ: Deploy applications using GitOps](https://archive-docs-old.d2iq.com/dkp/kommander/2.0/custom-git/)
* [D2iQ: Create a Git Repository](https://docs.d2iq.com/dkp/2.8/create-a-git-repository)

Controller logs:
```bash
kubectl -n kommander-flux logs -l app=source-controller
kubectl -n kommander-flux logs -l app=kustomize-controller
kubectl -n kommander-flux logs -l app=helm-controller
```

### 5.3 Create GitHub App secret in `kommander-flux` (YAML-first)

Find your **Installation ID** in GitHub (App settings -> Install App -> target repo/org installation).

Create `github-app-auth` in `kommander-flux`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: github-app-auth
  namespace: kommander-flux
type: Opaque
stringData:
  githubAppID: "<YOUR_APP_ID>"
  githubAppInstallationID: "<YOUR_INSTALLATION_ID>"
  githubAppPrivateKey: |
    -----BEGIN RSA PRIVATE KEY-----
    <YOUR_PRIVATE_KEY_CONTENT>
    -----END RSA PRIVATE KEY-----
```

Apply it:
```bash
kubectl apply -f github-app-auth.yaml
```

### 5.4 Create lab GitRepository in `kommander-flux`

Create a dedicated source for this lab:

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: lab-gitops
  namespace: kommander-flux
spec:
  interval: 1m0s
  url: https://github.com/<your-github-username>/fluxcd-gitops-
  ref:
    branch: main
  provider: github
  secretRef:
    name: github-app-auth
```

Apply it:
```bash
kubectl apply -f lab-gitrepository.yaml
```

### 5.5 Create lab Kustomization in `kommander-flux`

This Kustomization tells NKP Flux to apply your lab manifests from the repo:

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: lab-gitops
  namespace: kommander-flux
spec:
  interval: 1m0s
  prune: true
  sourceRef:
    kind: GitRepository
    name: lab-gitops
  path: ./gitops-config-repo/flux-system
```

Apply it:
```bash
kubectl apply -f lab-kustomization.yaml
```

Reconcile source and kustomization:
```bash
flux reconcile source git lab-gitops -n kommander-flux
flux reconcile kustomization lab-gitops -n kommander-flux
```

### 5.6 Validate integration

```bash
flux get sources git -n kommander-flux
flux get kustomizations -n kommander-flux
```

If `READY=True`, NKP Flux is now syncing your lab repo using GitHub App auth.

### Verify the NKP Flux Runtime
Check that NKP-managed Flux controllers are healthy:

```bash
kubectl get deployments -n kommander-flux
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

### 5.7 Deep Investigation: How Kubefed Works in This Cluster

From live cluster inspection, this NKP environment is running a full federation control plane:

* `KubeFedConfig` exists in `kube-federation-system` with `scope: Cluster`.
* Member clusters registered in `KubeFedCluster`:
  * `nkp-pro` (management)
  * `nkp-workloads01` (downstream)
* `FederatedTypeConfig` is enabled for key resources, including:
  * `namespaces`, `deployments.apps`, `services`, `configmaps`, `secrets`.
* Workspace namespace `nkp-workloads01-cqrp5-5gxht` already has:
  * `FederatedNamespace` scoped to cluster selector label
    `kommander.d2iq.io/workspace-namespace-ref=nkp-workloads01-cqrp5-5gxht`.
* Kommander application propagation is active via:
  * `AppDeployment` (desired app in workspace)
  * `AppDeploymentInstance` (realized app per downstream cluster)

This means your cluster supports both:
1. **Kommander AppDeployment model** (catalog-first, workspace-driven), and
2. **Kubefed native model** (Federated* resources for custom workloads).

### 5.8 Phase 2: Deploy Demo App to Federated Namespace (Downstream)

This phase demonstrates custom app federation to downstream clusters using Kubefed-native resources.

#### Included manifests

`gitops-config-repo/federation-phase2/` contains:

* `namespace-federation.yaml`:
  * Creates `Namespace/demo-federated`
  * Creates `FederatedNamespace/demo-federated`
  * Places it to workspace downstream cluster selector.
* `demo-federated-deployment.yaml`:
  * `FederatedDeployment/demo` with image `docker.io/fernandoqnutanix/demo:1.0.1`
* `demo-federated-service.yaml`:
  * `FederatedService/demo`
* `kustomization.yaml`

#### Apply phase 2 (manual test)

```bash
kubectl apply -k ./gitops-config-repo/federation-phase2
```

#### Validate federation and downstream rollout

```bash
# Federated objects on management cluster
kubectl get federatednamespace,federateddeployment,federatedservice -n demo-federated

# Check member cluster targeting
kubectl get federatednamespace demo-federated -n demo-federated -o yaml

# Kommander cluster membership
kubectl get kubefedclusters.core.kubefed.io -n kube-federation-system
```

#### AppDeployment alternative

If you want a fully NKP-native experience (catalog + policy + lifecycle), use `AppDeployment` in workspace namespace `nkp-workloads01-cqrp5-5gxht`. That creates `AppDeploymentInstance` per downstream cluster automatically.

For this lab’s custom demo image, Kubefed-native `FederatedDeployment` is the most direct path.

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
   image: docker.io/your_docker_username/demo:1.0.0 # {"$imagepolicy": "kommander-flux:demo"}
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
* `kommander-flux`: used by Flux `ImageRepository` scan auth.
* `default` (or app namespace): used by kubelet to pull the app image.

```bash
# Flux side: image-reflector-controller auth (namespace kommander-flux)
kubectl create secret docker-registry dockerhub-auth \
  -n kommander-flux \
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

#### SOPS Flow (Mermaid)

```mermaid
flowchart TD
    A[Local age keypair<br/>keys.txt + public key] --> B[.sops.yaml policy]
    B --> C[Local secret templates<br/>dockerhub-auth *.secret.yaml]
    C --> D[sops encrypt in place]
    D --> E[Encrypted secret files in Git]
    E --> F[Flux source-controller pulls repo]
    F --> G[Flux kustomize-controller with decryption:sops]
    H[sops-age Kubernetes Secret<br/>kommander-flux namespace] --> G
    G --> I[Decrypted Secret applied in kommander-flux and default]
    I --> J[ImageRepository scan auth]
    I --> K[Pod imagePullSecrets auth]
```

This is the trust model in this lab: plaintext secrets exist only on your workstation during encryption and inside the cluster after Flux decryption; Git stores only encrypted payloads.

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
  -n kommander-flux \
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
flux reconcile kustomization apps -n kommander-flux
```

#### 6) Validate
```bash
flux get image repository demo -n kommander-flux
flux get image policy demo -n kommander-flux
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
flux reconcile image repository demo -n kommander-flux
flux reconcile image policy demo -n kommander-flux
flux reconcile image update demo -n kommander-flux
flux reconcile kustomization apps -n kommander-flux
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
        image: docker.io/your_docker_username/demo:1.0.1 # {"$imagepolicy": "kommander-flux:demo"}
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
