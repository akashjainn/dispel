terraform {
  required_version = ">= 1.5"

  # State lives in HCP Terraform (free tier). Org and workspace come from the env vars
  # TF_CLOUD_ORGANIZATION and TF_WORKSPACE, and auth from TF_TOKEN_app_terraform_io
  # (or `terraform login`). The workspace's execution mode must be "Local".
  # Validate without any of that: terraform init -backend=false
  cloud {}

  required_providers {
    vultr = {
      source  = "vultr/vultr"
      version = "~> 2.21"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# Auth: export VULTR_API_KEY. Never put it in a .tf or .tfvars file.
provider "vultr" {}
