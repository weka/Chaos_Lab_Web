import os
import time
import hashlib
import subprocess
import zipfile
import requests
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from app.api import bp

@bp.route('/scenarios', methods=['POST'])
def create_scenario():
    """Handle POST requests to create a scenario and make it available for download."""
    try:
        # Extract and validate request data
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        button_variable = data.get('repo')
        if not button_variable:
            return jsonify({'error': 'Missing required parameter: repo'}), 400

        s3_bucket_name = 'cst-chaos-lab'  # Replace with your actual S3 bucket name
        current_app.logger.info(f"Processing request for repo: {button_variable}")

        # Fetch Terraform file from GitHub
        tf_file_url = f'https://raw.githubusercontent.com/NanoBlazer915/CST-Scenario-Lab/main/scenario-tfs/{button_variable}/{button_variable}.tf'
        tf_file_response = requests.get(tf_file_url)
        if tf_file_response.status_code != 200:
            current_app.logger.error(f"Failed to fetch Terraform file: {tf_file_response.status_code}")
            return jsonify({'error': f"Failed to fetch Terraform file: {tf_file_response.status_code}"}), 404
        tf_file_content = tf_file_response.text

        # Create unique directory for processing
        timestamp = str(time.time())
        hash_str = hashlib.sha256(timestamp.encode()).hexdigest()[:8]
        new_dir_name = f"{button_variable}_{hash_str}"
        os.makedirs(new_dir_name, exist_ok=True)
        current_app.logger.debug(f"Created directory: {new_dir_name}")

        # Write Terraform file
        tf_file_path = os.path.join(new_dir_name, 'main.tf')
        with open(tf_file_path, 'w') as file:
            file.write(tf_file_content)
        current_app.logger.debug(f"Terraform file written to: {tf_file_path}")

        # Run Terraform commands
        subprocess.run(['terraform', 'init'], check=True, cwd=new_dir_name)
        subprocess.run(['terraform', 'apply', '--auto-approve'], check=True, cwd=new_dir_name)
        current_app.logger.info("Terraform operations completed successfully.")

        # Zip directory contents
        zip_filename = f"{new_dir_name}.zip"
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(new_dir_name):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, new_dir_name)
                    zipf.write(file_path, arcname)
        current_app.logger.info(f"Zipped directory to: {zip_filename}")

        # Move ZIP file to a directory accessible by Flask
        downloads_dir = os.path.join(current_app.root_path, 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)
        zip_file_path = os.path.join(downloads_dir, zip_filename)
        os.rename(zip_filename, zip_file_path)
        current_app.logger.info(f"Moved ZIP file to downloads directory: {zip_file_path}")

        # **Start the S3 upload script as a separate process**
        s3_key = f"scenarios/{zip_filename}"
        upload_script_path = os.path.join(current_app.root_path, '/server/app/api/upload_to_s3.py')

        # Ensure the upload script is executable
        if not os.access(upload_script_path, os.X_OK):
            os.chmod(upload_script_path, 0o755)

        # Build the command to run the upload script
        command = [
            'python',  # Or use 'python3' depending on your environment
            upload_script_path,
            zip_file_path,
            s3_bucket_name,
            s3_key
        ]

        # Start the upload script as a separate process
        subprocess.Popen(command)
        current_app.logger.info(f"Started upload script: {' '.join(command)}")

        # Return a URL to download the ZIP file
        download_url = f"/api/downloads/{zip_filename}"

        # Return the response to the client immediately
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

# Route to serve the ZIP files
@bp.route('/downloads/<path:filename>', methods=['GET'])
def download_file(filename):
    downloads_dir = os.path.join(current_app.root_path, 'downloads')
    return send_from_directory(directory=downloads_dir, path=filename, as_attachment=True)