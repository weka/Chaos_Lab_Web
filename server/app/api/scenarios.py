import os
import time
import hashlib
import subprocess
import zipfile
import base64
import requests
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from app.api import bp

@bp.route('/scenarios', methods=['POST', 'OPTIONS', 'HEAD'])
def create_scenario():
    """Handle POST requests to create a scenario and make it available for download."""
    # Immediately respond to OPTIONS or HEAD requests.
    if request.method in ['OPTIONS', 'HEAD']:
        return '', 200

    try:
        # Extract and validate request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        button_variable = data.get('repo')
        if not button_variable:
            return jsonify({'error': 'Missing required parameter: repo'}), 400

        # Get region from payload; default to "virginia" if not provided.
        let_region = data.get('region') or 'virginia'
        region = let_region.lower()

        s3_bucket_name = 'cst-chaos-lab'  # Replace with your actual S3 bucket name
        current_app.logger.info(f"Processing request for repo: {button_variable}")

        # Build the GitHub API URL for the main Terraform file
        owner = os.environ.get("GITHUB_OWNER", "weka")
        repo = os.environ.get("GITHUB_REPO", "Chaos-Lab")
        main_path = f"scenario-tfs/{button_variable}/{button_variable}.tf"
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{main_path}"

        # Set up headers for GitHub API authentication
        github_token = os.environ.get("GITHUB_TOKEN")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        else:
            current_app.logger.error("GITHUB_TOKEN is not set.")
            return jsonify({'error': 'Server configuration error: missing GitHub token.'}), 500

        current_app.logger.debug(f"Fetching Terraform file from: {api_url}")
        tf_file_response = requests.get(api_url, headers=headers)
        if tf_file_response.status_code != 200:
            current_app.logger.error(f"Failed to fetch Terraform file: {tf_file_response.status_code}")
            return jsonify({'error': f"Failed to fetch Terraform file: {tf_file_response.status_code}"}), 404

        json_data = tf_file_response.json()
        if "content" not in json_data:
            current_app.logger.error("No 'content' key in GitHub API response")
            return jsonify({'error': "Invalid response from GitHub."}), 500

        try:
            tf_file_content = base64.b64decode(json_data["content"]).decode('utf-8')
        except Exception as e:
            current_app.logger.error(f"Error decoding main file content: {e}")
            return jsonify({'error': 'Failed to decode main file content.'}), 500

        # Rewrite the module source URL from SSH to HTTPS (with token)
        original_source = "git::ssh://git@github.com/weka/Chaos-Lab.git"
        if github_token:
            replacement = f"git::https://{github_token}@github.com/weka/Chaos-Lab.git"
        else:
            replacement = "git::https://github.com/weka/Chaos-Lab.git"
        tf_file_content = tf_file_content.replace(original_source, replacement)
        current_app.logger.debug("Rewritten Terraform module source URL.")

        # Create a unique directory for processing
        timestamp = str(time.time())
        hash_str = hashlib.sha256(timestamp.encode()).hexdigest()[:8]
        new_dir_name = f"{button_variable}_{hash_str}"
        os.makedirs(new_dir_name, exist_ok=True)
        current_app.logger.debug(f"Created directory: {new_dir_name}")

        # Write the main Terraform file to disk
        tf_file_path = os.path.join(new_dir_name, 'main.tf')
        with open(tf_file_path, 'w') as file:
            file.write(tf_file_content)
        current_app.logger.debug(f"Main Terraform file written to: {tf_file_path}")

        # --- New: If a region is provided, fetch the corresponding region file ---
        region_map = {
            "california": "california-us.auto.tfvars",
            "london": "london.auto.tfvars",
            "mumbai": "mumbai.auto.tfvars",
            "sydney": "sydney.auto.tfvars",
            "virginia": "virginia-us.auto.tfvars"
        }
        region_file = region_map.get(region)
        if not region_file:
            current_app.logger.error("Invalid region provided.")
            return jsonify({'error': 'Invalid region provided.'}), 400

        region_path = f"region-vars/{region_file}"
        region_api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{region_path}"
        current_app.logger.debug(f"Fetching region file from: {region_api_url}")

        region_response = requests.get(region_api_url, headers=headers)
        if region_response.status_code != 200:
            current_app.logger.error(f"Failed to fetch region file: {region_response.status_code}")
            return jsonify({'error': f"Failed to fetch region file: {region_response.status_code}"}), 404

        region_json = region_response.json()
        if "content" not in region_json:
            current_app.logger.error("No 'content' key in GitHub API response for region file")
            return jsonify({'error': "Invalid response from GitHub for region file."}), 500

        try:
            region_file_content = base64.b64decode(region_json["content"]).decode('utf-8')
        except Exception as e:
            current_app.logger.error(f"Error decoding region file content: {e}")
            return jsonify({'error': 'Failed to decode region file content.'}), 500

        region_file_path = os.path.join(new_dir_name, region_file)
        with open(region_file_path, 'w') as region_file_handle:
            region_file_handle.write(region_file_content)
        current_app.logger.info(f"Region file '{region_file}' written to: {region_file_path}")

        # Run Terraform commands (init and apply)
        subprocess.run(['terraform', 'init'], check=True, cwd=new_dir_name)
        subprocess.run(['terraform', 'apply', '--auto-approve'], check=True, cwd=new_dir_name)
        current_app.logger.info("Terraform operations completed successfully.")

        # Zip the directory contents
        zip_filename = f"{new_dir_name}.zip"
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(new_dir_name):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, new_dir_name)
                    zipf.write(file_path, arcname)
        current_app.logger.info(f"Zipped directory to: {zip_filename}")

        # Move the ZIP file to a directory accessible by Flask
        downloads_dir = os.path.join(current_app.root_path, 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)
        zip_file_path = os.path.join(downloads_dir, zip_filename)
        os.rename(zip_filename, zip_file_path)
        current_app.logger.info(f"Moved ZIP file to downloads directory: {zip_file_path}")

        # **Start the S3 upload script as a separate process**
        s3_key = f"scenarios/{zip_filename}"
        # Corrected path: current_app.root_path already points to "server/app"
        upload_script_path = os.path.join(current_app.root_path, 'api', 'upload_to_s3.py')
        if not os.access(upload_script_path, os.X_OK):
            os.chmod(upload_script_path, 0o755)
        command = [
            'python',  # Or 'python3' as needed
            upload_script_path,
            zip_file_path,
            s3_bucket_name,
            s3_key
        ]
        subprocess.Popen(command)
        current_app.logger.info(f"Started upload script: {' '.join(command)}")

        download_url = f"/api/downloads/{zip_filename}"
        return jsonify({
            'message': 'Scenario created!',
            'download_url': download_url
        })

    except subprocess.CalledProcessError as e:
        error_msg = f"Terraform command failed: {e.cmd}\nOutput: {e.output.decode('utf-8') if e.output else 'No output'}"
        current_app.logger.error(error_msg)
        return jsonify({'error': error_msg}), 500
    except Exception as e:
        error_msg = f"An unexpected error occurred: {str(e)}"
        current_app.logger.error(error_msg)
        return jsonify({'error': error_msg}), 500

@bp.route('/downloads/<path:filename>', methods=['GET'])
def download_file(filename):
    downloads_dir = os.path.join(current_app.root_path, 'downloads')
    return send_from_directory(directory=downloads_dir, path=filename, as_attachment=True)

