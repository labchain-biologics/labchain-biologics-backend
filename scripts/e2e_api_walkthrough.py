#!/usr/bin/env python3
"""
Parcours API de bout en bout (ordre chronologique métier).

Prérequis :
  - API démarrée (ex. ``uv run poe start-dev``)
  - Postgres + LocalStack up (``docker compose --env-file .env up -d``)
  - Migrations appliquées (``uv run poe migrate``)

Usage :
  uv run python scripts/e2e_api_walkthrough.py
  uv run python scripts/e2e_api_walkthrough.py --base-url http://127.0.0.1:8000
  uv run python scripts/e2e_api_walkthrough.py --email lead@example.com --password 'Secret123!'

Aucune dépendance hors stdlib.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

API_PREFIX = "/api/v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_WORKSPACE = "default"
DEFAULT_PIPELINE_ID = "rnaseq"


def _pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Lit une clé camelCase ou snake_case."""
    for key in keys:
        if key in data:
            return data[key]
    return default


def stub_fastq_md5(s3_key: str, size_bytes: int) -> str:
    """Reproduit le MD5 déterministe du endpoint /fastq/{id}/verify."""
    digest = hashlib.md5(usedforsecurity=False)
    digest.update(s3_key.encode("utf-8"))
    digest.update(b":")
    digest.update(str(size_bytes).encode("utf-8"))
    return digest.hexdigest()


class ApiClient:
    def __init__(self, base_url: str, workspace: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.workspace = workspace
        self.token: str | None = None
        self.timeout = timeout

    def _headers(self, *, auth: bool = True, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "X-LabChain-Workspace": self.workspace,
        }
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int | set[int],
        auth: bool = True,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        data: bytes | None = None,
        content_type: str | None = None,
        step: str,
        absolute_url: str | None = None,
    ) -> Any:
        expected = {expected_status} if isinstance(expected_status, int) else set(expected_status)
        url = absolute_url or f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        body = data
        headers = self._headers(auth=auth, content_type=content_type)
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        print(f"\n→ [{step}] {method} {path if absolute_url is None else absolute_url[:100]}")
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.getcode()
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read()
            if status not in expected:
                try:
                    detail = json.loads(raw.decode("utf-8"))
                    detail_txt = json.dumps(detail, indent=2, default=str)
                except Exception:
                    detail_txt = raw.decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"{step}: attendu HTTP {sorted(expected)}, reçu {status}\n{detail_txt}"
                ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{step}: connexion impossible — {exc}") from exc

        if status not in expected:
            raise RuntimeError(f"{step}: attendu HTTP {sorted(expected)}, reçu {status}")

        print(f"  ✓ HTTP {status}")
        if status == 204 or not raw:
            return None
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception:
            text = raw.decode("utf-8", errors="replace")
            print(text[:1200])
            return text

        preview = json.dumps(parsed, indent=2, default=str)
        if len(preview) > 1200:
            preview = preview[:1200] + "\n  … (tronqué)"
        print(preview)
        return parsed

    def stream_sse(self, path: str, *, step: str, max_seconds: float = 12.0) -> int:
        url = f"{self.base_url}{path}"
        headers = self._headers(auth=True)
        headers["Accept"] = "text/event-stream"
        print(f"\n→ [{step}] GET {path}")
        req = urllib.request.Request(url, headers=headers, method="GET")
        lines_seen = 0
        deadline = time.monotonic() + max_seconds
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            if resp.getcode() != 200:
                raise RuntimeError(f"{step}: HTTP {resp.getcode()}")
            while time.monotonic() < deadline:
                line = resp.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if text:
                    print(f"  {text}")
                    lines_seen += 1
                if "stream-complete" in text or lines_seen >= 20:
                    break
        print(f"  ✓ {lines_seen} ligne(s) SSE reçue(s)")
        return lines_seen


def run_walkthrough(args: argparse.Namespace) -> int:
    email = args.email or f"e2e.lead.{uuid.uuid4().hex[:8]}@example.com"
    password = args.password
    client = ApiClient(args.base_url, args.workspace)

    # 0. Santé
    client.request(
        "GET",
        "/health",
        expected_status=200,
        auth=False,
        step="0. Health",
    )

    # 1. Créer un user (lead — requis pour lancer une pipeline)
    register = client.request(
        "POST",
        f"{API_PREFIX}/auth/register",
        expected_status={201, 409},
        auth=False,
        params={
            "fullName": args.full_name,
            "role": "bioinformatics_lead",
        },
        json_body={"email": email, "password": password},
        step="1. Register (bioinformatics_lead)",
    )
    if isinstance(register, dict) and register.get("detail") == "Email already registered":
        print("  (compte déjà existant — on continue avec le login)")

    # 2. Se connecter
    token_payload = client.request(
        "POST",
        f"{API_PREFIX}/auth/login",
        expected_status=200,
        auth=False,
        json_body={"email": email, "password": password},
        step="2. Login",
    )
    access_token = _pick(token_payload, "accessToken", "access_token")
    if not access_token:
        raise RuntimeError("Login: accessToken manquant dans la réponse")
    client.token = str(access_token)

    # 3. Profil courant
    client.request(
        "GET",
        f"{API_PREFIX}/auth/me",
        expected_status=200,
        step="3. GET /auth/me",
    )

    # 4. Créer un sample
    sample_code = f"SMP-E2E-{uuid.uuid4().hex[:8].upper()}"
    sample = client.request(
        "POST",
        f"{API_PREFIX}/samples",
        expected_status=201,
        json_body={
            "sampleCode": sample_code,
            "patientId": "PAT-E2E-001",
            "projectCode": "PRJ-E2E",
            "modality": "transcriptomics",
            "tissueType": "blood",
            "collectionDate": "2026-08-12",
            "rinDin": 8.4,
            "concentrationNgUl": 125.5,
            "volumeUl": 50.0,
            "qcStatus": "pending",
            "qcNotes": "E2E walkthrough sample",
            "metadata": {"source": "e2e_api_walkthrough"},
        },
        step="4. Create sample",
    )
    sample_id = str(_pick(sample, "id"))

    # 5. Lister / récupérer le sample
    client.request(
        "GET",
        f"{API_PREFIX}/samples",
        expected_status=200,
        params={"limit": 10},
        step="5a. List samples",
    )
    client.request(
        "GET",
        f"{API_PREFIX}/samples/{sample_id}",
        expected_status=200,
        step="5b. Get sample",
    )

    # 6. Mettre à jour le QC (réception / validation labo)
    client.request(
        "PATCH",
        f"{API_PREFIX}/samples/{sample_id}",
        expected_status=200,
        json_body={
            "qcStatus": "pass",
            "qcNotes": "QC passed during E2E walkthrough",
        },
        step="6. Update sample QC → pass",
    )

    # 7. Enregistrer un FastQ + upload S3 (LocalStack) + verify
    size_bytes = 1024
    filename = f"{sample_code}_R1.fastq.gz"
    register_fq = client.request(
        "POST",
        f"{API_PREFIX}/fastq/register",
        expected_status=201,
        json_body={
            "filename": filename,
            "sizeBytes": size_bytes,
            "sampleId": sample_id,
            "readPair": "R1",
        },
        step="7a. Register FastQ",
    )
    fastq_id = str(_pick(register_fq, "id"))
    s3_key = str(_pick(register_fq, "s3Key", "s3_key"))
    upload_url = str(_pick(register_fq, "uploadUrl", "upload_url"))
    expected_md5 = stub_fastq_md5(s3_key, size_bytes)

    print(f"\n→ [7b. Upload FastQ to S3] PUT {upload_url[:80]}…")
    upload_body = b"\x1f\x8b" + b"\x00" * (size_bytes - 2)
    upload_req = urllib.request.Request(
        upload_url,
        data=upload_body,
        headers={"Content-Type": "application/gzip"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(upload_req, timeout=30.0) as upload_resp:
            print(f"  ✓ HTTP {upload_resp.getcode()}")
    except urllib.error.HTTPError as exc:
        print(f"  ⚠ Upload S3 HTTP {exc.code} (LocalStack peut être down — on continue quand même)")
    except urllib.error.URLError as exc:
        print(f"  ⚠ Upload S3 impossible ({exc}) — on continue quand même")

    verify = client.request(
        "POST",
        f"{API_PREFIX}/fastq/{fastq_id}/verify",
        expected_status=200,
        step="7c. Verify FastQ",
    )
    status = _pick(verify, "verificationStatus", "verification_status")
    print(f"  verificationStatus={status} (stub md5={expected_md5})")

    # 8. Catalogue pipelines
    pipelines = client.request(
        "GET",
        f"{API_PREFIX}/pipelines",
        expected_status=200,
        step="8a. List pipelines",
    )
    pipeline_id = args.pipeline_id
    if isinstance(pipelines, list) and pipelines:
        ids = {_pick(p, "id") for p in pipelines if isinstance(p, dict)}
        if pipeline_id not in ids:
            pipeline_id = str(_pick(pipelines[0], "id"))
            print(f"  pipeline demandée indisponible → fallback {pipeline_id}")

    client.request(
        "GET",
        f"{API_PREFIX}/pipelines/{pipeline_id}",
        expected_status=200,
        step="8b. Get pipeline",
    )

    # 9. Lancer la pipeline d'analyse (lead only)
    run = client.request(
        "POST",
        f"{API_PREFIX}/runs",
        expected_status=201,
        json_body={
            "pipelineId": pipeline_id,
            "pipelineVersion": "latest",
            "sampleIds": [sample_id],
            "runName": f"e2e-{sample_code.lower()}",
            "parameters": {},
        },
        step="9. Launch pipeline run",
    )
    run_id = str(_pick(run, "id"))

    # 10. Suivre le run
    client.request(
        "GET",
        f"{API_PREFIX}/runs",
        expected_status=200,
        step="10a. List runs",
    )
    client.request(
        "GET",
        f"{API_PREFIX}/runs/{run_id}",
        expected_status=200,
        step="10b. Get run",
    )

    # 11. Stream SSE des logs
    client.stream_sse(
        f"{API_PREFIX}/runs/{run_id}/logs/stream",
        step="11. Stream run logs",
        max_seconds=12.0,
    )

    # 12. Résultats
    results = client.request(
        "GET",
        f"{API_PREFIX}/results",
        expected_status=200,
        params={"runId": run_id},
        step="12a. List results (by runId)",
    )
    client.request(
        "GET",
        f"{API_PREFIX}/results/runs/{run_id}",
        expected_status=200,
        step="12b. List results for run",
    )

    first_output_id: str | None = None
    if isinstance(results, list) and results:
        first_output_id = str(_pick(results[0], "id"))
    elif isinstance(run, dict):
        outputs = _pick(run, "outputFiles", "output_files") or []
        if outputs:
            first_output_id = str(_pick(outputs[0], "id"))

    if first_output_id:
        client.request(
            "GET",
            f"{API_PREFIX}/results/{first_output_id}/download",
            expected_status=200,
            step="12c. Presigned download URL",
        )
    else:
        print("\n  ⚠ Aucun fichier de résultat — skip download")

    # 13. Logout
    client.request(
        "POST",
        f"{API_PREFIX}/auth/logout",
        expected_status=200,
        step="13. Logout",
    )

    print("\n" + "=" * 60)
    print("Parcours E2E terminé avec succès.")
    print(f"  email     = {email}")
    print(f"  sampleId  = {sample_id}")
    print(f"  fastqId   = {fastq_id}")
    print(f"  runId     = {run_id}")
    print(f"  pipeline  = {pipeline_id}")
    print("=" * 60)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Walkthrough chronologique de l'API LabChain Biologics",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"URL de base de l'API (défaut: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--workspace",
        default=DEFAULT_WORKSPACE,
        help=f"Valeur de X-LabChain-Workspace (défaut: {DEFAULT_WORKSPACE})",
    )
    parser.add_argument(
        "--email",
        default=None,
        help="Email du compte (défaut: email aléatoire unique)",
    )
    parser.add_argument(
        "--password",
        default="E2eSecret123!",
        help="Mot de passe (≥ 8 caractères)",
    )
    parser.add_argument(
        "--full-name",
        default="E2E Bioinformatics Lead",
        help="Nom affiché à l'inscription",
    )
    parser.add_argument(
        "--pipeline-id",
        default=DEFAULT_PIPELINE_ID,
        help=f"Pipeline nf-core à lancer (défaut: {DEFAULT_PIPELINE_ID})",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        raise SystemExit(run_walkthrough(args))
    except Exception as exc:
        print(f"\nÉchec du parcours E2E: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
