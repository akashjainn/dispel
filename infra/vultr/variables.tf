variable "region" {
  description = "Vultr region id (e.g. atl = Atlanta, close to HackGT). List: vultr-cli regions list"
  type        = string
  default     = "atl"
}

variable "plan" {
  description = "Instance plan id. Default is CPU (fine for the mock API and short-clip CPU inference). For GPU, pick a vcg-* plan available in your region: vultr-cli plans list --type vcg"
  type        = string
  default     = "vc2-4c-8gb"
}

variable "os_id" {
  description = "Vultr OS id. 2284 = Ubuntu 24.04 LTS x64. Verify: vultr-cli os list"
  type        = number
  default     = 2284
}

variable "ssh_public_key" {
  description = "Your SSH public key contents (e.g. file(\"~/.ssh/id_ed25519.pub\") via tfvars)"
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "CIDRs allowed to SSH in. Use your own IP, e.g. [\"203.0.113.4/32\"]. Avoid 0.0.0.0/0."
  type        = list(string)
}

variable "repo_url" {
  description = "HTTPS git URL cloud-init clones (must be public, or embed no secrets)"
  type        = string
  default     = "https://github.com/akashjainn/dispel.git"
}

variable "git_ref" {
  description = "Branch, tag or commit to deploy"
  type        = string
  default     = "main"
}

variable "domain" {
  description = "Domain whose DNS zone Vultr hosts (dns.tf): apex, www and api point at the instance. Empty = no zone. The sslip.io hostname derived from the IP always works too."
  type        = string
  default     = "hocuspocus.tech"
}

variable "device" {
  description = "cpu or cuda; reported by /health"
  type        = string
  default     = "cpu"
}

variable "deploy_public_key" {
  description = "Public half of the CI deploy key. It can only run /opt/dispel/deploy.sh on the server as user `deploy`."
  type        = string
}

variable "models_volume_gb" {
  description = "Size of the persistent NVMe volume for model weights (about $0.10/GB/month). Releases are ~1.2 GB each. Can only grow; the filesystem follows on the next replace_server, or run `resize2fs /dev/vdb` as root."
  type        = number
  default     = 10
}
