# Stage 3.3.130 New Transit Worker Install Approval Preview

## Stage Goal

Stage 3.3.130 adds a no-real-VPS Worker install approval preview for
`pending_worker` transit resources.

The Transit Servers page now lets the operator open a read-only approval packet
for a draft transit VPS before any real Worker token, install command, Worker
installation, or route creation is approved.

## UI Changes

- `pending_worker` transit resources show a `查看 Worker 安装审批预览` action.
- The preview modal displays the draft resource name, status, entry host,
  optional SSH host/port/username metadata, entry/exit region, planned
  interface, protocol intent, target Worker version, Worker binary checksum, and
  public controller URL.
- The preview includes a placeholder command template only. It uses
  `<generated-in-later-stage>` for the Worker token and is explicitly marked as
  non-executable in this stage.
- The modal includes Go / No-Go checks and read-only confirmation text.
- The only actions in the modal are closing the preview and copying the approval
  checklist.

## Worker Version And Checksum

The approval preview records the expected Worker version:

```text
0.1.24-stage-3.3.122
```

The preview also records the bundled Linux amd64 Worker binary checksum:

```text
cf7990f3ba0f85348fa714edb69a94d36b8752323fe9c843fa676cf50f38fcce
```

## Public Controller URL

The preview uses the public controller URL:

```text
http://my-con.golirong.xyz:8200
```

The Go / No-Go checklist explicitly requires future install commands to use the
public controller URL, not `localhost` or `127.0.0.1`.

## Placeholder Command Boundary

The command shown in the preview is intentionally a placeholder:

```text
curl -fsSL http://my-con.golirong.xyz:8200/worker/install.sh | \
  sudo bash -s -- \
  --controller-url http://my-con.golirong.xyz:8200 \
  --worker-token <generated-in-later-stage> \
  --role transit
```

This stage does not generate a real Worker token and does not generate a real
install command. Real installation must be reviewed and approved in a later
independent stage.

## Go / No-Go Checklist

The approval preview records these checks for the next installation stage:

- Public controller backend health returns 200.
- Worker binary local/public checksum match.
- New VPS can access the public controller URL.
- New VPS has root or sudo, systemd, and curl.
- Install command must use the public controller URL, not `localhost` or
  `127.0.0.1`.
- SSH private keys, passwords, Worker tokens, provider credentials, database
  passwords, and secrets must not be stored in notes, README, PRs, logs, or chat.

## Safety Boundary

This stage did not perform any production action:

- No public controller deployment.
- No real VPS connection.
- No Worker token generation.
- No real Worker install command generation.
- No Worker installation.
- No SSH or remote command.
- No Worker command creation.
- No HAProxy route creation.
- No HAProxy installation.
- No socat mutation.
- No Xray mutation.
- No firewall, security group, or cloud firewall mutation.
- No cutover.
- No full `nodes.share_link` exposure.
- No `transit_routes.share_link` write.
- No Worker online status was faked.
- No HAProxy ready status was faked.
- No route active or line usable state was faked.

## Validation

Validation performed for this stage:

```bash
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
cd frontend && /Users/peng/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/next/dist/bin/next build
```

Sensitive scans were run for full client links, OpenSSH private key markers,
share-link URL patterns, real Worker token patterns, database passwords, and
secret wording. Any `token` / `secret` hits are expected to be safety-boundary
or placeholder text only, not real credentials.

## Next Recommended Stage

Recommended next stage:

```text
Stage 3.3.131-new-transit-worker-install-execution-approval
```

That stage can request explicit approval before generating a one-time Worker
token and installing the Worker on a real new transit VPS.
