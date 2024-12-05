#!/usr/bin/env python3

import sys
import boto3
import logging
from botocore.exceptions import NoCredentialsError, ClientError

def upload_to_s3(zip_file_path, s3_bucket_name, s3_key):
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        s3_client = boto3.client('s3')
        s3_client.upload_file(zip_file_path, s3_bucket_name, s3_key)
        logger.info(f"Uploaded '{zip_file_path}' to S3 bucket '{s3_bucket_name}' with key '{s3_key}'")
    except (NoCredentialsError, ClientError) as e:
        logger.error(f"AWS error during S3 upload: {str(e)}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during S3 upload: {str(e)}")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python upload_to_s3.py <zip_file_path> <s3_bucket_name> <s3_key>")
        sys.exit(1)

    zip_file_path = sys.argv[1]
    s3_bucket_name = sys.argv[2]
    s3_key = sys.argv[3]
    upload_to_s3(zip_file_path, s3_bucket_name, s3_key)