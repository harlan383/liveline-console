# Stage 3.3.44 — Transit Target Selection Record

## 1. Purpose

Stage 3.3.44 records the target-selection boundary for a future transit route in
front of the accepted landing node. This stage exists to keep the next execution
path explicit and auditable before any read-only preflight or controlled route
execution is allowed.

This stage is documentation-only. Because the operator has not yet supplied a
specific transit resource and candidate listener port in the current stage, this
record intentionally preserves those fields as `Pending operator selection`
instead of guessing or silently authorizing a route.

## 2. Current baseline

The immediately preceding planning stage is
`docs/stage-3.3.43-transit-integration-planning.md`.

Baseline carried forward:

- Current accepted landing node: `liveline-reality-27939`.
- Landing-node role in this stage: future transit destination only.
- Preferred first future forwarding method from the planning stage: `socat` TCP
  forward.
- Fallback method: `gost` TCP forwarding, only if later explicitly selected.
- Later alternatives: Xray `dokodemo-door` or iptables / nftables, not selected
  for the next controlled route by default.
- Full node export remains protected by explicit confirmation.
- Sensitive link and key material must remain excluded from documentation.

## 3. Selection record

| Field | Recorded value | Status |
| --- | --- | --- |
| Transit resource | `Pending operator selection` | Not selected |
| Transit resource type | `server`, `iepl`, `iplc`, or `other` | Not selected |
| Transit resource region | Hong Kong / IEPL / IPLC candidate expected | Not selected |
| Landing node | `liveline-reality-27939` | Selected as destination baseline |
| Landing node port | Existing accepted landing-node port only; do not repeat private client details here | Existing baseline |
| Forwarding method | `socat` TCP forward recommended for the first future route | Planned default, not executed |
| Candidate transit listener port | `Pending operator selection` | Not selected |
| Cloud security group confirmation | Pending | Not confirmed |
| Cloud firewall confirmation | Pending | Not confirmed |
| Server-local firewall confirmation | Pending | Not confirmed |
| Read-only preflight authorization | Pending | Not authorized by this stage |
| Real route execution authorization | Not authorized | No-Go |
| Cutover authorization | Not authorized | No-Go |

## 4. Decision made by this stage

This stage makes only one decision:

- The future route should target the accepted landing node
  `liveline-reality-27939` unless the operator later changes the destination in a
  separate documented stage.

This stage does not select:

- A concrete Hong Kong transit server.
- A concrete IEPL / IPLC transit resource.
- A concrete public listener port.
- A concrete cloud firewall rule.
- A concrete systemd service name.
- A concrete client import endpoint.

## 5. Required operator inputs before the next executable planning step

Before a future read-only preflight can be run, the operator must provide or
confirm:

1. The exact transit resource record to use.
2. The transit resource type: `server`, `iepl`, `iplc`, or `other`.
3. The expected transit resource region or line type.
4. The candidate TCP listener port on the transit resource.
5. Whether the candidate listener port has already been allowed in the cloud
   security group / cloud firewall.
6. Whether the server-local firewall is active and whether the candidate listener
   port is allowed locally.
7. Whether the next step is only read-only preflight, not real execution.

If any of these values are missing, the next real or read-only route stage must
remain blocked.

## 6. Port-selection guardrails

A later concrete listener port must follow these rules:

- Prefer a random high TCP port.
- Avoid SSH, web, database, Redis, console, and protected service ports.
- Do not reuse a port that is already listening on the transit resource.
- Do not reuse old fallback ports unless explicitly approved.
- Do not assume a provider firewall is open just because Linux is listening.
- Require cloud security group / cloud firewall confirmation before execution.
- Require server-local firewall confirmation before execution.

This stage does not reserve or open any port.

## 7. Future read-only preflight checklist

A later `Stage 3.3.45` / `Stage 3.3.46` read-only preflight should verify only
non-mutating facts, such as:

- Transit resource OS and architecture.
- Current user and privilege boundary.
- systemd availability.
- Installed forwarding tools, if any.
- Current TCP listeners.
- Whether the candidate listener port is already occupied.
- Firewall tooling and firewall state.
- Basic TCP reachability from the transit resource to the landing node.
- Whether the landing-node destination port is reachable from the transit host.

The preflight must not install packages, write files, create services, restart
services, modify firewall rules, or generate client links.

## 8. No-Go boundary

Stage 3.3.44 does not:

- Execute SSH or Worker remote commands.
- Run read-only preflight.
- Install, reinstall, start, stop, or restart `socat`, `gost`, Xray, nginx, or
  Worker.
- Create a transit route.
- Create a systemd service.
- Add or change a listening port.
- Modify cloud security groups, cloud firewalls, or local firewall rules.
- Modify iptables / nftables.
- Modify Xray config.
- Modify `nodes.share_link`.
- Export a full node link.
- Generate a transit client endpoint.
- Create, delete, rebuild, or rotate nodes.
- Change database schema or run Alembic migrations.
- Deploy the public console.

## 9. Sensitive-data handling

This document intentionally excludes:

- Full `vless://` links.
- Full `nodes.share_link` values.
- Reality private keys.
- Worker setup tokens.
- Database passwords.
- Full Xray configuration.
- Provider account credentials.
- SSH private keys.

Any future client acceptance record must keep full links redacted by default and
only describe whether the client test passed or failed.

## 10. Stage result

Stage 3.3.44 is complete when this document is merged.

Result:

- The landing-node destination baseline is recorded as `liveline-reality-27939`.
- The transit resource remains pending operator selection.
- The candidate listener port remains pending operator selection.
- Firewall confirmations remain pending.
- Read-only preflight remains unauthorized by this stage.
- Real execution and cutover remain No-Go.

Recommended next stage:

`Stage 3.3.45-transit-readonly-preflight-approval`

That next stage should remain blocked until the operator provides the exact transit
resource and candidate listener port, or it should explicitly document that those
inputs are still missing and therefore preflight execution is still No-Go.
