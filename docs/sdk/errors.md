# Errors

Every exception raised by the SDK derives from `labchain.LabChainError`, so one `except`
clause can catch them all.

```text
LabChainError
├── ConfigurationError        missing base URL or workspace, checked before any request
├── APIConnectionError        network failure, or object storage refused a transfer
├── APIError                  the API answered with an error status
│   ├── BadRequestError       400
│   ├── AuthenticationError   401: missing, invalid, expired or revoked credentials
│   ├── PermissionDeniedError 403: your role in this workspace does not allow the action
│   ├── NotFoundError         404: unknown resource, or a workspace you do not belong to
│   ├── ConflictError         409: duplicate, or already in that state
│   ├── UnprocessableError    422: invalid content
│   └── ServerError           5xx
├── ChecksumMismatchError     a transferred file does not match its MD5
├── ExecutionDisabledError    runs.wait: the server does not execute pipelines
├── RunFailedError            runs.wait: the run failed or was cancelled
└── RunTimeoutError           runs.wait: timeout elapsed (also a TimeoutError)
```

## API errors

`APIError` carries what the server said:

| Attribute | Description |
| --- | --- |
| `status_code` | HTTP status |
| `detail` | The server's `detail` field (a string, or the list of validation errors for 422) |
| `method`, `path` | The request, without query string or host |

```python
from labchain import NotFoundError, PermissionDeniedError

try:
    client.runs.launch("rnaseq", sample_ids=[sample_id])
except PermissionDeniedError:
    print("launching runs needs the bioinformatics_lead role")
except NotFoundError as exc:
    print("not found:", exc.detail)
```

Server-side validation errors (422) are rendered on one line in the message, as
`location: message` pairs separated by `;`.

!!! note "Local validation comes first"
    Request models check types, enums, lengths and unknown fields before sending. A bad
    argument such as `samples.create(sample_code="", modality="genomics")` raises
    `pydantic.ValidationError` locally, not a `LabChainError`, and no request is sent.

!!! note "404 hides other workspaces"
    A sample, run or file from a workspace you are not a member of answers `NotFoundError`,
    exactly like an ID that does not exist. The SDK cannot tell the two apart, by design.

## Run errors

| Exception | Attributes | Meaning |
| --- | --- | --- |
| `ExecutionDisabledError` | | The run was recorded with `execution_submitted=False`; it would stay `pending` forever |
| `RunFailedError` | `run_id`, `status`, message from `progress.errorMessage` | Status `failed` or `cancelled` |
| `RunTimeoutError` | | `timeout` elapsed; the run keeps going on the server |

## Retries

GET requests are retried twice (`max_retries=2`) on `502`, `503`, `504` and network errors,
with exponential backoff (0.5 s, 1 s, ... capped at 4 s). Other methods are never retried, so
a create or launch is never sent twice. Set `Client(max_retries=0)` to disable retries.

## What errors never contain

Error messages and `repr()` never include the API token or signed storage URLs. A refused
storage transfer reports the HTTP status and the storage error code (e.g. `AccessDenied`,
`SignatureDoesNotMatch`) only.
