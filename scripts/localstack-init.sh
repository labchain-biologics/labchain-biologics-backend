#!/usr/bin/env bash
set -euo pipefail

awslocal s3 mb "s3://labchain-biologics" || true
awslocal s3api put-bucket-cors --bucket labchain-biologics --cors-configuration '{
  "CORSRules": [
    {
      "AllowedOrigins": ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8080", "http://127.0.0.1:8080"],
      "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag", "x-amz-request-id"],
      "MaxAgeSeconds": 3000
    }
  ]
}'

# The API also applies CORS_ORIGINS to this bucket at startup (local development only).
echo "LocalStack S3 bucket labchain-biologics ready"
