<!-- markdownlint-disable-file MD041 -->
## Summary

<!-- What changes and why. Link the issue if there is one. -->

## Checklist

- [ ] Conventional Commit title (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`)
- [ ] `uv run poe check` and `uv run poe test` pass (`uv run poe sdk-test` for `sdk/`)
- [ ] API change: `openapi.json` regenerated (`uv run poe openapi`), `docs/api/` and `sdk/` updated
- [ ] Mutation of regulated data: audited in the same transaction, covered by a test
- [ ] Tenant routes: other workspace (404) and wrong role (403) tested
- [ ] No secrets, real data, customer names or production infrastructure references
