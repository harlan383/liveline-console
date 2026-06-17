# Stage 3.3.43 — Transit Integration Planning

## 1. Purpose

Stage 3.3.43 records the planning boundary for integrating a transit route in front
of the currently accepted formal landing node.

The stage is intentionally documentation-only. It prepares the decision framework
for a future Hong Kong transit server / IEPL / IPLC route without creating a new
route, changing the current node, changing `nodes.share_link`, opening ports, or
running remote commands.

## 2. Current baseline

The current formal landing node has already completed client acceptance. The
console must treat that landing node as the destination for future transit-route
planning, but this document does not repeat sensitive client import materials or
private Xray configuration values.

Baseline facts for planning:

- Current accepted landing node: `liveline-reality-27939`.
- Current landing protocol family: VLESS Reality over TCP with Vision flow.
- Current formal landing node status: accepted and usable by the client.
- `share_link` exists in the database but is default-redacted by the API and UI.
- Full node export requires explicit `confirm_export: true`.
- Node key rotation / rebuild / old-link retirement has a separate runbook in
  `docs/stage-3.3.41-node-key-rotation-runbook.md`.

Values intentionally not recorded here:

- Full `vless://` links.
- Full `nodes.share_link` values.
- Reality private keys.
- Worker setup tokens.
- Database passwords.
- Public or private Xray config contents.

## 3. Non-goals and safety boundary

Stage 3.3.43 does not perform any operational change.

It does not:

- Execute SSH or Worker remote commands.
- Deploy the public console.
- Reinstall, restart, stop, or upgrade the Worker.
- Install `socat`, `gost`, Xray, nginx, or any relay tool.
- Create, delete, rebuild, rotate, or cut over any node.
- Create or modify a transit route in production.
- Add or change a listening port.
- Modify cloud security groups, cloud firewalls, or local server firewalls.
- Modify iptables / nftables.
- Modify Xray config on the landing node.
- Modify `nodes.share_link`.
- Generate or expose a usable transit client link.
- Change database schema or run Alembic migrations.

Any future stage that adds or changes a listening port must explicitly remind the
operator to allow the corresponding TCP port in the cloud security group / cloud
firewall and verify the server-local firewall state before executing the route.

## 4. Target topology to plan

The intended future topology is:

```text
client
  -> transit listener on Hong Kong / IEPL / IPLC transit resource
  -> TCP forwarding path
  -> accepted formal landing node
  -> target platform traffic
```

The future transit listener should be treated as a separate access endpoint. The
landing node remains the destination. The transit layer should not require
modifying the landing node unless a later approved design explicitly chooses a
landing-side change.

## 5. Candidate implementation options

| Option | Summary | Fit for next planning step | Main risk |
| --- | --- | --- | --- |
| `socat` TCP forward | Simple local TCP listener forwarding to the landing node TCP port | Best first candidate because the previous controlled route work already used `socat` successfully | Needs systemd wrapper / restart guard / port safety checks |
| `gost` TCP forwarding | More feature-rich TCP forwarding tool; can be kept as fallback or alternative | Good fallback if route observability or advanced transport features are needed | Configuration modes must avoid protocol translation that could affect Reality ClientHello |
| Xray `dokodemo-door` | Xray-native inbound forwarding to the landing node | Useful later if Xray-managed transit features become necessary | More moving parts; higher chance of config collision with landing-node semantics |
| iptables / nftables DNAT | Kernel-level forwarding | Not preferred for the next controlled stage | Harder rollback, harder operator visibility, and greater firewall blast radius |

Recommended first planning path:

1. Keep the current landing node unchanged.
2. Plan a single transit listener using `socat` as the first future route option.
3. Preserve `gost` as a documented fallback option, not the default first action.
4. Avoid iptables / nftables for the next route unless a later design proves it is
   necessary.
5. Keep Xray `dokodemo-door` as a later alternative, not the first execution path.

## 6. Port strategy

Future transit listener ports should follow the existing high-port safety style:

- Prefer a random high TCP port outside common service ports.
- Avoid protected ports such as `22`, `80`, `443`, `5432`, `6379`, `8000`, and
  other console / database / Redis / SSH ports.
- Require a read-only preflight check before any real execution.
- Require explicit user approval before the future execution stage.
- Require cloud security group / cloud firewall / local firewall confirmation
  before the route is considered ready.

This stage does not reserve or open any port.

## 7. Future execution gates

Before any later real transit execution, the following gates should be completed
in order:

1. **Target confirmation** — select the exact transit resource, destination
   landing node, and candidate listener port.
2. **Read-only preflight** — verify OS, architecture, systemd, installed tools,
   listener conflicts, route reachability, and firewall state without modifying
   anything.
3. **Firewall confirmation** — confirm the cloud security group / cloud firewall
   and server-local firewall allow the candidate TCP listener port.
4. **Execution approval** — record explicit user approval for one route, one
   listener port, and one forwarding method.
5. **Controlled execution** — install or reuse the selected forwarding tool,
   create a systemd-managed route, and verify the listener.
6. **Client acceptance** — test the derived transit endpoint from the client.
7. **Cutover decision** — only after client acceptance, decide whether to keep the
   old direct link, promote the transit route, or keep it as a candidate.

## 8. Future stage split proposal

Recommended follow-up stages:

- `Stage 3.3.44-transit-target-selection-record` — choose the exact transit
  resource, landing node, and candidate listener port. Documentation-only.
- `Stage 3.3.45-transit-readonly-preflight-approval` — approve a read-only
  preflight checklist. No remote write actions.
- `Stage 3.3.46-transit-readonly-preflight-execution` — run only read-only
  diagnostics if explicitly authorized.
- `Stage 3.3.47-transit-firewall-confirmation-record` — record cloud security
  group / cloud firewall / local firewall confirmations.
- `Stage 3.3.48-transit-controlled-execution-approval` — approve one concrete
  route execution plan.
- `Stage 3.3.49-transit-controlled-execution` — future real execution stage, only
  after all gates pass.
- `Stage 3.3.50-transit-client-acceptance-record` — record client import and
  usability result without exposing full links.

## 9. Validation performed in this stage

This planning stage only validates documentation boundaries:

- Reviewed current accepted landing-node baseline from the project continuation
  summary.
- Confirmed that no complete client link or private key material is needed for
  route planning.
- Confirmed that future port changes require explicit cloud security group / cloud
  firewall / local firewall reminders and confirmation.
- Confirmed that this stage should not trigger deployment or remote execution.

## 10. Stage result

Stage 3.3.43 is complete when this document is merged.

The result is a documented No-Go boundary for real transit execution and a staged
path toward a future controlled transit route. The current formal landing node
remains unchanged and usable, and no new transit endpoint is created by this
stage.
