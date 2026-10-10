#!/usr/bin/env bash
# Build, push and deploy the three services, tagged with the current commit.
#   infra/scripts/deploy.sh <project-id>
# Refuses to deploy a dirty tree: the image tag must say exactly which code is running.
set -euo pipefail
project="${1:?usage: $0 <project-id>}"
region="europe-west1"
repo="${region}-docker.pkg.dev/${project}/haggle"

if [ -n "$(git status --porcelain)" ]; then
  echo "Commit your changes first: the image tag is the git commit." >&2
  exit 1
fi
sha="$(git rev-parse --short HEAD)"

for service in api seller mcp; do
  image="${repo}/${service}:${sha}"
  echo "== ${image}"
  docker build --quiet -f "services/${service}/Dockerfile" --build-arg "GIT_SHA=${sha}" -t "$image" .
  docker push --quiet "$image"
done

terraform -chdir=infra/terraform apply -auto-approve -input=false \
  -var "images={api=\"${repo}/api:${sha}\",seller=\"${repo}/seller:${sha}\",mcp=\"${repo}/mcp:${sha}\"}"
terraform -chdir=infra/terraform output -raw api_url && echo
