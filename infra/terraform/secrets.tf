# Secret CONTAINERS only. Their values are added outside Terraform (`make secrets`,
# `haggle-provision-roles`), so no secret value ever lands in the Terraform state.
locals {
  secrets = {
    "haggle-db-url-api"          = ["api"]
    "haggle-db-url-seller"       = ["seller"]
    "haggle-db-url-mcp"          = ["mcp"]
    "haggle-mcp-seller-token"    = ["seller", "mcp"]
    "haggle-mcp-catalog-token"   = ["mcp"]
    "haggle-ip-hash-secret"      = ["api"]
    "haggle-canary-secret"       = ["seller"]
    "haggle-langfuse-public-key" = ["api", "seller", "mcp"]
    "haggle-langfuse-secret-key" = ["api", "seller", "mcp"]
  }
  accessors = {
    api    = google_service_account.api.email
    seller = google_service_account.seller.email
    mcp    = google_service_account.mcp.email
  }
  secret_bindings = merge([
    for secret, services in local.secrets : {
      for service in services : "${secret}/${service}" => { secret = secret, service = service }
    }
  ]...)
}

resource "google_secret_manager_secret" "this" {
  for_each  = local.secrets
  secret_id = each.key

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

# Each service may read only its own secrets.
resource "google_secret_manager_secret_iam_member" "access" {
  for_each  = local.secret_bindings
  secret_id = google_secret_manager_secret.this[each.value.secret].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.accessors[each.value.service]}"
}
