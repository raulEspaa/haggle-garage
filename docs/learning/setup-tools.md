# Setup: install and configure the tools (Ubuntu 26.04)

Commands checked on 2026-10-09 against each vendor's official install page. All four apt
repositories (Docker, HashiCorp, Google Cloud, GitHub CLI) publish packages for Ubuntu 26.04
"resolute". Run `make doctor` at any point to see what is still missing.

| Tool | Used for | From week |
|------|----------|-----------|
| **Docker Engine + Compose** | Local Postgres, building images, running the stack | 1 |
| **Terraform** | Creating the GCP infrastructure from code | 1 |
| **gcloud CLI** | Logging in to GCP, pushing images, secrets | 1 |
| **gh** (GitHub CLI) | Creating the repo, watching CI, PRs | 1 |
| uv, git, make | Already installed | — |

## Why vendor repositories and not Ubuntu's packages?

Ubuntu ships `docker.io` (29.1) and `docker-compose-v2`, which would work too. The vendor repos
give you the versions the docs describe and faster security fixes. Terraform, gcloud and gh have
no up-to-date Ubuntu package at all.

How an apt repository is added (the same 3 steps for every tool below):

1. Download the vendor's **signing key** into a keyring file.
2. Add a **source** that says: "packages from this URL must be signed by *that* key"
   (`signed-by=`). The key is trusted only for that one repository, not system-wide.
3. `apt update` + `apt install`.

---

## 1. Install (needs sudo, ~10 min)

### 1.1 Prerequisites

```bash
sudo apt update && sudo apt install -y ca-certificates curl gnupg wget
```

### 1.2 Docker repository

([docs](https://docs.docker.com/engine/install/ubuntu/))

```bash
sudo install -m 0755 -d /etc/apt/keyrings && sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && sudo chmod a+r /etc/apt/keyrings/docker.asc
```

```bash
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
```

This is the newer **deb822** format (`.sources` files). It's the same information as a one-line
`.list` entry, but easier to read.

### 1.3 HashiCorp repository (Terraform)

([docs](https://developer.hashicorp.com/terraform/install))

```bash
wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --yes --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
```

```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release || lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
```

### 1.4 Google Cloud repository (gcloud)

([docs](https://docs.cloud.google.com/sdk/docs/install-sdk))

```bash
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --yes --dearmor -o /usr/share/keyrings/cloud.google.gpg
```

```bash
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
```

(The official page uses `tee -a`, which appends. Without `-a`, running the command twice
doesn't create a duplicate entry.)

### 1.5 GitHub CLI repository (gh)

([docs](https://github.com/cli/cli/blob/trunk/docs/install_linux.md))

```bash
sudo mkdir -p -m 755 /etc/apt/keyrings && wget -nv -O- https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
```

```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
```

### 1.6 Install everything in one go

```bash
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin terraform google-cloud-cli gh
```

### 1.7 Use Docker without sudo

```bash
sudo usermod -aG docker "$USER"
```

Then **log out and back in** (or reboot) so the new group applies to your session.
`newgrp docker` applies it to one terminal only.

> ⚠️ **Security note.** Membership in the `docker` group is **equivalent to root**: anyone in it
> can start a container that mounts `/` and edits any file. On a single-user dev laptop that's
> the accepted trade-off. Never add service accounts or other people to this group. The
> stricter alternative is
> [rootless Docker](https://docs.docker.com/engine/security/rootless/), at the cost of some
> networking quirks.

The Docker package enables the service at boot automatically. Check it with
`systemctl is-enabled docker`. If you only want Docker running while you work, disable it:
`sudo systemctl disable --now docker.service containerd.service`.

---

## 2. Configure (no sudo)

### 2.1 Docker: verify

```bash
docker run --rm hello-world
```

If you have a local Postgres already listening on port 5432, stop it or change the left side of
`127.0.0.1:5432:5432` in `compose.yaml`.

### 2.2 Git identity

Your commits will be public. Use GitHub's **noreply** address so your personal email isn't
published. You'll find it in GitHub → Settings → Emails → "Keep my email addresses private";
it looks like `12345678+username@users.noreply.github.com`.

```bash
git config --global user.name "Your Name"
```

```bash
git config --global user.email "ID+username@users.noreply.github.com"
```

```bash
git config --global init.defaultBranch main
```

### 2.3 GitHub CLI

```bash
gh auth login
```

Choose GitHub.com → HTTPS (or SSH if you already use keys) → login with a web browser. gh
stores the token in your system keyring, not in a plain file, when one is available.

### 2.4 gcloud: account, project, credentials

Three **different** logins, a common source of confusion:

| Command | Who uses the credential |
|---------|-------------------------|
| `gcloud init` / `gcloud auth login` | the `gcloud` CLI itself |
| `gcloud auth application-default login` | **libraries and Terraform** (Application Default Credentials, ADC) |
| `gcloud auth configure-docker <registry>` | `docker push` to Artifact Registry |

```bash
gcloud init
```

It opens the browser and lets you pick or **create** a project. Suggested id:
`haggle-prod-<random>`. Project ids are global and permanent, so you can't reuse one after
deleting it.

If you prefer to create and link the project from the CLI instead:

```bash
gcloud projects create haggle-prod-123456 --name="Haggle Garage"
```

```bash
gcloud billing accounts list
```

```bash
gcloud billing projects link haggle-prod-123456 --billing-account=XXXXXX-XXXXXX-XXXXXX
```

Then the defaults and credentials:

```bash
gcloud config set project haggle-prod-123456
```

```bash
gcloud config set run/region europe-west1
```

```bash
gcloud auth application-default login
```

```bash
gcloud auth configure-docker europe-west1-docker.pkg.dev
```

The last one adds a credential helper to `~/.docker/config.json`. Docker then asks gcloud for a
short-lived token on every push, so no password is stored.

> 🔐 ADC are stored in `~/.config/gcloud/application_default_credentials.json` and act as
> **you** (owner of the project). Never copy that file into a repo or an image. Cloud Run
> services use their own service accounts instead.

### 2.5 Budget alert (console)

Billing → **Budgets & alerts** → *Create budget* → scope: the project → amount **10 USD** →
thresholds **50 / 90 / 100 %** → email to billing admins. Remember: a budget **alerts**, it
does **not** stop spending (that's what the AI Studio spend cap is for, ADR-0003).

### 2.6 Terraform: optional tab completion

```bash
terraform -install-autocomplete
```

---

## 3. Verify everything

```bash
make doctor
```

Expected: every line ✓. Then the full local check from Week 1:

```bash
make db-up && make migrate seed && make test-db
```

Expected: **26 passed**.

```bash
make docker-api && docker compose up -d api && curl -s localhost:8080/health
```

Expected: `{"status":"ok","service":"api","version":"<git sha>"}`. Stop it with
`docker compose down`.

Next: Week 1 §12.2–12.4 ([week-01-foundations.md](week-01-foundations.md#12-your-turn--needs-sudo-or-your-accounts)) for accounts,
the first Cloud Run deploy and the first push to GitHub.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `permission denied while trying to connect to the Docker daemon socket` | You haven't logged out/in since `usermod`. Run `id -nG` and check that `docker` is listed. |
| `apt update` complains about `NO_PUBKEY` | The key download failed (empty file). Re-run that repository's key command. |
| `make db-up` hangs or says port in use | Another Postgres is on 5432: `sudo ss -ltnp \| grep 5432`. |
| `gcloud` works but Terraform says *could not find default credentials* | You skipped `gcloud auth application-default login`. |
| `docker push` → `denied: Unauthenticated` | Run `gcloud auth configure-docker europe-west1-docker.pkg.dev` again. |
| `terraform init` → *bucket doesn't exist* | Create the state bucket first (Week 1 §12.3). |
