#!/usr/bin/env bash
set -euo pipefail

awslocal s3 mb "s3://vesselchain-biologics" || true
awslocal s3api put-bucket-cors --bucket vesselchain-biologics --cors-configuration '{
  "CORSRules": [
    {
      "AllowedOrigins": ["http://localhost:5173", "http://127.0.0.1:5173"],
      "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag", "x-amz-request-id"],
      "MaxAgeSeconds": 3000
    }
  ]
}'

echo "LocalStack S3 bucket vesselchain-biologics ready"
