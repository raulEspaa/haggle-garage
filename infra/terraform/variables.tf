variable "project_id" {
  description = "GCP project id that hosts the demo (e.g. haggle-prod-123456)."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run and Artifact Registry. europe-west1 has Tier 1 pricing."
  type        = string
  default     = "europe-west1"
}

variable "api_image" {
  description = <<-EOT
    Container image for the api service. The default is Google's public "hello" sample, so
    the very first apply works before our own image exists. Afterwards pass the real one:
      -var="api_image=europe-west1-docker.pkg.dev/<project>/haggle/api:<git-sha>"
  EOT
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "api_max_instances" {
  description = "Upper bound on api containers: also an upper bound on cost and on abuse."
  type        = number
  default     = 3
}
