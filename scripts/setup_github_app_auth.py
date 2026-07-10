#!/usr/bin/env python3
"""
Discover GitHub App installation ID and optionally apply Flux auth objects.

Usage example:
  python3 scripts/setup_github_app_auth.py \
    --app-id 4266229 \
    --private-key /path/to/app.private-key.pem \
    --owner fquinino \
    --repo fluxcd-gitops- \
    --namespace flux-system \
    --gitrepository flux-system \
    --apply
"""

import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def build_jwt(app_id: str, private_key_path: str) -> str:
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    now = int(time.time())
    payload = b64url(
        json.dumps({"iat": now - 60, "exp": now + 540, "iss": app_id}, separators=(",", ":")).encode()
    )
    unsigned = f"{header}.{payload}"

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(unsigned.encode())
        msg_path = tmp.name

    try:
        sig = subprocess.check_output(
            ["openssl", "dgst", "-sha256", "-sign", private_key_path, msg_path],
            stderr=subprocess.STDOUT,
        )
    finally:
        os.unlink(msg_path)

    return f"{unsigned}.{b64url(sig)}"


def github_get(url: str, jwt_token: str):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "fluxcd-github-app-lab",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get_installation_id(jwt_token: str, owner: str, repo: str) -> int:
    full_name = f"{owner}/{repo}"
    installations = github_get("https://api.github.com/app/installations", jwt_token)

    for inst in installations:
        repos_url = inst.get("repositories_url")
        if not repos_url:
            continue
        repo_payload = github_get(repos_url, jwt_token)
        for item in repo_payload.get("repositories", []):
            if item.get("full_name", "").lower() == full_name.lower():
                return inst["id"]

    raise RuntimeError(
        f"GitHub App is not installed on {full_name}. Install the app on the repo/org and retry."
    )


def run(cmd):
    subprocess.run(cmd, check=True)


def apply_k8s_objects(app_id, installation_id, private_key_path, namespace, gitrepository, secret_name):
    create_cmd = [
        "kubectl",
        "create",
        "secret",
        "generic",
        secret_name,
        "-n",
        namespace,
        "--from-literal",
        f"githubAppID={app_id}",
        "--from-literal",
        f"githubAppInstallationID={installation_id}",
        "--from-file",
        f"githubAppPrivateKey={private_key_path}",
        "--dry-run=client",
        "-o",
        "yaml",
    ]
    yaml_secret = subprocess.check_output(create_cmd, text=True)
    subprocess.run(["kubectl", "apply", "-f", "-"], input=yaml_secret, text=True, check=True)

    patch_payload = json.dumps({"spec": {"provider": "github", "secretRef": {"name": secret_name}}})
    run(
        [
            "kubectl",
            "patch",
            "gitrepository",
            gitrepository,
            "-n",
            namespace,
            "--type",
            "merge",
            "-p",
            patch_payload,
        ]
    )
    run(["flux", "reconcile", "source", "git", gitrepository, "-n", namespace])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--namespace", default="flux-system")
    parser.add_argument("--gitrepository", default="flux-system")
    parser.add_argument("--secret-name", default="github-app-auth")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not os.path.isfile(args.private_key):
        raise FileNotFoundError(f"Private key not found: {args.private_key}")

    jwt_token = build_jwt(args.app_id, args.private_key)
    installation_id = get_installation_id(jwt_token, args.owner, args.repo)

    print(f"Installation ID for {args.owner}/{args.repo}: {installation_id}")

    if args.apply:
        apply_k8s_objects(
            app_id=args.app_id,
            installation_id=str(installation_id),
            private_key_path=args.private_key,
            namespace=args.namespace,
            gitrepository=args.gitrepository,
            secret_name=args.secret_name,
        )
        print(
            f"Applied secret '{args.secret_name}' and patched GitRepository "
            f"'{args.gitrepository}' in namespace '{args.namespace}'."
        )


if __name__ == "__main__":
    main()
