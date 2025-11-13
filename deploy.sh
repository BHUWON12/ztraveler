#!/bin/bash
set -e
set -a
source .env
set +a

SERVICE_NAME="ztraveler-backend"
REGION="us-central1"
IMAGE_URI="us-central1-docker.pkg.dev/gen-lang-client-0193173099/ztraveler-repo/${SERVICE_NAME}:latest"

echo "🧱 Building Docker image..."
docker buildx build --platform linux/amd64 -t "${IMAGE_URI}" .

echo "📤 Pushing image to Artifact Registry..."
docker push "${IMAGE_URI}"

echo "🚀 Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE_URI}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --timeout 900 \
  --max-instances 3 \
  --memory 1Gi \
  --cpu 1 \
  --set-env-vars \
MONGO_URI="${MONGO_URI}",\
MONGO_DB="${MONGO_DB}",\
REDIS_URL="${REDIS_URL}",\
CACHE_TTL="${CACHE_TTL}",\
COLL_HOTELS="${COLL_HOTELS}",\
COLL_ATTRACTIONS="${COLL_ATTRACTIONS}",\
COLL_EVENTS="${COLL_EVENTS}",\
COLL_FLIGHTS="${COLL_FLIGHTS}",\
COLL_TRANSPORTS="${COLL_TRANSPORTS}",\
GOOGLE_API_KEY="${GOOGLE_API_KEY}",\
ENV="${ENV}",\
PORT="${PORT}",\
LOG_LEVEL="${LOG_LEVEL}"

echo "✅ Deployment triggered successfully!"
echo "🌐 Visit: https://console.cloud.google.com/run/detail/${REGION}/${SERVICE_NAME}"
echo "🩺 Health check: curl https://${SERVICE_NAME}-${PROJECT_ID}.${REGION}.run.app/health"
