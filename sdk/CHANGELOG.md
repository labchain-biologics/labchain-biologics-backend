# Changelog

All notable changes to `titerlane-biologics-sdk`. The SDK follows
[Semantic Versioning](https://semver.org/); while it is 0.x, a minor version may change the
interface. Releases are tagged `sdk-vX.Y.Z`.

## 0.2.0 (unreleased)

### Added

- `AsyncClient`: the same resources and methods as `Client`, awaited, on `httpx.AsyncClient`;
  listings and log streams are async iterators. Disk work runs in worker threads.
- `titerlane` command line, in the `cli` extra (`pip install "titerlane-biologics-sdk[cli]"`):
  tokens, workspaces, members, samples, FASTQ upload, pipelines, runs and results.

### Changed

- FASTQ uploads send the headers the server signed (`FastqRegistration.upload_headers`, the
  API's `uploadHeaders`) instead of assuming `Content-Type: application/gzip`. This needs a
  server that returns `uploadHeaders`.
- Workspace-scoped calls without a workspace now say "pass workspace= to the client" (was
  "to Client"), as the message also applies to `AsyncClient`.

## 0.1.0

First version (not published to PyPI): synchronous `Client` with personal access tokens,
samples, sequencing runs, FASTQ upload and verification, pipeline runs, log streaming, MD5-checked
result downloads, typed errors and retries.
