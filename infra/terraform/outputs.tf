output "api_url" {
  description = "Public URL of the game."
  value       = local.service_url.api
}

output "service_urls" {
  description = "Deterministic URLs of the three services (seller and mcp are IAM-only)."
  value       = local.service_url
}

output "image_repository" {
  description = "Prefix for `docker tag` / `docker push`."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}
