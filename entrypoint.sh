#!/bin/sh
set -e 

echo "[Entrypoint] Starting SSH agent setup..."
eval $(ssh-agent -s) > /dev/null

if [ -f "/root/.ssh/id_git_rsa" ]; then
    echo "[Entrypoint] Adding SSH key /root/.ssh/id_git_rsa to agent..."
    ssh-add /root/.ssh/id_git_rsa
    echo "[Entrypoint] SSH key added. Keys in agent:"
    ssh-add -L
else
    echo "[Entrypoint] WARNING: SSH key /root/.ssh/id_git_rsa not found."
fi

echo "[Entrypoint] SSH Agent PID: $SSH_AGENT_PID"
echo "[Entrypoint] SSH Auth Sock: $SSH_AUTH_SOCK"

echo "[Entrypoint] Executing command: $@"
exec "$@"
