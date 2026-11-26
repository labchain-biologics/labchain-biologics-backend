# ADR 0001: Edition boundary for subscriber-only server features

| | |
| --- | --- |
| Status | **Proposed**: to be accepted before the first subscriber-only server feature |
| Date | 2026-11-26 |
| Scope | Server (this repository), Python SDK, any API client |

## Context

Titerlane Biologics is open core. This server is AGPL-3.0-only and must stay fully usable on
its own. Some future server features will be for subscribers only (examples often cited:
SAML/OIDC single sign-on, signed audit trail exports, advanced retention policies).

Constraints:

1. **No hidden code.** Nothing in this repository may be dormant paid functionality
   unlocked by a key. Under the AGPL anyone can remove such a check, and hiding it would
   mislead users about what the open-source server does.
2. **One public API.** Clients (the proprietary web frontend, the SDK, scripts) use only
   documented API routes. No private or undocumented endpoint for a particular client.
3. **Regulated data stays reachable (21 CFR Part 11).** An expired or missing subscription
   must never block access to records, results or the audit trail, nor corrupt it.
4. **The core does not know about paid features.** It cannot list them, price them or
   check for them by name.

## Decision

Subscriber-only server features ship in a **separate, proprietary Python package**
(working name `titerlane-enterprise`), installed next to the open-source server. The
open-source server defines **generic extension points**, documented and tested here, and
loads extensions through a Python entry point. The enterprise package, not the core,
checks the subscription licence.

```text
┌──────────────────────── open source (this repo, AGPL) ────────────────────────┐
│  app.extensions: Extension protocol, registry, entry-point loader             │
│  extension points: routers · login providers · audit exporters · ...          │
│  GET /api/v1/edition  →  {"edition": "community" | name, "features": [...]}   │
└───────────────────────────────────────────────▲───────────────────────────────┘
                                                │ entry point "titerlane.extensions"
┌───────────────────── proprietary (separate package and repository) ────────────┐
│  licence verification (signed licence file, offline)                          │
│  features: SSO login provider, audit export, ...                              │
└───────────────────────────────────────────────────────────────────────────────┘
```

### In this repository (open source)

- `app/extensions/`: an `Extension` protocol (name, version, the features it provides, a
  `setup(registry)` hook) and a registry. At startup the server loads every installed
  `titerlane.extensions` entry point, logs each one (name, version, features), and refuses
  to start if one fails to load: no silent partial edition.
- **Extension points**, each added when the first feature needs it, never speculatively,
  and each with a community implementation or a documented "none" behaviour:
  - extra API routers, mounted under `/api/v1` and included in the OpenAPI document of
    that deployment;
  - login providers, next to password, personal access tokens and Google;
  - audit trail exporters (read-only consumers of `audit_logs`);
  - and so on, as features require.
- `GET /api/v1/edition` (public, documented): edition name and the list of feature
  identifiers the loaded extensions declare. Clients show or hide features from it.
  Without extensions: `{"edition": "community", "features": []}`.
- Extensions go through the same rules as core code: tenant routes use `deps.Workspace` /
  `deps.Membership`, authorization uses `deps.py`, mutations call `audit_service.record`.
  These helpers are the supported extension API; anything else under `app.` is internal.

### In the enterprise package (proprietary)

- **Licence**: a licence file signed by Titerlane (Ed25519), verified offline with a public
  key embedded in the package. Claims: licensee, deployment identifier, features, expiry. No
  call home, so air-gapped labs work.
- The package registers a feature only when the licence covers it. Its routes therefore
  do not exist on unlicensed deployments (`404`, like any unknown route), rather than
  existing and answering `402`/`403`.
- **Expiry**: a grace period, then the paid features stop being registered at the next
  restart. Data created through them stays in core tables and stays readable through the
  core API. A login provider that disappears leaves password and token login working, so
  administrators can always get in.
- Installing, replacing or losing a licence is written to the audit trail (`licence`
  entity), with the licence identifier but never the file contents.

### Clients

- The web frontend reads `GET /api/v1/edition` and uses the routes of the features
  listed there. It never infers an edition from its own subscription state.
- The SDK models `/edition`. Enterprise routes are documented with the enterprise package;
  the SDK supports them only as far as the published contract of that edition goes.

## Consequences

- The open-source server never contains, references or enumerates paid features. A
  self-hosted community deployment is complete for everything it documents.
- Extension points are public API and need the same care: semantic versioning, tests, docs.
  The enterprise package declares the core version range it supports.
- Two repositories and two release trains. Contract tests run the enterprise package
  against the matching core release in its own CI.
- A subscriber-only feature that needs a new table ships its own Alembic branch in the
  enterprise package, never a migration in this repository that only it uses.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Licence-key feature flags in this repository | Paid code would sit in the AGPL repository, removable by anyone, and look like hidden functionality (constraint 1). |
| `ee/` directory under a separate licence in this repository (GitLab model) | Mixed licences in one repository: confusing for contributors and downstream packagers, and makes the AGPL scope harder to state. Could be reconsidered if contributions to paid features matter. |
| Proprietary features as a separate service behind the frontend | Splits the API, and the frontend would depend on a second backend that the SDK and scripts cannot use (constraint 2). |
| Frontend-only paid features | Fine for purely presentational features; useless for anything the server must enforce (SSO, exports, retention). Both models can coexist. |

## Open questions

1. **Legal.** The enterprise package is distributed together with the AGPL server.
   Distributing it under proprietary terms relies on holding all rights to the server
   (dual licensing), so it depends on the copyright and CLA work (Next steps, item 2). To
   confirm with counsel before the first paid release.
2. **Licence granularity**: per deployment, per workspace, per seat? This drives the claims
   of the licence file and whether features are checked per workspace.
3. **Hosted offering**: the same mechanism with a licence per hosted deployment, or a
   separate entitlement source? Proposed: the same, so both paths stay tested.
4. **First feature**: which one opens the extension mechanism (SSO is the usual
   candidate) decides which extension point is built first.
