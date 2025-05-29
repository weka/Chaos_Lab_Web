import os
import time
import hashlib
import subprocess
import json
import glob
import requests
from flask import Blueprint, jsonify, request, current_app
from app.api import bp
import shutil

SCENARIO_SESSIONS = {}

# This template is now simpler as we're not defining root outputs here
# if the modules themselves will provide them via `terraform output -json` OR via local_file
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
        return jsonify({'error': 'No data provided'}), 400

    button_variable_repo_name = data.get('repo') 
    if not button_variable_repo_name:
        return jsonify({'error': 'Missing required parameter: repo'}), 400
    
    scenario_module_git_path = f"modules/{button_variable_repo_name}"

    current_app.logger.info(f"Processing scenario request for repo: {button_variable_repo_name}, module path: //{scenario_module_git_path}")

    timestamp = str(time.time())
    hash_str = hashlib.sha256(timestamp.encode()).hexdigest()[:5]
    terraform_name_prefix_for_run = f'clw-{button_variable_repo_name}-{hash_str}' 
    
    new_dir_name = f"{terraform_name_prefix_for_run}_scenario_dir"
    
    base_work_dir = os.path.join(current_app.root_path, '..', 'scenarios_work_dir')
    os.makedirs(base_work_dir, exist_ok=True)
    scenario_specific_dir = os.path.join(base_work_dir, new_dir_name)
    
    os.makedirs(scenario_specific_dir, exist_ok=True)
    current_app.logger.debug(f"Created scenario working directory: {scenario_specific_dir}")

    tf_file_path_on_server = os.path.join(scenario_specific_dir, 'main.tf')
    
    try:
        tf_file_content = BASE_TERRAFORM_TEMPLATE.format(
            terraform_name_prefix=terraform_name_prefix_for_run,
            scenario_module_git_path=scenario_module_git_path
        )
        
        with open(tf_file_path_on_server, 'w') as file:
            file.write(tf_file_content)
        current_app.logger.debug(f"Terraform main.tf generated at: {tf_file_path_on_server}:\n{tf_file_content}")

        current_app.logger.info(f"Running Terraform init in {scenario_specific_dir}")
        init_process = subprocess.run(
            ['terraform', 'init', '-no-color', '-input=false'], 
            capture_output=True, text=True, cwd=scenario_specific_dir, timeout=600
        )
        current_app.logger.info(f"Terraform init STDOUT:\n{init_process.stdout}")
        if init_process.returncode != 0:
            current_app.logger.error(f"Terraform init FAILED. STDERR:\n{init_process.stderr}")
            raise subprocess.CalledProcessError(init_process.returncode, init_process.args, output=init_process.stdout, stderr=init_process.stderr)

        current_app.logger.info(f"Running Terraform apply in {scenario_specific_dir}")
        apply_process = subprocess.run(
            ['terraform', 'apply', '--auto-approve', '-no-color', '-input=false'], 
            capture_output=True, text=True, cwd=scenario_specific_dir, timeout=900
        )
        current_app.logger.info(f"Terraform apply STDOUT:\n{apply_process.stdout}")
        if apply_process.returncode != 0:
            current_app.logger.error(f"Terraform apply FAILED. STDERR:\n{apply_process.stderr}")
            raise subprocess.CalledProcessError(apply_process.returncode, apply_process.args, output=apply_process.stdout, stderr=apply_process.stderr)
        
        current_app.logger.info(f"Terraform apply completed for {terraform_name_prefix_for_run}.")

        # --- Read IP from scenario_chaos_ip.txt ---
        ip_file_path = os.path.join(scenario_specific_dir, 'scenario_chaos_ip.txt')
        instance_ip = None
        if os.path.exists(ip_file_path):
            with open(ip_file_path, 'r') as f:
                instance_ip = f.readline().strip() # Read first line and strip whitespace
            current_app.logger.info(f"Read IP '{instance_ip}' from {ip_file_path}")
        
        if not instance_ip:
            current_app.logger.error(f"Failed to read instance IP from {ip_file_path}. File content might be empty or file not found.")
            # Attempt to get it from terraform output as a fallback if the file method fails,
            # assuming the scenario_chaos module outputs 'scenario_instance_public_ip'
            output_result = subprocess.run(['terraform', 'output', '-json', 'scenario_instance_public_ip'], capture_output=True, text=True, cwd=scenario_specific_dir)
            if output_result.returncode == 0 and output_result.stdout.strip() != "null":
                try:
                    instance_ip = json.loads(output_result.stdout) # Will be the direct value if -raw, or needs .get('value') if full json
                    if isinstance(instance_ip, dict): # If full JSON output for the var
                        instance_ip = instance_ip.get('value')
                    current_app.logger.info(f"Read IP '{instance_ip}' from terraform output as fallback.")
                except json.JSONDecodeError:
                    current_app.logger.error(f"Failed to parse TF output for IP fallback: {output_result.stdout}")
                    instance_ip = None # Ensure it's None if parsing fails
            if not instance_ip:
                raise Exception('Missing "instance_public_ip": Failed to get from scenario_chaos_ip.txt and terraform output.')

        # --- Read PEM key content from the randomly named PEM file ---
        pem_files_on_disk = glob.glob(os.path.join(scenario_specific_dir, "*-key.pem"))
        private_key_pem_content = None
        actual_pem_filename_on_server = "PEM_FILE_NOT_FOUND_ON_DISK"

        if pem_files_on_disk:
            actual_pem_filename_on_server = pem_files_on_disk[0]
            with open(actual_pem_filename_on_server, 'r') as f:
                private_key_pem_content = f.read()
            current_app.logger.info(f"Read PEM content from {actual_pem_filename_on_server}")
        
        if not private_key_pem_content:
            # Fallback to terraform output if local_file method failed
            current_app.logger.warning(f"PEM file not found via glob in {scenario_specific_dir}. Trying terraform output for 'private_key_pem'.")
            output_result_pem = subprocess.run(['terraform', 'output', '-json', 'private_key_pem'], capture_output=True, text=True, cwd=scenario_specific_dir)
            if output_result_pem.returncode == 0 and output_result_pem.stdout.strip() != "null":
                try:
                    pem_data = json.loads(output_result_pem.stdout)
                    private_key_pem_content = pem_data.get('value') if isinstance(pem_data, dict) else pem_data
                    if private_key_pem_content:
                         current_app.logger.info("Read PEM content from terraform output as fallback.")
                except json.JSONDecodeError:
                    current_app.logger.error(f"Failed to parse TF output for PEM fallback: {output_result_pem.stdout}")
            if not private_key_pem_content:
                raise Exception('Missing "private_key_pem": Failed to get from *-key.pem file and terraform output. Ensure base_infrastructure module outputs it or local_file writes it.')

        # --- Get AWS Key Pair Name (for deletion later) ---
        aws_key_pair_name = None
        output_key_name_result = subprocess.run(
            ['terraform', 'output', '-raw', 'key_name'], # Use -raw to get the direct string value
            capture_output=True, text=True, cwd=scenario_specific_dir, timeout=60
        )
        if output_key_name_result.returncode == 0 and output_key_name_result.stdout.strip():
            aws_key_pair_name = output_key_name_result.stdout.strip()
            current_app.logger.info(f"Read AWS key_name '{aws_key_pair_name}' from terraform output.")
        else:
            current_app.logger.warning(f"Could not retrieve 'key_name' from Terraform output. Stderr: {output_key_name_result.stderr}")
        
        current_app.logger.info(f"Final - Instance IP: {instance_ip}, AWS Key Pair Name: {aws_key_pair_name}, PEM File used: {actual_pem_filename_on_server}")

        session_id = terraform_name_prefix_for_run
        SCENARIO_SESSIONS[session_id] = {
            "repo": button_variable_repo_name,
            "status": "provisioned",
            "terraform_dir": scenario_specific_dir,
            "instance_ip": instance_ip,
            "private_key_pem_content": private_key_pem_content,
            "key_name_aws": aws_key_pair_name, 
            "terraform_name_prefix_for_run": terraform_name_prefix_for_run
        }
        current_app.logger.info(f"Scenario '{button_variable_repo_name}' (run as {terraform_name_prefix_for_run}) provisioned. Session ID: {session_id}")

        return jsonify({
            'message': f'Scenario {button_variable_repo_name} provisioned! IP: {instance_ip}',
            'sessionId': session_id,
            'websocketPath': '/terminal_ws'
        }), 200

    # ... (exception handling blocks remain largely the same, ensure they try to destroy if scenario_specific_dir exists) ...
    except subprocess.TimeoutExpired as e:
        error_msg = f"Terraform command timed out: {' '.join(e.cmd)}"
        current_app.logger.error(error_msg)
        if os.path.exists(scenario_specific_dir):
            current_app.logger.info(f"Attempting destroy due to timeout: {scenario_specific_dir}")
            subprocess.run(['terraform', 'destroy', '--auto-approve', '-no-color'], cwd=scenario_specific_dir, timeout=300)
        return jsonify({'error': error_msg, 'details': 'Terraform operation timed out.'}), 500
    except subprocess.CalledProcessError as e:
        error_msg = f"Terraform command '{' '.join(e.cmd)}' failed with code {e.returncode}."
        current_app.logger.error(f"{error_msg}\nTerraform STDOUT:\n{e.stdout}\nTerraform STDERR:\n{e.stderr}")
        if os.path.exists(scenario_specific_dir): 
            current_app.logger.info(f"Attempting destroy due to failed TF command: {scenario_specific_dir}")
            subprocess.run(['terraform', 'destroy', '--auto-approve', '-no-color'], cwd=scenario_specific_dir, timeout=300)
        return jsonify({'error': error_msg, 'details': e.stderr or e.stdout or "Terraform command failed."}), 500
    except Exception as e:
        error_msg = f"An unexpected error occurred in create_scenario: {str(e)}"
        current_app.logger.error(error_msg, exc_info=True)
        if 'scenario_specific_dir' in locals() and os.path.exists(scenario_specific_dir): # Ensure var is defined
            current_app.logger.info(f"Attempting destroy due to unexpected error: {scenario_specific_dir}")
            try:
                subprocess.run(['terraform', 'destroy', '--auto-approve', '-no-color'], cwd=scenario_specific_dir, timeout=300)
            except Exception as cleanup_e:
                current_app.logger.error(f"Error during cleanup attempt: {cleanup_e}")
        return jsonify({'error': error_msg}), 500
