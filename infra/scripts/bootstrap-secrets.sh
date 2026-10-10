#!/usr/bin/env bash
# Give every secret Terraform created a value, from this machine (docs/learning/week-07).
#   infra/scripts/bootstrap-secrets.sh <project-id>
# Values travel to gcloud on stdin: never in argv, the shell history, a file or Terraform state.
# Random secrets are created once and kept on later runs; Langfuse keys are copied from .env.
# Database URLs are NOT set here: run `haggle-provision-roles --to-secret-manager <project>`.
set -euo pipefail
project="${1:?usage: $0 <project-id>}"

add() { gcloud secrets versions add "$1" --project "$project" --data-file=- >/dev/null && echo "set  $1"; }
has() {
  gcloud secrets versions list "$1" --project "$project" --filter="state=ENABLED" \
    --format="value(name)" --limit=1 | grep -q .
}

for secret in haggle-mcp-seller-token haggle-mcp-catalog-token haggle-ip-hash-secret haggle-canary-secret; do
  if has "$secret"; then echo "keep $secret"; else openssl rand -base64 32 | tr -d '\n' | add "$secret"; fi
done

for pair in "LANGFUSE_PUBLIC_KEY haggle-langfuse-public-key" "LANGFUSE_SECRET_KEY haggle-langfuse-secret-key"; do
  read -r variable secret <<<"$pair"
  value="$(grep -E "^${variable}=" .env | cut -d= -f2- || true)"
  if [ -z "$value" ]; then echo "skip $secret ($variable not in .env: tracing off in prod)"; continue; fi
  if has "$secret"; then echo "keep $secret"; else printf %s "$value" | add "$secret"; fi
done
