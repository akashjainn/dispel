terraform {
  required_version = ">= 1.5"
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
