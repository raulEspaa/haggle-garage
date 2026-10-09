# One service account per service = one identity per service (least privilege).
# Week 1: the api needs no permissions at all. Secret access etc. is granted in later weeks.
resource "google_service_account" "api" {
  account_id   = "haggle-api"
  display_name = "Haggle API (Cloud Run runtime identity)"

  depends_on = [google_project_service.enabled]
}

resource "google_cloud_run_v2_service" "api" {
  name                = "haggle-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL" # the api is the public entry point
  deletion_protection = false                 # a demo: we want `terraform destroy` to work

  template {
    service_account                  = google_service_account.api.email
    max_instance_request_concurrency = 40
    timeout                          = "30s"

    scaling {
      min_instance_count = 0 # scale to zero: no traffic, no cost
      max_instance_count = var.api_max_instances
    }

    containers {
      image = var.api_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true # request-based billing: CPU is billed only while serving
        startup_cpu_boost = true # faster cold starts at no extra cost
      }

      env {
        name  = "HAGGLE_ENV"
        value = "prod"
      }
    }
  }

  depends_on = [google_project_service.enabled]
}

# Make the api public: anyone on the internet may invoke it.
# The seller and MCP services (later weeks) will NOT get this binding.
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
