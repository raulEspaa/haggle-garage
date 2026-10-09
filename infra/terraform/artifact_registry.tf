# Private Docker registry for our images. Storage beyond 0.5 GB is billed, so old images are
# cleaned up automatically. KEEP policies win over DELETE policies.
resource "google_artifact_registry_repository" "containers" {
  repository_id = "haggle"
  location      = var.region
  format        = "DOCKER"
  description   = "Container images for Haggle Garage services."

  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-last-3"
    action = "KEEP"
    most_recent_versions {
      keep_count = 3
    }
  }

  cleanup_policies {
    id     = "delete-older-than-14-days"
    action = "DELETE"
    condition {
      older_than = "1209600s" # 14 days
    }
  }

  depends_on = [google_project_service.enabled]
}
