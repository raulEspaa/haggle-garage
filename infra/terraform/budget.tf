# A budget ALERT (e-mails to the billing admins at 50 / 90 / 100 %). It does not stop spending:
# the hard limits are the game's own daily budget and max_instances (docs/07-threat-model.md).
resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "haggle-garage monthly"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "EUR"
      units         = tostring(var.monthly_budget_eur)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }

  depends_on = [google_project_service.enabled]
}
