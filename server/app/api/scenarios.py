import os
import time
import hashlib
import subprocess
import zipfile # Will be removed for terminal flow, kept for now if you want to revert
# import requests # Kept for now, but the .tf file content is less critical for terminal echo phase
from flask import Blueprint, jsonify, request, current_app, send_from_directory # send_from_directory might be removed
from app.api import bp
# from app import socketio # Not needed here directly if events are in terminal_events.py

# A simple in-memory store for scenario sessions for this phase
# In a real app, use Redis or a database
SCENARIO_SESSIONS = {}

@bp.route('/scenarios', methods=['POST'])
def create_scenario():
    """
    Handle POST requests to create/prepare a scenario.
    For Phase 1 of terminal integration, this will still run Terraform
    but will respond with a session ID for WebSocket connection.
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        button_variable = data.get('repo')
        if not button_variable:
            return jsonify({'error': 'Missing required parameter: repo'}), 400

        current_app.logger.info(f"Processing scenario request for repo: {button_variable}")

        # --- Terraform part (kept for now, but its output isn't used by terminal yet) ---
        # Fetch Terraform file from GitHub
        # tf_file_url = f'https://raw.githubusercontent.com/NanoBlazer915/CST-Scenario-Lab/main/scenario-tfs/{button_variable}/{button_variable}.tf'
        # tf_file_response = requests.get(tf_file_url)
        # if tf_file_response.status_code != 200:
        #     current_app.logger.error(f"Failed to fetch Terraform file: {tf_file_response.status_code}")
        #     return jsonify({'error': f"Failed to fetch Terraform file: {tf_file_response.status_code}"}), 404
        # tf_file_content = tf_file_response.text

        # Create unique directory for processing
        timestamp = str(time.time())
        hash_str = hashlib.sha256(timestamp.encode()).hexdigest()[:8]
        new_dir_name = f"{button_variable}_{hash_str}_scenario_dir" # More descriptive
        
        # Ensure base 'scenarios_work_dir' exists
        base_work_dir = os.path.join(current_app.root_path, '..', 'scenarios_work_dir') # Place it outside /server
        os.makedirs(base_work_dir, exist_ok=True)
        scenario_specific_dir = os.path.join(base_work_dir, new_dir_name)
        os.makedirs(scenario_specific_dir, exist_ok=True)
        current_app.logger.debug(f"Created directory: {scenario_specific_dir}")

        # Write Terraform file (Example - in real scenario, fetch it)
        tf_file_path = os.path.join(scenario_specific_dir, 'main.tf')
        # For Phase 1, we can even use a dummy Terraform file if real provisioning is slow/costly for testing UI
        dummy_tf_content = """
        # resource "null_resource" "example" {} 
        # output "message" { value = "Terraform apply for ${var.scenario_name} complete." }
        # variable "scenario_name" { default = "dummy_scenario" }
        """
        # with open(tf_file_path, 'w') as file:
        #     file.write(tf_file_content) # Or dummy_tf_content for testing
        # current_app.logger.debug(f"Terraform file written to: {tf_file_path}")

        # Run Terraform commands (Placeholder - you'd re-enable this)
        # current_app.logger.info(f"Running Terraform in {scenario_specific_dir}")
        # subprocess.run(['terraform', 'init'], check=True, cwd=scenario_specific_dir)
        # subprocess.run(['terraform', 'apply', '--auto-approve', '-var', f'scenario_name={button_variable}'], check=True, cwd=scenario_specific_dir)
        current_app.logger.info(f"Terraform operations placeholder for {button_variable} completed.")
        # --- End Terraform part ---

        # Generate a unique session ID for the terminal
        session_id = f"{button_variable}-{hash_str}"
        SCENARIO_SESSIONS[session_id] = {
            "repo": button_variable,
            "status": "ready",
            "terraform_dir": scenario_specific_dir
            # In a real app, you'd store IP, credentials, or PTY process here
        }
        current_app.logger.info(f"Scenario '{button_variable}' ready. Session ID: {session_id}")

        return jsonify({
            'message': f'Scenario {button_variable} initialized.',
            'sessionId': session_id,
            'websocketPath': '/terminal_ws' # This will be the Socket.IO namespace
        }), 200

    except subprocess.CalledProcessError as e:
        error_msg = f"Terraform command failed: {e.cmd}\nOutput: {e.output.decode('utf-8') if e.output else 'No output'}"
        current_app.logger.error(error_msg)
        return jsonify({'error': error_msg}), 500
    except Exception as e:
        error_msg = f"An unexpected error occurred: {str(e)}"
        current_app.logger.error(error_msg, exc_info=True) # Log full traceback
        return jsonify({'error': error_msg}), 500

# The download endpoint is likely no longer needed for the terminal flow
# You can comment it out or remove it if the zip file is fully replaced.
# @bp.route('/downloads/<path:filename>', methods=['GET'])
# def download_file(filename):
#     downloads_dir = os.path.join(current_app.root_path, 'downloads') # Original path
#     # Ensure this path is correct or update if downloads are now elsewhere
#     return send_from_directory(directory=downloads_dir, path=filename, as_attachment=True)
