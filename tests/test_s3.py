"""Unit tests for S3Service (boto3 client mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.services.s3 import S3Service


@pytest.fixture
def s3_service(mock_s3_client: MagicMock) -> S3Service:
    return S3Service(client=mock_s3_client)


def test_build_object_key_strips_leading_slashes(s3_service: S3Service) -> None:
    key = s3_service.build_object_key("ws-a", "/fastq", "/run1/sample.fastq.gz")
    assert key == "ws-a/fastq/run1/sample.fastq.gz"


def test_presign_upload(s3_service: S3Service, mock_s3_client: MagicMock) -> None:
    upload = s3_service.presign_upload(
        "ws/fastq/file.fastq.gz",
        content_type="application/gzip",
        expires_in=120,
    )
    assert upload.url == "https://s3.example/presigned"
    assert upload.headers == {"Content-Type": "application/gzip"}
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


def test_object_exists_raises_on_boto_core_error(
    s3_service: S3Service, mock_s3_client: MagicMock
) -> None:
    mock_s3_client.head_object.side_effect = EndpointConnectionError(endpoint_url="http://s3.local")
    with pytest.raises(EndpointConnectionError):
        s3_service.object_exists("missing")


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


def test_ensure_bucket_raises_on_boto_core_error(
    s3_service: S3Service, mock_s3_client: MagicMock
) -> None:
    mock_s3_client.head_bucket.side_effect = EndpointConnectionError(endpoint_url="http://s3.local")
    with pytest.raises(EndpointConnectionError):
        s3_service.ensure_bucket()


def test_apply_cors_allows_given_origins(mock_s3_client: MagicMock) -> None:
    service = S3Service(client=mock_s3_client)
    service.apply_cors(["http://localhost:8080"])
    config = mock_s3_client.put_bucket_cors.call_args.kwargs["CORSConfiguration"]
    rule = config["CORSRules"][0]
    assert rule["AllowedOrigins"] == ["http://localhost:8080"]
    assert "PUT" in rule["AllowedMethods"]


def test_object_checksum_uses_single_part_etag(mock_s3_client: MagicMock) -> None:
    mock_s3_client.head_object.return_value = {
        "ContentLength": 4,
        "ETag": '"098F6BCD4621D373CADE4E832627B4F6"',
    }
    checksum = S3Service(client=mock_s3_client).object_checksum("k")
    assert checksum is not None
    assert checksum.md5 == "098f6bcd4621d373cade4e832627b4f6"
    assert checksum.size_bytes == 4
    mock_s3_client.get_object.assert_not_called()


def test_object_checksum_hashes_multipart_objects(mock_s3_client: MagicMock) -> None:
    mock_s3_client.head_object.return_value = {"ContentLength": 4, "ETag": '"abc-2"'}
    body = MagicMock()
    body.iter_chunks.return_value = [b"te", b"st"]
    mock_s3_client.get_object.return_value = {"Body": body}
    checksum = S3Service(client=mock_s3_client).object_checksum("k")
    assert checksum is not None
    assert checksum.md5 == "098f6bcd4621d373cade4e832627b4f6"  # md5("test")


def test_object_checksum_missing_object(mock_s3_client: MagicMock) -> None:
    mock_s3_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )
    assert S3Service(client=mock_s3_client).object_checksum("k") is None


def test_object_checksum_hashes_kms_encrypted_objects(mock_s3_client: MagicMock) -> None:
    # SSE-KMS ETags are not content MD5s, even for single-part uploads.
    mock_s3_client.head_object.return_value = {
        "ContentLength": 4,
        "ETag": '"0123456789abcdef0123456789abcdef"',
        "ServerSideEncryption": "aws:kms",
    }
    body = MagicMock()
    body.iter_chunks.return_value = [b"test"]
    mock_s3_client.get_object.return_value = {"Body": body}
    checksum = S3Service(client=mock_s3_client).object_checksum("k")
    assert checksum is not None
    assert checksum.md5 == "098f6bcd4621d373cade4e832627b4f6"
    assert checksum.etag == "0123456789abcdef0123456789abcdef"
    # The streamed object is pinned to the version whose headers were read.
    assert mock_s3_client.get_object.call_args.kwargs["IfMatch"] == (
        '"0123456789abcdef0123456789abcdef"'
    )


def test_client_is_created_once_across_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    import time

    from app.services import s3

    created: list[object] = []

    def slow_client(**_: object) -> object:
        time.sleep(0.05)  # widen the race window
        client = object()
        created.append(client)
        return client

    s3.get_s3_client.cache_clear()
    monkeypatch.setattr(s3.boto3, "client", slow_client)
    service = S3Service()
    seen: list[object] = []
    threads = [threading.Thread(target=lambda: seen.append(service._client)) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    s3.get_s3_client.cache_clear()

    assert len(created) == 1
    assert all(client is created[0] for client in seen)
