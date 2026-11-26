# Contributing

Thank you for your interest in LabChain Biologics.

## Code contributions are not open yet

We cannot accept pull requests from outside the core team yet. The project is dual-licensed
in practice (AGPL-3.0-only for the server, Apache-2.0 for the Python SDK, and commercial
licences in the future), which requires a Contributor License Agreement (CLA) that is
still being prepared. Pull requests opened before it exists will be closed without review,
so that no code enters the project without clear rights.

This page will explain how to sign the CLA once it is available.

## What you can do today

- **Report a bug** or **propose a feature** with the
  [issue templates](https://github.com/labchain-biologics/labchain-biologics-backend/issues/new/choose).
- **Report a security problem privately**: see [SECURITY.md](SECURITY.md). Never in a
  public issue.
- **Improve the documentation** by reporting what is unclear or missing in an issue.

Please never post real patient, sample or customer data, credentials, tokens or signed
storage URLs in an issue, even partially.

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).

## For the core team

The development workflow is described in [docs/development.md](docs/development.md) and in
`CLAUDE.md`:

- work on a branch and open a pull request; `main` is protected and requires the `CI gate`
  check;
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`),
  small and focused;
- code, comments, commit messages and docs in English;
- run `uv run poe check` and `uv run poe test` (plus `uv run poe sdk-test` for `sdk/`)
  before asking for review;
- every mutation of regulated data is audited in the same transaction; `audit_logs` is
  append-only.

## Licences

By contributing (once the CLA is in place), you agree that your contribution is licensed
under the licence of the part of the repository it touches: AGPL-3.0-only for the server,
Apache-2.0 for `sdk/`. See the [README](README.md#license).
