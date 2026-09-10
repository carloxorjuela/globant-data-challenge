#!/usr/bin/env bash
#
# Provisions the Cloud Run + Cloud SQL setup this API runs on.
#
# Written down because "it works on my machine, and also somewhere in GCP"
# is not a deployment. Run it once against an empty project; every command
# is idempotent enough to re-run except the password generation, which
# would rotate the credential.
#
# The database password is generated here and never leaves Secret Manager.
# It is not printed, not committed, and not passed as an environment
# variable to the service.

set -euo pipefail

PROJECT="${PROJECT:-globant-data-challenge-2026}"
REGION="${REGION:-us-central1}"
INSTANCE="${INSTANCE:-globant-challenge-db}"
DB_NAME="challenge"
DB_USER="challenge_app"
SERVICE="globant-data-challenge"
SECRET="globant-database-url"
SA="globant-api@${PROJECT}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com

# Shared-core tiers require the ENTERPRISE edition; the default edition is
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
# rather than an address.
printf 'postgresql+psycopg://%s:%s@/%s?host=/cloudsql/%s' \
  "$DB_USER" "$PASSWORD" "$DB_NAME" "$CONNECTION_NAME" \
  | gcloud secrets create "$SECRET" --data-file=-

unset PASSWORD

# A dedicated runtime identity, rather than the default compute service
# account, so the service holds only the two permissions it actually needs.
gcloud iam service-accounts create globant-api \
  --display-name="Globant challenge API runtime"

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" \
  --role="roles/cloudsql.client" \
  --condition=None

gcloud secrets add-iam-policy-binding "$SECRET" \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor"

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --service-account "$SA" \
  --add-cloudsql-instances "$CONNECTION_NAME" \
  --set-secrets "DATABASE_URL=${SECRET}:latest"
