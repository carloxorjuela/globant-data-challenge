#!/usr/bin/env bash
#
# Provisions the Cloud Run + Cloud SQL setup this API runs on.
#
# Written down because "it works on my machine, and also somewhere in GCP"
# is not a deployment. Run it once against an empty project.
#
# Neither the database password nor the API key leaves Secret Manager. They
# are generated here, piped straight in, and never printed, committed or
# passed to the service as plain environment variables.

set -euo pipefail

PROJECT="${PROJECT:-globant-data-challenge-2026}"
REGION="${REGION:-us-central1}"
INSTANCE="${INSTANCE:-globant-challenge-db}"
DB_NAME="challenge"
DB_USER="challenge_app"
SERVICE="globant-data-challenge"
DB_SECRET="globant-database-url"
KEY_SECRET="globant-api-key"
SA="globant-api@${PROJECT}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com

# Shared-core tiers require the ENTERPRISE edition. The default is
# ENTERPRISE_PLUS, which rejects db-f1-micro outright.
gcloud sql instances create "$INSTANCE" \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-f1-micro \
  --region="$REGION" \
  --storage-size=10GB \
  --storage-type=HDD \
  --no-backup

gcloud sql databases create "$DB_NAME" --instance="$INSTANCE"

PASSWORD="$(python -c 'import secrets,string; print("".join(secrets.choice(string.ascii_letters+string.digits) for _ in range(32)))')"
gcloud sql users create "$DB_USER" --instance="$INSTANCE" --password="$PASSWORD"

CONNECTION_NAME="$(gcloud sql instances describe "$INSTANCE" --format='value(connectionName)')"

# Cloud Run reaches Cloud SQL over a Unix socket, so the host is a path
# rather than an address. printf, never echo: a trailing newline would end up
# inside the secret.
printf 'postgresql+psycopg://%s:%s@/%s?host=/cloudsql/%s' \
  "$DB_USER" "$PASSWORD" "$DB_NAME" "$CONNECTION_NAME" \
  | gcloud secrets create "$DB_SECRET" --data-file=-
unset PASSWORD

# The shared key guarding the write endpoints. Same newline trap: a key with
# a trailing newline never matches the header the client sends.
API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf '%s' "$API_KEY" | gcloud secrets create "$KEY_SECRET" --data-file=-
unset API_KEY

# A dedicated runtime identity instead of the default compute service
# account, so the service holds only the permissions it actually needs.
gcloud iam service-accounts create globant-api \
  --display-name="Globant challenge API runtime"

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" \
  --role="roles/cloudsql.client" \
  --condition=None

for secret in "$DB_SECRET" "$KEY_SECRET"; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${SA}" \
    --role="roles/secretmanager.secretAccessor"
done

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --service-account "$SA" \
  --add-cloudsql-instances "$CONNECTION_NAME" \
  --set-secrets "DATABASE_URL=${DB_SECRET}:latest,API_KEY=${KEY_SECRET}:latest"

echo "Deployed. Retrieve the API key with:"
echo "  gcloud secrets versions access latest --secret=${KEY_SECRET}"
