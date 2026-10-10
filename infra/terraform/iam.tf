# One service account per service = one identity per service (least privilege).
resource "google_service_account" "api" {
  account_id   = "haggle-api"
  display_name = "Haggle API (Cloud Run runtime identity)"

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "seller" {
  account_id   = "haggle-seller"
  display_name = "Haggle seller agent (Cloud Run runtime identity)"

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "mcp" {
  account_id   = "haggle-mcp"
  display_name = "Haggle MCP server (Cloud Run runtime identity)"

  depends_on = [google_project_service.enabled]
}

# Gemini on Vertex AI with the service's own identity: no API key anywhere (ADR-0013).
# The seller calls the chat model; the MCP server calls the embedding model. The api: neither.
resource "google_project_iam_member" "vertex_user" {
  for_each = {
    seller = google_service_account.seller.email
    mcp    = google_service_account.mcp.email
  }

  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${each.value}"
}

# Service-to-service calls: Cloud Run checks a Google-signed ID token for these identities.
#   api -> seller (A2A)      seller -> mcp (MCP tools)
resource "google_cloud_run_v2_service_iam_member" "api_invokes_seller" {
  name     = google_cloud_run_v2_service.seller.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api.email}"
}

resource "google_cloud_run_v2_service_iam_member" "seller_invokes_mcp" {
  name     = google_cloud_run_v2_service.mcp.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.seller.email}"
}

# Only the api is public. The seller and the MCP server get NO allUsers binding.
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
