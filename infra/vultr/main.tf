resource "random_password" "api_key" {
  length  = 40
  special = false
}

resource "vultr_ssh_key" "deploy" {
  name    = "dispel-deploy"
  ssh_key = var.ssh_public_key
}

resource "vultr_firewall_group" "api" {
  description = "dispel api"
}

# SSH only from allowed CIDRs
resource "vultr_firewall_rule" "ssh" {
  for_each          = toset(var.ssh_allowed_cidrs)
  firewall_group_id = vultr_firewall_group.api.id
  protocol          = "tcp"
  ip_type           = "v4"
  subnet            = split("/", each.value)[0]
  subnet_size       = tonumber(split("/", each.value)[1])
  port              = "22"
}

# HTTP (ACME challenge + redirect) and HTTPS from anywhere
resource "vultr_firewall_rule" "web" {
  for_each          = toset(["80", "443"])
  firewall_group_id = vultr_firewall_group.api.id
  protocol          = "tcp"
  ip_type           = "v4"
  subnet            = "0.0.0.0"
  subnet_size       = 0
  port              = each.value
}

resource "vultr_instance" "api" {
  label             = "dispel-api"
  hostname          = "dispel-api"
  region            = var.region
  plan              = var.plan
  os_id             = var.os_id
  ssh_key_ids       = [vultr_ssh_key.deploy.id]
  firewall_group_id = vultr_firewall_group.api.id
  enable_ipv6       = false
  backups           = "disabled"

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    repo_url = var.repo_url
    git_ref  = var.git_ref
    domain   = var.domain
    device   = var.device
    api_key  = random_password.api_key.result
  })
}
