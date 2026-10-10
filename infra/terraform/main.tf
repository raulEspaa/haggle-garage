provider "google" {
  project = var.project_id
  region  = var.region

  # The budget API is billed to a project: with user credentials (ADC) it must be told which.
  user_project_override = true
  billing_project       = var.project_id
}

data "google_project" "this" {}

# Google Cloud APIs are disabled by default in a new project. Enabling them is a resource too.
resource "google_project_service" "enabled" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudresourcemanager.googleapis.com", # bootstrap: enabled once by hand, see week 7 journal
    "iam.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false # destroying the stack must not break other things in the project
}

locals {
  # Cloud Run's deterministic URLs (https://<service>-<project number>.<region>.run.app) are
  # known BEFORE the services exist, so services can reference each other without a cycle.
  service_url = {
    for name in ["api", "seller", "mcp"] :
    name => "https://haggle-${name}-${data.google_project.this.number}.${var.region}.run.app"
  }
  mcp_host = trimprefix(local.service_url.mcp, "https://")
}
