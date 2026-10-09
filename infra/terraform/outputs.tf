output "api_url" {
  description = "Public URL of the api service."
  value       = google_cloud_run_v2_service.api.uri
}

output "image_repository" {
  description = "Prefix for `docker tag` / `docker push`."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}
