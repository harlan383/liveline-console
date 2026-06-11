# Stage 3.5.4 Topology Preview Usability Polish

## Current Stage Conclusion

Stage 3.5.4 improves the usability and safety messaging of the local transit
topology preview page.

This stage changes frontend display text and styling only. It does not change
backend logic, database schema, `node.share_link`, listening ports, firewall
rules, backend tasks, or the current transit links.

## Stage Goal

The topology preview page must make it obvious that the page is only a local
frontend preview:

- `PREVIEW ONLY`
- `NOT USABLE`
- Local browser preview only.
- No remote connection.
- No configuration write.
- No saved route.
- No real forwarding rule creation.
- No real usable transit link generation.
- No `node.share_link` modification.

## Modified Frontend Components

| File | Change |
| --- | --- |
| `frontend/components/TransitTopologyPreviewPanel.tsx` | Strengthened preview-only text, current link status, topology segment labels, preview-port wording, and safety boundary notices |
| `frontend/app/globals.css` | Added small dedicated styles for the current-link status strip and field hint text |

No frontend API type change was needed.

## What Topology Preview Means

Topology preview is a local planning view. It helps the operator understand a
possible future chain:

```text
client -> transit server -> landing VPS / node -> target platform
```

It is not a route creation screen, not an apply-config screen, and not a real
client-link generator.

## Preview Is Not a Usable Line

The page now states in more visible language:

- This is only a browser-local sketch.
- It is not a client-importable working line.
- It does not connect to remote hosts.
- It does not write configuration.
- It does not save `transit_routes`.
- It does not create remote forwarding.
- It does not generate a real usable transit link.
- It does not modify `node.share_link`.

The refresh button remains a preview-data refresh action only.

## Topology Display Improvements

The topology view now separates the chain into clear segments:

| Segment | Meaning |
| --- | --- |
| Client | Operator or client software |
| Transit resource | Selected active transit resource |
| Landing VPS / node | Selected active node and necessary landing IP / port |
| Target platform | Target platform / unspecified |

The expected relay listen port is labeled as `preview port` and described as a
planned value, not an actual listening port.

## Current Production Link Status Shown on Page

The page now displays the current project link state:

| Item | Current state |
| --- | --- |
| Formal link | `socat` 18443 |
| Fallback link | `gost` 8443 |
| `node.share_link` | Already points to `socat` 18443 |

The page also states that topology preview will not modify those states and
will not read or show complete node links.

## Safety Boundary Shown on Page

The page now explicitly states:

- No SSH is executed.
- No remote forwarding is created.
- No new listening port is added.
- No firewall rule is modified.
- `gost` 8443 is not closed.
- `socat` does not take over 8443.
- No complete `share_link`, Reality privateKey, SSH Key, SSH password, or
  notes content is included.
- If a future stage adds or changes a listening port, the operator must check
  cloud security group, cloud firewall, and server firewall rules for the
  corresponding TCP port.

## Current Production Link Protection Boundary

| Item | Current state |
| --- | --- |
| Formal link | `socat` 18443 |
| Fallback link | `gost` 8443 |
| `node.share_link` | Already points to `socat` 18443 |
| Stage 3.5.4 `node.share_link` changes | None |
| Stage 3.5.4 new listening ports | None |
| Stage 3.5.4 `socat` 8443 takeover | None |
| Stage 3.5.4 `gost` 8443 shutdown / downgrade / replacement | None |
| Stage 3.5.4 cutover activity | None |

## Future Real Route Creation

If the operator wants to create or modify a real route, that must happen in a
separate single-route creation or route-management stage. It must not be
treated as part of topology preview.

## Stage 3.5.4 Recorded Impact

| Item | Result |
| --- | --- |
| Modified frontend display | Yes |
| Modified backend business logic | No |
| Added database migration | No |
| Added listening port | No |
| Modified `node.share_link` | No |
| Read or output complete node link | No |
| Executed SSH / remote command | No |
| Triggered backend task | No |
| Performed cutover | No |
| Closed `gost` 8443 | No |
| Let `socat` take over 8443 | No |
| Affected `socat` 18443 formal link | No |
| Affected `gost` 8443 fallback link | No |

## Safety Boundary

- Do not write real passwords, real hashes, `SESSION_SECRET` values, SSH Keys,
  Passphrases, tokens, or complete node links.
- Do not read or output complete node links.
- Do not execute SSH or remote commands.
- Do not trigger backend Worker/RQ tasks.
- Do not modify firewall rules.
- Do not perform cutover.
- Do not add listening ports.
- Do not modify `node.share_link`.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not let `socat` take over 8443.

## Usability Polish Conclusion

Topology preview is now clearer and safer for local use. The page communicates
that it is preview-only, shows the current formal and fallback link roles, and
keeps real route creation separated from local planning.
