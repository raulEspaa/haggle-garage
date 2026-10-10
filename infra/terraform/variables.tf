variable "project_id" {
  description = "GCP project id that hosts the demo (e.g. haggle-prod-123456)."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run and Artifact Registry. europe-west1 has Tier 1 pricing."
  type        = string
  default     = "europe-west1"
}

variable "billing_account" {
  description = "Billing account id (gcloud billing accounts list), for the budget alert."
  type        = string
}

variable "images" {
  description = <<-EOT
    Container image per service. The default is Google's public "hello" sample, so the first
    apply works before our images exist. Afterwards `make deploy` passes the real ones:
      europe-west1-docker.pkg.dev/<project>/haggle/<service>:<git-sha>
  EOT
  type        = map(string)
  default = {
    api    = "us-docker.pkg.dev/cloudrun/container/hello"
    seller = "us-docker.pkg.dev/cloudrun/container/hello"
    mcp    = "us-docker.pkg.dev/cloudrun/container/hello"
  }
}

variable "max_instances" {
  description = "Upper bound on containers per service: also an upper bound on cost and abuse."
  type        = number
  default     = 2
}

variable "daily_budget_usd" {
  description = "Game spend per day (all LLM calls); past it the dealership is closed until tomorrow."
  type        = string
  default     = "2.00"
}

variable "monthly_budget_eur" {
  description = "GCP budget alert: e-mails at 50/90/100 %. An ALERT, not a cap."
  type        = number
  default     = 10
}

variable "langfuse_base_url" {
  description = "Langfuse region endpoint (keys are secrets)."
  type        = string
  default     = "https://cloud.langfuse.com"
}
