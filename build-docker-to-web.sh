#!/usr/bin/env zsh

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration Variables ---
AWS_ACCOUNT_ID="034362041757"
AWS_REGION="us-east-1"
ECR_CLIENT_REPO_NAME="ecs-chaos-lab-creator-client"
ECR_SERVER_REPO_NAME="ecs-chaos-lab-creator-server"
ECS_CLUSTER_NAME="ecs-chaos-lab-cluster"
ECS_SERVICE_NAME="ecs-chaos-lab-app-v3-service-orp02hz5"

# Construct ECR repository URIs
ECR_CLIENT_IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_CLIENT_REPO_NAME}:latest"
ECR_SERVER_IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_SERVER_REPO_NAME}:latest"

# --- Helper Functions ---
log_info() {
    echo "[INFO] $(date +'%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo "[ERROR] $(date +'%Y-%m-%d %H:%M:%S') - $1" >&2
}

# --- Script Logic ---

# 1. Authenticate Docker to ECR
log_info "Authenticating Docker to ECR for region ${AWS_REGION}..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
log_info "Docker ECR authentication successful."

# 2. Build Client Docker Image
log_info "Building client Docker image: ${ECR_CLIENT_IMAGE_URI}..."
docker build -t "${ECR_CLIENT_IMAGE_URI}" -f Dockerfile.client .
log_info "Client Docker image build complete."

# 3. Push Client Docker Image to ECR
log_info "Pushing client Docker image to ECR: ${ECR_CLIENT_IMAGE_URI}..."
docker push "${ECR_CLIENT_IMAGE_URI}"
log_info "Client Docker image push complete."

# 4. Build Server Docker Image
log_info "Building server Docker image: ${ECR_SERVER_IMAGE_URI}..."
docker build -t "${ECR_SERVER_IMAGE_URI}" -f Dockerfile.server .
log_info "Server Docker image build complete."

# 5. Push Server Docker Image to ECR
log_info "Pushing server Docker image to ECR: ${ECR_SERVER_IMAGE_URI}..."
docker push "${ECR_SERVER_IMAGE_URI}"
log_info "Server Docker image push complete."

# 6. Force a new deployment of the ECS Service
log_info "Forcing new deployment for ECS service: ${ECS_SERVICE_NAME} in cluster ${ECS_CLUSTER_NAME}..."
aws ecs update-service --cluster "${ECS_CLUSTER_NAME}" --service "${ECS_SERVICE_NAME}" --force-new-deployment --no-cli-pager
log_info "ECS service update initiated. The new deployment will pull the 'latest' images."

# 7. Wait for service to become stable
log_info "Waiting for service ${ECS_SERVICE_NAME} to become stable..."
aws ecs wait services-stable --cluster "${ECS_CLUSTER_NAME}" --services "${ECS_SERVICE_NAME}" --no-cli-pager
log_info "Service ${ECS_SERVICE_NAME} is stable."

# 8. Get and Echo the New Task ARN
log_info "Fetching new task ARN for service ${ECS_SERVICE_NAME}..."
NEW_TASK_ARN=$(aws ecs list-tasks --cluster "${ECS_CLUSTER_NAME}" --service-name "${ECS_SERVICE_NAME}" --desired-status RUNNING --query "taskArns[0]" --output text --no-cli-pager)

# Ensure variable is quoted and use single = for POSIX compatibility, though == is fine for bash
if [ -z "$NEW_TASK_ARN" ] || [ "$NEW_TASK_ARN" = "None" ] || [ "$NEW_TASK_ARN" = "null" ]; then
    log_error "Could not retrieve new task ARN. The command returned '$NEW_TASK_ARN'. Please check the ECS console."
else
    log_info "New running task ARN: ${NEW_TASK_ARN}"
fi

log_info "Deployment script finished successfully!"
