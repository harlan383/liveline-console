# Stage 3.3.129 New Transit Resource Draft And Demo Flow

## Stage Goal

Stage 3.3.129 adds a no-real-VPS draft flow for new transit VPS resources.
The operator can create a local LiveLine Console transit resource record before
the real VPS is available or before Worker installation is approved.

The resource is saved as `pending_worker` / waiting for Worker installation.
This stage does not create a Worker token, does not generate a real install
command, does not connect to a remote host, and does not create a HAProxy route.

## Implemented UI/API Changes

- The Transit Servers page now treats "add transit server" as a draft resource
  creation flow.
- The add modal is labeled as a new transit VPS draft, not a Worker install
  command generator.
- The frontend reuses the existing safe `POST /api/transit-resources` API,
  which only writes the system resource record.
- The saved record uses `resource_type=server` and `status=pending_worker`.
- The backend schema now accepts `haproxy_tcp` and `socat` as resource
  `protocol_hint` values so the draft can record the intended forwarding
  direction without creating a route.
- Existing Worker bootstrap token generation is not exposed from this daily
  draft flow. Worker install command generation remains a later approval stage.

## Draft / pending_worker Behavior

Draft resources are displayed as:

- `pending_worker`
- waiting for Worker installation
- not Worker online
- not HAProxy ready
- not route active
- not line usable

The UI shows the next step as Worker install approval and the required Worker
version:

```text
0.1.24-stage-3.3.122
```

The UI also displays the bundled Worker binary checksum for later approval
checks:

```text
cf7990f3ba0f85348fa714edb69a94d36b8752323fe9c843fa676cf50f38fcce
```

## Fields Supported

The draft form supports:

- resource name
- provider
- public entry host or domain
- entry region
- exit region
- bandwidth Mbps
- traffic limit GB
- planned interface name, such as `eth0` or `ens3`
- protocol hint: `haproxy_tcp`, `socat`, or `unknown`
- optional SSH metadata: host, port, and username
- notes

The form must not contain passwords, private keys, Worker tokens, provider
backend credentials, database passwords, or full client links.

The planned interface and preferred forwarding method are recorded only as
draft notes. They are not treated as verified Worker metadata.

## HAProxy Readiness Reminder

Before a future HAProxy TCP route can be created, a later stage must verify:

- new transit Worker online
- Worker version at least `0.1.24-stage-3.3.122`
- HAProxy installed
- `haproxy -v` available
- planned listen port not occupied
- TCP reachability from the new transit VPS to the landing target port
- cloud security group allows the listen TCP port
- cloud firewall allows the listen TCP port
- server firewall allows the listen TCP port

This page only shows the readiness checklist. It does not perform those checks.

## Safety Boundary

This stage did not perform any production action:

- No public controller deployment.
- No real VPS required.
- No Worker token generation.
- No Worker installation.
- No real Worker install command generation.
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
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app
cd frontend && npm run build
```

Sensitive scans were run for full client links, OpenSSH private key markers,
share-link URL patterns, and password/token/secret wording. Any hits are
expected to be safety-boundary or field-name text only, not real credentials or
full client links.

## Next Recommended Stage

Recommended next stage:

```text
Stage 3.3.130-new-transit-worker-install-approval-preview
```

That stage can design the explicit approval preview for generating a one-time
Worker install command. It must still avoid real Worker installation until the
operator separately approves deployment to a real VPS.
