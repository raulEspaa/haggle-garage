provider "google" {
  project = var.project_id
  region  = var.region
}

# Google Cloud APIs are disabled by default in a new project. Enabling them is a resource too.
resource "google_project_service" "enabled" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false # destroying the stack must not break other things in the project
}
