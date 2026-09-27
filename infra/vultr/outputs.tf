locals {
  host = var.domain != "" ? "api.${var.domain}" : "${replace(vultr_instance.api.main_ip, ".", "-")}.sslip.io"
}

output "base_url" {
  description = "Set this as the Electron app's API base URL"
  value       = "https://${local.host}"
}

output "ip" {
  value = vultr_instance.api.main_ip
}

output "nameservers" {
  description = "Set these at the domain registrar so Vultr answers for var.domain"
  value       = var.domain != "" ? ["ns1.vultr.com", "ns2.vultr.com"] : []
}

output "api_key" {
  description = "Bearer token for POST /analyze. Read with: terraform output -raw api_key"
  value       = random_password.api_key.result
  sensitive   = true
}

output "upload_weights" {
  description = "Model weights are not in git; copy them here once"
  value       = "rsync -avP <local MODEL_DIR>/ root@${vultr_instance.api.main_ip}:/opt/dispel/models/"
}

output "models_volume_id" {
  description = "Persistent volume holding /opt/dispel/models"
  value       = vultr_block_storage.models.id
}
