# Vultr deployment

Provisions one Vultr instance (firewall, SSH key, Docker, Caddy HTTPS) that runs
`server/` from this repo. Frontend agents only need the two outputs below.

## Deploy from GitHub Actions (preferred, shared state)
State lives in HCP Terraform, so Actions and laptops see the same infra.
One-time setup (see the PR description): HCP org + workspace `dispel-infra` (CLI-driven,
**Execution mode: Local**), then repo secrets `VULTR_API_KEY`, `TF_API_TOKEN` and repo
variable `TF_CLOUD_ORGANIZATION`. Other variables already set: `TF_WORKSPACE`, `SSH_PUBLIC_KEY`,
`SSH_ALLOWED_CIDRS` (JSON list, your IP as /32), `DEPLOY_GIT_REF`.
- PRs touching `infra/`: fmt + validate + `plan` (shown in the run summary).
- Actions -> infra -> Run workflow -> `apply`: creates/changes the real server (costs credit).
- Changing your IP or teammates' keys = edit the repo variables, then re-run apply.
- `apply` refuses any plan that destroys the server unless `replace_server` is ticked, and always refuses to destroy the models volume.

## Deploy from a laptop
Needs the same env: `TF_CLOUD_ORGANIZATION`, `TF_WORKSPACE=dispel-infra`, `TF_TOKEN_app_terraform_io` (or `terraform login`).
Prefer Actions so there is one place that applies.

```sh
export VULTR_API_KEY=...            # Vultr console -> Account -> API (allow your IP)
cd infra/vultr
cp terraform.tfvars.example terraform.tfvars   # fill in (git-ignored)
terraform init && terraform apply
terraform output base_url            # -> the app's API base URL
terraform output -raw api_key        # -> bearer token (keep in the Electron main process)
```
Cloud-init takes a few minutes; then `curl $(terraform output -raw base_url)/health`.

## What survives what
| Event | Server disk | Models volume (`/opt/dispel/models`) |
|---|---|---|
| Code deploy (merge to `main`), reboot, container restart | kept | kept |
| Editing `cloud-init.yaml.tftpl` | kept (`ignore_changes`; change has no effect on the running server) | kept |
| infra apply with `replace_server` ticked | **wiped** (new IP, new URL) | kept, re-attached and re-mounted |
| Any other plan that destroys the server | apply refuses | apply refuses |
| Anything that destroys the volume | apply refuses (and `prevent_destroy`) | n/a |
Keep a copy of the weights off the server anyway (Akash has the source of truth).

## How the server is driven from the repo
The startup script (cloud-init) writes a tiny fixed bootstrap: `/opt/dispel/deploy.sh` updates the git checkout and runs
`docker/remote-deploy.sh` from the repo. That script and `docker/compose.prod.yml` hold everything else (Caddy config, the
container stack, settings), so changing them is an ordinary PR that deploys on merge, with no server replacement.
- **Settings/secrets** (`GEMINI_API_KEY`, `GEMINI_MODEL`): set the repo secret/variable, then the deploy workflow pushes them
  over SSH into `/opt/dispel/settings.env` (allowlist in `docker/remote-deploy.sh`; add a name there to allow a new one).
- To roll the server back to the bootstrap state deliberately: Actions -> infra -> apply with `replace_server`.

## Deploying code (automatic)
`.github/workflows/deploy.yml` runs on merges to `main` that touch `server/`, `docker/` or `docs/examples/`
(and on demand from the Actions tab). It finds the server by its label (`dispel-api`), opens port 22 for the
runner's IP through the Vultr API, SSHes in as `deploy`, and closes the rule. The `deploy` key (repo secret
`DEPLOY_SSH_KEY`, public half in repo variable `DEPLOY_PUBLIC_KEY`) can only run `/opt/dispel/deploy.sh`.
If a run is killed mid-way, a stale rule named `gha-<run id>` may stay in the firewall group; delete it in the console.

## Weights (not in git)
```sh
$(terraform output -raw upload_weights)   # rsync your MODEL_DIR to the instance
ssh root@<ip> 'cd /opt/dispel && docker compose -f compose.prod.yml restart server'
```

## Redeploy / GPU
- New code: push the branch, then `ssh root@<ip> /opt/dispel/deploy.sh` (set `git_ref` to what you want).
- GPU: set `plan` to a `vcg-*` plan (`vultr-cli plans list --type vcg`) and `device = "cuda"`. The current Dockerfile is CPU-only; GPU needs a CUDA torch base image and the NVIDIA container toolkit. Not done yet.
- Tear down after the event: `terraform destroy` (billing is hourly).

## Notes
- Plan id `vc2-4c-8gb` (atl, ~$0.06/hr) and os_id `2284` were verified with `vultr-cli` on 2026-09-26.
- State (in HCP Terraform) contains the server API key; only people in the HCP org can read it.
- Without `domain`, TLS uses `<ip-with-dashes>.sslip.io` (Let's Encrypt via Caddy).
