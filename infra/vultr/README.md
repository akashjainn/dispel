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
