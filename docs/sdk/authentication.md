# Authentication

Every SDK call acts as a user, with that user's role in the selected workspace. The server
enforces permissions: the SDK never decides what you may do.

## Personal access tokens (recommended)

Scripts, notebooks and CI jobs should use a personal access token (PAT). It lasts up to the
server's maximum lifetime (365 days by default) instead of the one-hour login session. See
[/auth/tokens](../api/auth/tokens.md) for the security model.

Creating a token requires a **password login**: a token cannot create another token.

```python
from titerlane import Client

with Client.login("you@lab.example", "your-password", base_url="http://localhost:8000") as c:
    created = c.auth.tokens.create("nightly QC job", expires_in_days=90)
    print(created.token)  # the secret is returned only once
```

Store `created.token` in a secret manager or CI secret, then expose it as `TITERLANE_TOKEN`.
The server keeps only a digest and cannot show the secret again.

Manage your tokens with any credential, including a token:

```python
for token in client.auth.tokens.list():  # newest first, including revoked and expired
    print(token.name, token.token_prefix, token.expires_at, token.revoked_at)

client.auth.tokens.revoke(token_id)  # stops working immediately
```

!!! warning "Treat a token like a password"
    It acts as you in every workspace you belong to. Revoke it as soon as it may have
    leaked, and prefer one token per job so you can revoke one without stopping the others.

## Password login

`Client.login` signs in with email and password and returns a ready client. The session
expires after the server's JWT lifetime (one hour by default), so use it for interactive
work or to create a token, not for long jobs.

```python
client = Client.login("you@lab.example", "your-password", base_url="http://localhost:8000",
                      workspace="demo-lab")
```

`client.auth.logout()` records the logout in the audit trail. It does not invalidate the
credential: a login JWT stays valid until it expires, a token until it is revoked.

## Workspaces

Most routes are scoped to a workspace, sent as the `X-Titerlane-Workspace` header. The SDK
takes it from `workspace=` or `TITERLANE_WORKSPACE`. A workspace-scoped call without one raises
`ConfigurationError` before any request is sent.

```python
for ws in client.workspaces.list():
    print(ws.slug, ws.role)

east = client.with_workspace("lab-east")  # same connection and credentials
east.samples.list(limit=10)
```

Routes that are not scoped (`auth`, `workspaces.list/create`, `health`) ignore the workspace.

A workspace you are not a member of answers `404` (`NotFoundError`), exactly like a resource
that does not exist.

### Members

`client.members` manages the members of the client's workspace. Listing is open to every
member; adding, changing a role and removing require `bioinformatics_lead`.

```python
client.members.add("tech@lab.example", role="lab_technician")
client.members.change_role(user_id, "bioinformatics_lead")
client.members.remove(user_id)
```

## Secrets handling

- The token is never logged and never appears in `repr(client)` or in error messages.
- Signed object-storage URLs (FASTQ upload, result download) are credentials too. The SDK
  sends them through a separate HTTP client that never carries the API `Authorization`
  header, and leaves them out of `repr()` and errors.
- Debug logging (`logging.getLogger("titerlane")`) shows method, path and attempt number only.
