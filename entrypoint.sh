#!/bin/sh
set -e # Exit immediately if a command exits with a non-zero status.

echo "[Entrypoint] Starting SSH agent and key setup..."

# Check if GIT_SSH_KEY_SECRET_ARN is set
if [ -n "$GIT_SSH_KEY_SECRET_ARN" ]; then
    echo "[Entrypoint] GIT_SSH_KEY_SECRET_ARN is set to: $GIT_SSH_KEY_SECRET_ARN"
    echo "[Entrypoint] Fetching Git SSH key from AWS Secrets Manager..."
    
    # Fetch the secret. AWS CLI v2 uses --query SecretString --output text
    # For AWS CLI v1, you might need to parse JSON differently.
    # The `aws sts get-caller-identity` is a good test for IAM role assumption.
    echo "[Entrypoint] Testing AWS credentials with 'aws sts get-caller-identity'..."
    aws sts get-caller-identity || { echo "[Entrypoint] FATAL: 'aws sts get-caller-identity' failed. Check IAM role and permissions."; exit 1; }
    
    SECRET_OUTPUT=$(aws secretsmanager get-secret-value --secret-id "$GIT_SSH_KEY_SECRET_ARN" --query SecretString --output text --region ${AWS_DEFAULT_REGION:-us-east-1})
    
    if [ -n "$SECRET_OUTPUT" ]; then
        echo "$SECRET_OUTPUT" > /root/.ssh/id_git_rsa
        chmod 600 /root/.ssh/id_git_rsa
        echo "[Entrypoint] Git SSH key fetched from Secrets Manager and saved to /root/.ssh/id_git_rsa"
    else
        echo "[Entrypoint] WARNING: Failed to fetch SSH key from Secrets Manager or secret was empty."
        # Decide if this is a fatal error. For now, we'll let it continue and ssh-add will fail.
    fi
else
    echo "[Entrypoint] WARNING: GIT_SSH_KEY_SECRET_ARN not set. SSH key for Git must be pre-baked or mounted if needed."
    # This will likely cause ssh-add to fail if the file isn't present from another source (like a previous Docker layer or bad mount)
fi

# Start the SSH agent
echo "[Entrypoint] Starting SSH agent..."
eval $(ssh-agent -s) > /dev/null # Start agent and set SSH_AUTH_SOCK etc.

# Add the SSH key.
if [ -f "/root/.ssh/id_git_rsa" ]; then
    echo "[Entrypoint] Adding SSH key /root/.ssh/id_git_rsa to agent..."
    ssh-add /root/.ssh/id_git_rsa
    echo "[Entrypoint] SSH key added. Keys in agent:"
    ssh-add -L
else
    echo "[Entrypoint] WARNING: SSH key /root/.ssh/id_git_rsa not found after attempting to fetch/load. Git SSH operations will likely fail."
fi

echo "[Entrypoint] SSH Agent PID: $SSH_AGENT_PID"
echo "[Entrypoint] SSH Auth Sock: $SSH_AUTH_SOCK"

# Execute the CMD passed to this entrypoint script (e.g., "python main.py")
echo "[Entrypoint] Executing command: $@"
exec "$@"
