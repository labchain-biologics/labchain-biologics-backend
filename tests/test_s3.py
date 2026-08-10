"""Unit tests for S3Service (boto3 client mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.services.s3 import S3Service


@pytest.fixture
def s3_service(mock_s3_client: MagicMock) -> S3Service:
    return S3Service(client=mock_s3_client)


def test_build_object_key_strips_leading_slashes(s3_service: S3Service) -> None:
    key = s3_service.build_object_key("ws-a", "/fastq", "/run1/sample.fastq.gz")
    assert key == "ws-a/fastq/run1/sample.fastq.gz"


def test_generate_presigned_upload_url(s3_service: S3Service, mock_s3_client: MagicMock) -> None:
    url = s3_service.generate_presigned_upload_url(
        "ws/fastq/file.fastq.gz",
        content_type="application/gzip",
        expires_in=120,
    )
    assert url == "https://s3.example/presigned"
    mock_s3_client.generate_presigned_url.assert_called_once_with(
        ClientMethod="put_object",
        Params={
            "Bucket": s3_service._bucket,
            "Key": "ws/fastq/file.fastq.gz",
            "ContentType": "application/gzip",
        },
        ExpiresIn=120,
    )


def test_generate_presigned_download_url_with_filename(
    s3_service: S3Service, mock_s3_client: MagicMock
) -> None:
    s3_service.generate_presigned_download_url("ws/out/report.html", filename="report.html")
    params = mock_s3_client.generate_presigned_url.call_args.kwargs["Params"]
    assert params["ResponseContentDisposition"] == 'attachment; filename="report.html"'
    assert mock_s3_client.generate_presigned_url.call_args.kwargs["ClientMethod"] == "get_object"


def test_object_exists_true(s3_service: S3Service, mock_s3_client: MagicMock) -> None:
    assert s3_service.object_exists("ws/key") is True
    mock_s3_client.head_object.assert_called_once()


def test_object_exists_false_on_error(s3_service: S3Service, mock_s3_client: MagicMock) -> None:
    mock_s3_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}},
        "HeadObject",
    )
    assert s3_service.object_exists("missing") is False


def test_ensure_bucket_creates_when_missing(
    s3_service: S3Service, mock_s3_client: MagicMock
) -> None:
    mock_s3_client.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "NoSuchBucket", "Message": "No such bucket"}},
        "HeadBucket",
    )
    s3_service.ensure_bucket()
    mock_s3_client.create_bucket.assert_called_once()


def test_ensure_bucket_raises_on_unexpected_client_error(
    s3_service: S3Service, mock_s3_client: MagicMock
) -> None:
    mock_s3_client.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}},
        "HeadBucket",
    )
    with pytest.raises(ClientError):
        s3_service.ensure_bucket()
