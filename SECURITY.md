# Security policy

LabChain Biologics handles regulated laboratory data (21 CFR Part 11 audit trail, sample and
patient identifiers). We take vulnerability reports seriously and ask you to disclose them
privately.

## Reporting a vulnerability

**Do not open a public issue, discussion or pull request for a security problem.**

Report it privately through GitHub: open the repository's
[**Security** tab](https://github.com/labchain-biologics/labchain-biologics-backend/security)
and choose **Report a vulnerability**. Only the maintainers can see the report.

Please include:

- the affected component (API server, Python SDK, CLI) and version or commit;
- what an attacker can do, and the conditions (role, workspace membership, configuration);
- steps to reproduce, or a proof of concept that uses no real data;
- any suggested fix.

Never include real patient, sample or customer data in a report.

## What to expect

- Acknowledgement within 5 working days.
- An assessment and a plan (fix, mitigation or explanation) within 15 working days.
- A coordinated disclosure: we publish a GitHub security advisory once a fix is available,
  crediting you unless you prefer otherwise.

The project is maintained by a small team; these are targets, not contractual commitments.

## Supported versions

The project is in alpha (0.x). Security fixes are made on `main` and in the latest release of
the Python SDK only.

| Component | Supported |
| --- | --- |
| API server, `main` branch | yes |
| `labchain-biologics-sdk`, latest release | yes |
| Older SDK releases | no |

## Scope

In scope: this repository, i.e. the API server, its database migrations, the Python SDK and
the `labchain` CLI. Of particular interest: authentication and personal access tokens,
workspace isolation (cross-tenant access), role checks, the append-only audit trail, signed
storage URLs, and pipeline launch (command or parameter injection).

Out of scope: deployments run by third parties, findings that need a compromised
administrator account or host, denial of service by volume, and missing hardening headers
without a demonstrated impact.

Please test only against your own local deployment (see
[Getting started](docs/getting-started.md)), never against someone else's server.
