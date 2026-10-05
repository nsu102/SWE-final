#!/usr/bin/env bash
# Deploy LookFind to AWS. Production settings come from backend/.env.production.
#
#   scripts/deploy.sh            # env + backend + frontend
#   scripts/deploy.sh env        # upload backend/.env.production and restart the Lambda (no image build)
#   scripts/deploy.sh backend    # env + build/push the Lambda image + update the backend stack
#   scripts/deploy.sh frontend   # update the frontend stack, build, upload to S3, invalidate CloudFront
#   scripts/deploy.sh check      # validate backend/.env.production only (no AWS calls)
#   scripts/deploy.sh seed       # load backend/seed (bundled in the image) into RDS; run after `backend`
#
# First deploy of a stack also needs: VPC_ID, SUBNET_IDS (comma-separated) for the backend and
# HOSTED_ZONE_ID for the frontend. Later deploys reuse the stacks' previous values.
set -euo pipefail
cd "$(dirname "$0")/.."

REGION="${REGION:-ap-northeast-2}"
FRONTEND_REGION="us-east-1"               # CloudFront certificates must live in us-east-1
BACKEND_STACK="${BACKEND_STACK:-lookfind-backend}"
FRONTEND_STACK="${FRONTEND_STACK:-lookfind-frontend}"
ECR_REPO="${ECR_REPO:-lookfind-api}"
APP_ENV_SECRET_NAME="${APP_ENV_SECRET_NAME:-lookfind/backend-env}"
ENV_FILE="backend/.env.production"

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { echo "error: $*" >&2; exit 1; }

# Value of KEY in .env.production (last match, outer quotes removed). The file is not sourced:
# it is configuration for the Lambda, not for this shell.
env_value() {
  local line
  line="$(grep -E "^$1=" "$ENV_FILE" | tail -n 1 || true)"
  line="${line#*=}"; line="${line%\"}"; line="${line#\"}"
  printf '%s' "$line"
}

stack_output() {  # region stack key
  aws cloudformation describe-stacks --region "$1" --stack-name "$2" \
    --query "Stacks[0].Outputs[?OutputKey=='$3'].OutputValue" --output text
}

check_env_file() {
  [[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found"
  local key
  for key in FRONTEND_URL CORS_ORIGINS AWS_BUCKET_NAME JWT_SECRET KAKAO_REST_API_KEY KAKAO_REDIRECT_URI; do
    [[ -n "$(env_value "$key")" ]] || die "$key is empty in $ENV_FILE"
  done
  local jwt; jwt="$(env_value JWT_SECRET)"
  (( ${#jwt} >= 32 )) || die "JWT_SECRET in $ENV_FILE must be at least 32 characters"
  if grep -qE '^AWS_(ACCESS_KEY_ID|SECRET_ACCESS_KEY)=.+' "$ENV_FILE"; then
    die "$ENV_FILE contains static AWS keys; the Lambda uses its IAM role, remove them"
  fi
}

# Upload .env.production to Secrets Manager; prints the secret ARN.
sync_env() {
  local arn
  if arn="$(aws secretsmanager describe-secret --region "$REGION" --secret-id "$APP_ENV_SECRET_NAME" --query ARN --output text 2>/dev/null)"; then
    aws secretsmanager put-secret-value --region "$REGION" --secret-id "$APP_ENV_SECRET_NAME" \
      --secret-string "file://$ENV_FILE" >/dev/null
  else
    arn="$(aws secretsmanager create-secret --region "$REGION" --name "$APP_ENV_SECRET_NAME" \
      --description "LookFind backend/.env.production" --secret-string "file://$ENV_FILE" --query ARN --output text)"
  fi
  printf '%s' "$arn"
}

env_version() { shasum -a 256 "$ENV_FILE" | cut -c1-16; }

deploy_backend_stack() {  # extra parameter overrides...
  local params=("AppEnvSecretArn=$APP_ENV_SECRET_ARN" "AppEnvVersion=$(env_version)" "ProductBucketName=$(env_value AWS_BUCKET_NAME)" "$@")
  [[ -n "${VPC_ID:-}" ]] && params+=("VpcId=$VPC_ID")
  [[ -n "${SUBNET_IDS:-}" ]] && params+=("SubnetIds=$SUBNET_IDS")
  aws cloudformation deploy --region "$REGION" --stack-name "$BACKEND_STACK" \
    --template-file infra/aws/backend.yaml --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset --parameter-overrides "${params[@]}"
}

cmd_env() {
  check_env_file
  log "Uploading $ENV_FILE to Secrets Manager ($APP_ENV_SECRET_NAME)"
  APP_ENV_SECRET_ARN="$(sync_env)"
  log "Restarting the API function with the new settings (stack $BACKEND_STACK)"
  deploy_backend_stack
}

cmd_backend() {
  check_env_file
  local account registry tag image
  account="$(aws sts get-caller-identity --region "$REGION" --query Account --output text)"
  registry="$account.dkr.ecr.$REGION.amazonaws.com"
  tag="$(git rev-parse --short HEAD)-$(date +%Y%m%d%H%M%S)"   # unique: Lambda pins the image digest per update
  image="$registry/$ECR_REPO:$tag"

  log "ECR repository $ECR_REPO"
  aws ecr describe-repositories --region "$REGION" --repository-names "$ECR_REPO" >/dev/null 2>&1 \
    || aws ecr create-repository --region "$REGION" --repository-name "$ECR_REPO" >/dev/null
  aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$registry"

  log "Building $image (linux/amd64)"
  # amd64 + no provenance: Lambda (x86_64) rejects arm64 images built on Apple Silicon and OCI attestation manifests.
  docker buildx build --platform linux/amd64 --provenance=false \
    -f backend/deploy/lambda/Dockerfile -t "$image" --push backend

  log "Uploading $ENV_FILE to Secrets Manager ($APP_ENV_SECRET_NAME)"
  APP_ENV_SECRET_ARN="$(sync_env)"

  log "Deploying stack $BACKEND_STACK"
  deploy_backend_stack "ImageUri=$image"
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$BACKEND_STACK" --query "Stacks[0].Outputs" --output table
}

cmd_seed() {
  local function out
  function="$(stack_output "$REGION" "$BACKEND_STACK" SeedFunctionName)"
  [[ -n "$function" && "$function" != None ]] || die "no SeedFunctionName output on $BACKEND_STACK (run: $0 backend)"
  out="$(mktemp)"
  log "Loading the catalog seed into RDS via $function (takes a few minutes)"
  aws lambda invoke --region "$REGION" --function-name "$function" --cli-read-timeout 900 \
    --payload '{}' --cli-binary-format raw-in-base64-out "$out" --query FunctionError --output text \
    | grep -q None || { cat "$out"; echo; die "seed load failed (see CloudWatch logs of $function)"; }
  cat "$out"; echo
  rm -f "$out"
}

cmd_frontend() {
  local api_domain params bucket distribution
  api_domain="$(stack_output "$REGION" "$BACKEND_STACK" ApiOriginDomain)"
  [[ -n "$api_domain" && "$api_domain" != None ]] || die "no ApiOriginDomain output on $BACKEND_STACK (deploy the backend first)"
  params=("ApiOriginDomain=$api_domain")
  [[ -n "${HOSTED_ZONE_ID:-}" ]] && params+=("HostedZoneId=$HOSTED_ZONE_ID")

  log "Deploying stack $FRONTEND_STACK ($FRONTEND_REGION)"
  aws cloudformation deploy --region "$FRONTEND_REGION" --stack-name "$FRONTEND_STACK" \
    --template-file infra/aws/frontend.yaml --no-fail-on-empty-changeset --parameter-overrides "${params[@]}"

  log "Building the static frontend"
  (cd frontend && npm ci && npm run build)

  bucket="$(stack_output "$FRONTEND_REGION" "$FRONTEND_STACK" BucketName)"
  distribution="$(stack_output "$FRONTEND_REGION" "$FRONTEND_STACK" DistributionId)"
  log "Uploading frontend/out to s3://$bucket"
  aws s3 sync frontend/out "s3://$bucket" --region "$FRONTEND_REGION" --delete
  log "Invalidating CloudFront $distribution"
  aws cloudfront create-invalidation --region "$FRONTEND_REGION" --distribution-id "$distribution" --paths "/*" --query Invalidation.Id --output text
  log "Done: $(stack_output "$FRONTEND_REGION" "$FRONTEND_STACK" Url)"
}

if [[ "${1:-}" == check ]]; then
  check_env_file
  echo "$ENV_FILE ok (bucket=$(env_value AWS_BUCKET_NAME), frontend=$(env_value FRONTEND_URL), version=$(env_version))"
  exit 0
fi
command -v aws >/dev/null || die "AWS CLI v2 is required"
case "${1:-all}" in
  env) cmd_env ;;
  backend) cmd_backend ;;
  frontend) cmd_frontend ;;
  seed) cmd_seed ;;
  all) cmd_backend; cmd_frontend ;;
  *) die "usage: $0 [all|env|backend|frontend|seed|check]" ;;
esac
