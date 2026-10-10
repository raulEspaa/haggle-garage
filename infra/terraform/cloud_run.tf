# Three services, one public:
#
#   browser ──▶ haggle-api (public) ──A2A + ID token──▶ haggle-seller (IAM only)
#                                                          └──MCP + ID token──▶ haggle-mcp (IAM only)
#
# Settings are plain env vars; secrets are references to Secret Manager, resolved by Cloud Run
# when a container starts (the values never appear in Terraform or in the service definition).

locals {
  vertex_env = {
    GOOGLE_GENAI_USE_VERTEXAI = "true"
    GOOGLE_CLOUD_PROJECT      = var.project_id
    GOOGLE_CLOUD_LOCATION     = "global"
  }
  common_env = {
    HAGGLE_ENV             = "prod"
    HAGGLE_DB_POOL_SIZE    = "3"
    HAGGLE_DB_MAX_OVERFLOW = "2"
    LANGFUSE_BASE_URL      = var.langfuse_base_url
  }
  langfuse_secrets = {
    LANGFUSE_PUBLIC_KEY = "haggle-langfuse-public-key"
    LANGFUSE_SECRET_KEY = "haggle-langfuse-secret-key"
  }

  services = {
    api = {
      port        = 8080
      memory      = "512Mi"
      timeout     = "120s" # the seller may take up to 90 s on a slow model day
      concurrency = 40
      env = merge(local.common_env, {
        HAGGLE_API_SELLER_URL         = local.service_url.seller
        HAGGLE_API_SELLER_AUTH        = "google"
        HAGGLE_API_TRUSTED_PROXY_HOPS = "1" # Google's front end appends the real client IP
        HAGGLE_API_DAILY_BUDGET_USD   = var.daily_budget_usd
      })
      secrets = merge(local.langfuse_secrets, {
        HAGGLE_DATABASE_URL       = "haggle-db-url-api"
        HAGGLE_API_IP_HASH_SECRET = "haggle-ip-hash-secret"
      })
    }
    seller = {
      port        = 8200
      memory      = "1Gi" # ADK + the model client
      timeout     = "300s"
      concurrency = 10
      env = merge(local.common_env, local.vertex_env, {
        HAGGLE_SELLER_PUBLIC_URL       = local.service_url.seller # what the agent card says
        HAGGLE_SELLER_MCP_URL          = "${local.service_url.mcp}/mcp"
        HAGGLE_SELLER_MCP_AUTH         = "google"
        HAGGLE_SELLER_DAILY_BUDGET_USD = var.daily_budget_usd
      })
      secrets = merge(local.langfuse_secrets, {
        HAGGLE_DATABASE_URL         = "haggle-db-url-seller"
        HAGGLE_SELLER_MCP_TOKEN     = "haggle-mcp-seller-token"
        HAGGLE_SELLER_CANARY_SECRET = "haggle-canary-secret"
      })
    }
    mcp = {
      port        = 8100
      memory      = "512Mi"
      timeout     = "60s"
      concurrency = 40
      env = merge(local.common_env, local.vertex_env, {
        HAGGLE_MCP_BACKEND = "cloud"
        # DNS-rebinding protection: the exact Host header Cloud Run passes (no port).
        HAGGLE_MCP_ALLOWED_HOSTS = jsonencode([local.mcp_host])
      })
      secrets = merge(local.langfuse_secrets, {
        HAGGLE_DATABASE_URL      = "haggle-db-url-mcp"
        HAGGLE_MCP_SELLER_TOKEN  = "haggle-mcp-seller-token"
        HAGGLE_MCP_CATALOG_TOKEN = "haggle-mcp-catalog-token"
      })
    }
  }
  identities = {
    api    = google_service_account.api.email
    seller = google_service_account.seller.email
    mcp    = google_service_account.mcp.email
  }
}

resource "google_cloud_run_v2_service" "api" {
  name                = "haggle-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false # a demo: we want `terraform destroy` to work

  template {
    service_account                  = local.identities.api
    max_instance_request_concurrency = local.services.api.concurrency
    timeout                          = local.services.api.timeout

    scaling {
      min_instance_count = 0 # scale to zero: no traffic, no cost
      max_instance_count = var.max_instances
    }

    containers {
      image = var.images.api

      ports {
        container_port = local.services.api.port
      }

      resources {
        limits = {
          cpu    = "1"
          memory = local.services.api.memory
        }
        cpu_idle          = true # request-based billing: CPU is billed only while serving
        startup_cpu_boost = true # faster cold starts at no extra cost
      }

      dynamic "env" {
        for_each = local.services.api.env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.services.api.secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.access]
}

resource "google_cloud_run_v2_service" "seller" {
  name                = "haggle-seller"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL" # reachable, but only with an ID token (IAM)
  deletion_protection = false

  template {
    service_account                  = local.identities.seller
    max_instance_request_concurrency = local.services.seller.concurrency
    timeout                          = local.services.seller.timeout

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    containers {
      image = var.images.seller

      ports {
        container_port = local.services.seller.port
      }

      resources {
        limits = {
          cpu    = "1"
          memory = local.services.seller.memory
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = local.services.seller.env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.services.seller.secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.access, google_project_iam_member.vertex_user]
}

resource "google_cloud_run_v2_service" "mcp" {
  name                = "haggle-mcp"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = local.identities.mcp
    max_instance_request_concurrency = local.services.mcp.concurrency
    timeout                          = local.services.mcp.timeout

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    containers {
      image = var.images.mcp

      ports {
        container_port = local.services.mcp.port
      }

      resources {
        limits = {
          cpu    = "1"
          memory = local.services.mcp.memory
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = local.services.mcp.env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.services.mcp.secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.access, google_project_iam_member.vertex_user]
}
