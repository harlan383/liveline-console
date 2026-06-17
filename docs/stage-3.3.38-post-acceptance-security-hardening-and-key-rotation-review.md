# Stage 3.3.38 Post-Acceptance Security Hardening and Key Rotation Review

## Stage Goal

Stage 3.3.38 records a security review after the formal VLESS Reality landing
node passed client acceptance.

This stage produces a risk assessment and follow-up hardening plan. It does not
rotate keys, recreate the node, change runtime services, or modify the public
environment.

## Execution Boundary

This stage did not:

- execute SSH or remote commands
- connect to the public console VPS
- connect to the landing VPS
- run `docker compose`
- query the real database
- trigger `landing_node_create`
- reinstall Worker
- install Xray
- restart or stop `liveline-xray`
- modify Xray config
- delete, recreate, rotate, or rebuild the current node
- add listening ports
- modify firewall, cloud firewall, or cloud security group rules
- modify `node.share_link`
- output a complete node link
- perform cutover

## Current Accepted Node Summary

The accepted node is recorded only as a summary:

```text
node_name = liveline-reality-27939
landing_ip = 64.90.13.19
xray_port = 27939
protocol = vless
transport = tcp
security = reality
flow = xtls-rprx-vision
service_status = active
status = active
client_acceptance = passed
```

The complete `node.share_link`, complete UUID, Reality privateKey, complete
Reality public key, and shortId are intentionally not recorded.

## Identified Sensitive Exposure Surfaces

| Area | Exposure Surface | Notes |
| --- | --- | --- |
| Worker setup token | A complete Worker setup token previously appeared in conversation context | Treat as exposed unless confirmed expired, consumed, or invalidated. |
| Node connection material | UUID, Reality public key, and shortId were previously seen in operational output | These are not the Reality privateKey, but they are still connection material and should not continue to be published. |
| Full node link | Complete `vless://` or full `node.share_link` | Must not be pasted into chat, PRs, docs, logs, or terminal transcripts. If externally copied, plan node rotation. |
| Xray config content | Full `/opt/liveline-xray/config/config.json` | Must not be printed with `cat`, copied into docs, or pasted into logs because it can contain private key material. |
| Runtime summary | Port, protocol, service state, managed paths | Low risk for operational notes, but should remain summary-only and exclude full config content. |

## Risk Classification

### High Risk

- Complete Worker setup token exposure.

Recommended handling:

- Confirm whether the exposed setup token is already expired, consumed, or
  invalidated.
- Add or verify one-time-use token semantics.
- Add or verify token TTL enforcement.
- Hide complete tokens after generation.
- Do not paste complete Worker setup tokens in chat, PRs, logs, docs, or issue
  comments.

### Medium Risk

- Complete `node.share_link` exposure outside trusted local client import flow.
- UUID, Reality public key, and shortId appearing in logs or copied output.

Recommended handling:

- If the complete `node.share_link` was copied outside trusted local use, plan a
  formal node rotation or rebuild with fresh Reality material.
- Stop displaying full connection material by default.
- Redact or mask share links in API responses, task summaries, UI tables, and
  future docs.
- Require explicit user confirmation before exporting a full client link.

### Low Risk

- Port number, protocol type, service status, and managed Xray paths.

Recommended handling:

- Keep these as summary fields only.
- Do not include full Xray config, private keys, complete client links, or raw
  database rows in review notes.

## Immediate Rotation Decision

Do not immediately destroy, rotate, or rebuild the currently working node from
this review stage alone.

Rationale:

- The current node is accepted and usable.
- No Reality privateKey or complete `vless://` link is recorded in this stage.
- Immediate rotation would interrupt a known-good service.
- A safer path is to first harden token handling and share-link exposure, then
  prepare a node rotation runbook and approval stage.

Immediate rotation becomes recommended if any of these are confirmed:

- complete `node.share_link` was shared outside trusted local client import
  context
- Reality privateKey was exposed
- complete Xray config content was pasted to logs, PRs, docs, or chat
- client link was posted to an untrusted channel
- current node is suspected compromised

## Recommended Security Closure Order

1. Worker setup token hardening.
2. Share-link redaction and export confirmation.
3. Node key rotation runbook.
4. Formal node rotation execution approval.
5. Transit integration planning.

This order avoids breaking the accepted node while closing the highest-risk
future exposure path first.

## Recommended Follow-Up Stages

```text
Stage 3.3.39-worker-setup-token-one-time-use-hardening
Stage 3.3.40-share-link-redaction-and-export-confirmation
Stage 3.3.41-node-key-rotation-runbook
Stage 3.3.42-formal-node-rotation-execution-approval
Stage 3.3.43-transit-integration-planning
```

Do not execute these stages from this document.

## Security Operating Principles

- Do not paste complete Worker setup tokens into chat, PRs, logs, docs, or issue
  comments.
- Do not paste complete `vless://` links into chat, PRs, logs, docs, or issue
  comments.
- Do not run or share output from `cat /opt/liveline-xray/config/config.json`.
- When querying database state, prefer `length(share_link)` or
  `has_share_link` instead of returning full link values.
- When producing command output, exclude or redact fields such as
  `share_link`, `secure_share_link`, and `client_link`.
- For remote validation, inspect service state, listening ports, and node
  summaries only. Do not inspect or print private key material.
- Frontend export of a complete client link should require deliberate user
  action and a clear warning.
- Backend APIs should not return complete `node.share_link` by default.

## Current Status Conclusion

- Formal landing node creation and client acceptance have passed.
- Current accepted node remains in service.
- This review stage does not change the runtime state.
- Worker setup token handling is the highest-priority hardening target.
- Share-link redaction and export confirmation should follow.
- Node rotation should be planned with a runbook before any disruptive action.
- This stage is not a cutover.

## Validation Checklist

- `git diff --check`
- `python3 -m compileall backend/app`
- Sensitive scan for complete `vless://`, Reality privateKey, complete
  `node.share_link`, complete Worker setup token, passwords, `SESSION_SECRET`,
  database passwords, complete UUID, complete public key, and complete shortId.
