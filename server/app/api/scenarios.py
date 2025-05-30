# --- START server/app/api/scenarios.py ---
import os
import time
import hashlib
import subprocess
import json
import glob
# import requests # Not currently used
from flask import jsonify, request, current_app # Blueprint not needed here if bp is imported
from app.api import bp # Import the blueprint from the package __init__
import shutil

# NEW: Import timer functions
from app.timer_manager import init_timer as initialize_session_timer
from app.timer_manager import extend_timer as extend_session_timer
# remove_timer will be used in terminal_events.py for cleanup in a later step (or this one if preferred)

SCENARIO_SESSIONS = {}

BASE_TERRAFORM_TEMPLATE = """

provider "aws" {{
  region = "us-east-1"
}}

module "base_infrastructure" {{
  source      = "git::ssh://git@github.com/weka/Chaos-Lab.git//modules/base"
  name_prefix = "{terraform_name_prefix}" 
}}

module "scenario_chaos" {{
  source      = "git::ssh://git@github.com/weka/Chaos-Lab.git//{scenario_module_git_path}"
  name_prefix = "{terraform_name_prefix}"
  subnet_id         = module.base_infrastructure.subnet_id
  private_subnet_id = module.base_infrastructure.private_subnet_id
  security_group_id = module.base_infrastructure.security_group_id
  key_name          = module.base_infrastructure.keypair_name
  random_pet_id     = module.base_infrastructure.random_pet_id
  private_key_pem = module.base_infrastructure.private_key_pem
  other_private_ips = module.base_infrastructure.instance_private_ips
  other_public_ips  = module.base_infrastructure.instance_public_ips
  iam_role_name            = module.base_infrastructure.ec2_instance_role_name
  iam_policy_arn           = module.base_infrastructure.describe_instances_policy_arn
  iam_instance_profile_name = module.base_infrastructure.ec2_instance_profile_name
  ami_id                    = module.base_infrastructure.ami_id
}}
"""

@bp.route('/scenarios', methods=['POST'])
def create_scenario():
    data = request.json
    if not data:
        current_app.logger.error("API: No data provided in POST /scenarios request.")
        return jsonify({'error': 'No data provided'}), 400

    button_variable_repo_name = data.get('repo') 
    if not button_variable_repo_name:
        current_app.logger.error("API: Missing 'repo' parameter in POST /scenarios request.")
        return jsonify({'error': 'Missing required parameter: repo'}), 400
    
    scenario_module_git_path = f"modules/{button_variable_repo_name}"
    current_app.logger.info(f"API: Processing scenario request for repo: {button_variable_repo_name}, module path: //{scenario_module_git_path}")

    timestamp = str(time.time())
    hash_str = hashlib.sha256(timestamp.encode()).hexdigest()[:5]
    terraform_name_prefix_for_run = f'clw-{button_variable_repo_name}-{hash_str}' 
    session_id = terraform_name_prefix_for_run # Use this as the unique session identifier
    
    new_dir_name = f"{terraform_name_prefix_for_run}_scenario_dir"
    
    # Adjust base_work_dir path relative to current_app.root_path
    # If current_app.root_path is /server/app, then '..' goes to /server
    base_work_dir = os.path.join(current_app.root_path, '..', 'scenarios_work_dir')
    scenario_specific_dir = os.path.join(base_work_dir, new_dir_name)
    
    tf_file_path_on_server = os.path.join(scenario_specific_dir, 'main.tf')
    
    try:
        os.makedirs(base_work_dir, exist_ok=True) # Ensure base dir exists first
        os.makedirs(scenario_specific_dir, exist_ok=True)
        current_app.logger.debug(f"API: Created scenario working directory: {scenario_specific_dir}")

        tf_file_content = BASE_TERRAFORM_TEMPLATE.format(
            terraform_name_prefix=terraform_name_prefix_for_run,
            scenario_module_git_path=scenario_module_git_path
        )
        
        with open(tf_file_path_on_server, 'w') as file:
            file.write(tf_file_content)
        current_app.logger.debug(f"API: Terraform main.tf generated at: {tf_file_path_on_server}:\n{tf_file_content[:200]}...") # Log snippet

        current_app.logger.info(f"API: Running Terraform init in {scenario_specific_dir}")
        init_process = subprocess.run(
            ['terraform', 'init', '-no-color', '-input=false'], 
            capture_output=True, text=True, cwd=scenario_specific_dir, timeout=600, check=True # check=True will raise CalledProcessError on non-zero exit
        )
        current_app.logger.info(f"API: Terraform init STDOUT:\n{init_process.stdout}")
        # No need to check init_process.returncode if check=True is used

        current_app.logger.info(f"API: Running Terraform apply in {scenario_specific_dir}")
        apply_process = subprocess.run(
            ['terraform', 'apply', '--auto-approve', '-no-color', '-input=false'], 
            capture_output=True, text=True, cwd=scenario_specific_dir, timeout=900, check=True
        )
        current_app.logger.info(f"API: Terraform apply STDOUT:\n{apply_process.stdout}")
        current_app.logger.info(f"API: Terraform apply completed for {terraform_name_prefix_for_run}.")

        # --- Read IP ---
        ip_file_path = os.path.join(scenario_specific_dir, 'scenario_chaos_ip.txt')
        instance_ip = None
        if os.path.exists(ip_file_path):
            with open(ip_file_path, 'r') as f:
                instance_ip = f.readline().strip()
            current_app.logger.info(f"API: Read IP '{instance_ip}' from {ip_file_path}")
        
        if not instance_ip:
            current_app.logger.warning(f"API: Failed to read instance IP from {ip_file_path}. Attempting TF output fallback.")
            output_result = subprocess.run(['terraform', 'output', '-json', 'scenario_instance_public_ip'], capture_output=True, text=True, cwd=scenario_specific_dir)
            if output_result.returncode == 0 and output_result.stdout.strip() and output_result.stdout.strip().lower() != "null":
                try:
                    ip_data_parsed = json.loads(output_result.stdout)
                    instance_ip = ip_data_parsed.get('value') if isinstance(ip_data_parsed, dict) else ip_data_parsed
                    current_app.logger.info(f"API: Read IP '{instance_ip}' from terraform output as fallback.")
                except json.JSONDecodeError:
                    current_app.logger.error(f"API: Failed to parse TF output for IP fallback: {output_result.stdout}")
            if not instance_ip:
                current_app.logger.error("API: Missing 'instance_public_ip' after all attempts.")
                raise Exception('Missing "instance_public_ip": Failed to get from file and terraform output.')

        # --- Read PEM key ---
        pem_files_on_disk = glob.glob(os.path.join(scenario_specific_dir, "*-key.pem"))
        private_key_pem_content = None
        actual_pem_filename_on_server = "PEM_FILE_NOT_FOUND_ON_DISK"
        if pem_files_on_disk:
            actual_pem_filename_on_server = pem_files_on_disk[0]
            with open(actual_pem_filename_on_server, 'r') as f:
                private_key_pem_content = f.read()
            current_app.logger.info(f"API: Read PEM content from {actual_pem_filename_on_server}")
        
        if not private_key_pem_content:
            current_app.logger.warning(f"API: PEM file not found via glob. Trying TF output for 'private_key_pem'.")
            output_result_pem = subprocess.run(['terraform', 'output', '-json', 'private_key_pem'], capture_output=True, text=True, cwd=scenario_specific_dir)
            if output_result_pem.returncode == 0 and output_result_pem.stdout.strip() and output_result_pem.stdout.strip().lower() != "null":
                try:
                    pem_data_parsed = json.loads(output_result_pem.stdout)
                    private_key_pem_content = pem_data_parsed.get('value') if isinstance(pem_data_parsed, dict) else pem_data_parsed
                    if private_key_pem_content:
                         current_app.logger.info("API: Read PEM content from terraform output as fallback.")
                except json.JSONDecodeError:
                    current_app.logger.error(f"API: Failed to parse TF output for PEM fallback: {output_result_pem.stdout}")
            if not private_key_pem_content:
                current_app.logger.error("API: Missing 'private_key_pem' after all attempts.")
                raise Exception('Missing "private_key_pem": Failed to get from file and terraform output.')

        # --- Get AWS Key Pair Name ---
        aws_key_pair_name = None
        output_key_name_result = subprocess.run(
            ['terraform', 'output', '-raw', 'key_name'],
            capture_output=True, text=True, cwd=scenario_specific_dir, timeout=60
        )
        if output_key_name_result.returncode == 0 and output_key_name_result.stdout.strip():
            aws_key_pair_name = output_key_name_result.stdout.strip()
            current_app.logger.info(f"API: Read AWS key_name '{aws_key_pair_name}' from terraform output.")
        else:
            current_app.logger.warning(f"API: Could not retrieve 'key_name' from Terraform output. Stderr: {output_key_name_result.stderr}")
        
        current_app.logger.info(f"API: Final - Instance IP: {instance_ip}, AWS Key Pair Name: {aws_key_pair_name}, PEM File used: {actual_pem_filename_on_server}")

        SCENARIO_SESSIONS[session_id] = {
            "repo": button_variable_repo_name,
            "status": "provisioned",
            "terraform_dir": scenario_specific_dir,
            "instance_ip": instance_ip,
            "private_key_pem_content": private_key_pem_content,
            "key_name_aws": aws_key_pair_name, 
            "terraform_name_prefix_for_run": terraform_name_prefix_for_run
        }
        
        # NEW: Initialize timer for the session
        initial_end_time = initialize_session_timer(session_id, app_logger=current_app.logger)
        current_app.logger.info(f"API: Scenario '{button_variable_repo_name}' (ID: {session_id}) provisioned. Timer initialized, ends at epoch {initial_end_time}.")

        return jsonify({
            'message': f'Scenario {button_variable_repo_name} provisioned! IP: {instance_ip}',
            'sessionId': session_id,
            'websocketPath': '/terminal_ws',
            'endTime': initial_end_time # NEW: Return end time to the client
        }), 200

    except subprocess.TimeoutExpired as e:
        error_msg = f"Terraform command timed out: {' '.join(e.cmd)}"
        current_app.logger.error(error_msg, exc_info=True)
        if os.path.exists(scenario_specific_dir):
            current_app.logger.info(f"API: Attempting destroy due to timeout: {scenario_specific_dir}")
            subprocess.run(['terraform', 'destroy', '--auto-approve', '-no-color', '-input=false'], cwd=scenario_specific_dir, timeout=300)
        return jsonify({'error': error_msg, 'details': 'Terraform operation timed out.'}), 500
    except subprocess.CalledProcessError as e:
        error_msg = f"Terraform command '{' '.join(e.cmd)}' failed with code {e.returncode}."
        current_app.logger.error(f"{error_msg}\nTerraform STDOUT:\n{e.stdout}\nTerraform STDERR:\n{e.stderr}", exc_info=True)
        if os.path.exists(scenario_specific_dir): 
            current_app.logger.info(f"API: Attempting destroy due to failed TF command: {scenario_specific_dir}")
            subprocess.run(['terraform', 'destroy', '--auto-approve', '-no-color', '-input=false'], cwd=scenario_specific_dir, timeout=300)
        return jsonify({'error': error_msg, 'details': e.stderr or e.stdout or "Terraform command failed."}), 500
    except Exception as e:
        error_msg = f"An unexpected error occurred in create_scenario: {str(e)}"
        current_app.logger.error(error_msg, exc_info=True)
        if 'scenario_specific_dir' in locals() and os.path.exists(scenario_specific_dir):
            current_app.logger.info(f"API: Attempting destroy due to unexpected error: {scenario_specific_dir}")
            try:
                subprocess.run(['terraform', 'destroy', '--auto-approve', '-no-color', '-input=false'], cwd=scenario_specific_dir, timeout=300)
            except Exception as cleanup_e:
                current_app.logger.error(f"API: Error during cleanup attempt: {cleanup_e}")
        return jsonify({'error': error_msg, 'details': str(e)}), 500

# NEW: Endpoint to extend timer
@bp.route('/scenarios/<session_id>/extend_timer', methods=['POST'])
def extend_scenario_timer_route(session_id): # Renamed function to avoid potential import conflicts
    current_app.logger.info(f"API: Request to extend timer for session: {session_id}")
    if session_id not in SCENARIO_SESSIONS: # Check if session exists
        current_app.logger.warning(f"API: Extend timer request for non-existent session: {session_id}")
        return jsonify({'error': 'Scenario session not found'}), 404

    new_end_time = extend_session_timer(session_id, app_logger=current_app.logger)
    if new_end_time:
        current_app.logger.info(f"API: Timer for {session_id} extended. New end time (Epoch): {new_end_time}.")
        # In a later step (Step E), we'll add a Socket.IO emit here to notify clients
        return jsonify({
            'message': 'Timer extended successfully',
            'sessionId': session_id,
            'newEndTime': new_end_time # Return the new end time
        }), 200
    else:
        # This case might occur if extend_session_timer returns None for other reasons (e.g. session removed between checks)
        current_app.logger.error(f"API: Failed to extend timer for session {session_id} (extend_session_timer returned None).")
        return jsonify({'error': 'Failed to extend timer. Session might no longer be valid.'}), 500
# --- END server/app/api/scenarios.py ---
