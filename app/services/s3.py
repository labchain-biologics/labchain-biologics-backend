"""Boto3 S3 helper for presigned upload/download URLs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings

if TYPE_CHECKING:
    # Type stubs are a dev-only dependency: never import them at runtime.
    from mypy_boto3_s3 import S3Client


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
    return cast("S3Client", boto3.client(**client_kwargs))


_MD5_CHUNK_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ObjectChecksum:
    md5: str
    size_bytes: int
    etag: str


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

    def apply_cors(self, origins: list[str]) -> None:
        """Allow browsers on ``origins`` to PUT/GET objects through presigned URLs."""
        self._client.put_bucket_cors(
            Bucket=self._bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": origins,
                        "AllowedMethods": ["GET", "PUT", "HEAD"],
                        "AllowedHeaders": ["*"],
                        "ExposeHeaders": ["ETag", "x-amz-request-id"],
                        "MaxAgeSeconds": 3000,
                    }
                ]
            },
        )

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

    def uri(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    def key_from_uri(self, uri: str) -> str:
        prefix = f"s3://{self._bucket}/"
        if not uri.startswith(prefix):
            raise ValueError(f"{uri} is not in bucket {self._bucket}")
        return uri[len(prefix) :]

    def put_text(self, key: str, body: str, *, content_type: str = "text/plain") -> str:
        """Store a small text object and return its ``s3://`` URI."""
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=body.encode("utf-8"), ContentType=content_type
        )
        return self.uri(key)

    def list_objects(self, prefix: str) -> list[StoredObject]:
        """Every object under ``prefix``, following all listing pages."""
        found: list[StoredObject] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                found.append(StoredObject(key=item["Key"], size_bytes=int(item.get("Size", 0))))
        return found

    def object_checksum(self, key: str) -> ObjectChecksum | None:
        """
        MD5 and size of a stored object, or ``None`` if it does not exist.

        The ETag of a single-part upload stored unencrypted or with SSE-S3 is the MD5 of its
        content, so it is used directly. Otherwise (multipart ``<hash>-<parts>`` ETag,
        SSE-KMS or SSE-C) the object is streamed and hashed, pinned to the ETag read first so
        a concurrent overwrite cannot be hashed by mistake. ``etag`` identifies the exact
        object version that was checked.
        """
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        size = int(head.get("ContentLength", 0))
        raw_etag = str(head.get("ETag", ""))
        etag = raw_etag.strip('"')
        encryption = head.get("ServerSideEncryption")
        plain_etag = encryption in (None, "AES256") and not head.get("SSECustomerAlgorithm")
        if plain_etag and "-" not in etag and len(etag) == 32:
            return ObjectChecksum(md5=etag.lower(), size_bytes=size, etag=etag)

        digest = hashlib.md5(usedforsecurity=False)
        body = self._client.get_object(Bucket=self._bucket, Key=key, IfMatch=raw_etag)["Body"]
        for chunk in body.iter_chunks(chunk_size=_MD5_CHUNK_BYTES):
            digest.update(chunk)
        return ObjectChecksum(md5=digest.hexdigest(), size_bytes=size, etag=etag)

    def current_etag(self, key: str) -> str | None:
        """ETag of the object now stored at ``key``, or ``None`` if it does not exist."""
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return str(head.get("ETag", "")).strip('"')


s3_service = S3Service()
