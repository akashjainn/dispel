variable "region" {
  description = "Vultr region id (e.g. atl = Atlanta, close to HackGT). List: vultr-cli regions list"
  type        = string
  default     = "atl"
}

variable "plan" {
  description = "Instance plan id. Default is CPU (fine for the mock API and short-clip CPU inference). For GPU, pick a vcg-* plan available in your region: vultr-cli plans list --type vcg"
  type        = string
  default     = "vhf-4c-16gb"
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
  description = "Optional DNS name pointing at the instance. If empty, an sslip.io hostname is derived from the IP so TLS still works."
  type        = string
  default     = ""
}

variable "device" {
  description = "cpu or cuda; reported by /health"
  type        = string
  default     = "cpu"
}
