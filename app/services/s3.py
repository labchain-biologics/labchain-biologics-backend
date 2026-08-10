"""Boto3 S3 helper for presigned upload/download URLs."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from app.core.config import settings


@lru_cache
def get_s3_client() -> S3Client:
    client_kwargs: dict[str, Any] = {
        "service_name": "s3",
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
        "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    }
    if settings.s3_endpoint_url:
        client_kwargs["endpoint_url"] = settings.s3_endpoint_url
    return cast(S3Client, boto3.client(**client_kwargs))


class S3Service:
    def __init__(self, client: S3Client | None = None) -> None:
        self._client = client or get_s3_client()
        self._bucket = settings.s3_bucket
        self._expire = settings.s3_presign_expire_seconds

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code not in {"404", "NotFound", "NoSuchBucket"}:
                raise
            create_kwargs: dict[str, Any] = {"Bucket": self._bucket}
            if settings.aws_region != "us-east-1" and not settings.s3_endpoint_url:
                create_kwargs["CreateBucketConfiguration"] = {
                    "LocationConstraint": settings.aws_region
                }
            self._client.create_bucket(**create_kwargs)

    def build_object_key(self, workspace: str, prefix: str, filename: str) -> str:
        safe_name = filename.lstrip("/")
        return f"{workspace.strip('/')}/{prefix.strip('/')}/{safe_name}"

    def generate_presigned_upload_url(
        self,
        key: str,
        *,
        content_type: str = "application/octet-stream",
        expires_in: int | None = None,
    ) -> str:
        return self._client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in or self._expire,
        )

    def generate_presigned_download_url(
        self,
        key: str,
        *,
        filename: str | None = None,
        expires_in: int | None = None,
    ) -> str:
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return self._client.generate_presigned_url(
            ClientMethod="get_object",
            Params=params,
            ExpiresIn=expires_in or self._expire,
        )

    def object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise


s3_service = S3Service()
