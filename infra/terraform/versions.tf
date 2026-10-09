terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0" # any 8.x; the exact version is pinned in .terraform.lock.hcl
    }
  }

  # Remote state in a GCS bucket (created once by hand, see docs/learning/week-01-foundations.md).
  # "Partial configuration": the bucket name is NOT hardcoded. Pass it at init time:
  #   terraform init -backend-config="bucket=<your-state-bucket>"
  backend "gcs" {
    prefix = "haggle/prod"
  }
}
