# Stage 3.3.75b Route Promotion Implementation Plan

## Stage Goal

Stage 3.3.75b designs route promotion implementation options for the already
validated Hong Kong `socat` `23843/TCP` candidate path.

This stage is design-only. It does not perform cutover, mutate
`nodes.share_link`, read or export a full `nodes.share_link`, generate a full
node link, create Worker commands, restart or stop `socat`, modify Xray, change
firewall rules, add database migrations, or execute SSH / remote commands.

## Current Candidate State

The current candidate link has already passed client validation:

| Field | Value |
| --- | --- |
| route id | `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af` |
| route name | `hk-socat-live-23843` |
| candidate entry | `163.223.216.108:23843` |
| forwarding target | `64.90.13.19:27939` |
| forwarding method | `socat` |
| service | `liveline-socat-23843.service` |
| route status | `active` |
| client manual test | `passed` |
| route share_link | `NULL / empty` |
| cutover status | `not performed` |

Stage 3.3.74c recorded that the manually imported candidate client profile can
open normal pages, the observed exit remains the landing VPS / landing region,
and short continuous use did not show frequent disconnects.

## Promotion Options

### Option A: Recommended Candidate Flag

Option A marks the route as a recommended client candidate in the console
without generating a new client link and without mutating `nodes.share_link`.

Expected behavior:

- Show `hk-socat-live-23843` as the recommended transit candidate.
- Keep the original direct node unchanged.
- Keep the manually created test client profile as the operator's reference.
- Do not generate, store, or display a full client link.
- Do not write route-derived data into `nodes.share_link`.
- Do not perform cutover.

This is the lowest-risk short-term option because it only changes presentation
and operational guidance.

### Option B: Transient Candidate Export

Option B adds a guarded, temporary export flow for candidate client parameters.
An administrator must explicitly confirm the export, and the backend returns a
one-time transient candidate response for client import.

Future requirements if Option B is implemented:

- Read only the minimum node parameters needed for the candidate export.
- Assemble the candidate link or client parameters transiently for the
  administrator.
- Do not write the assembled candidate link to the database.
- Do not mutate `nodes.share_link`.
- Record an audit event for the export.
- Use masked display by default.
- Require explicit confirmation that this is not cutover.
- Never write full links to README, docs, PRs, logs, or task results.

Option B is useful when operators need a cleaner import flow than manual client
editing, but it carries more disclosure risk than Option A.

### Option C: Formal Cutover

Option C changes the default route or client entry to prefer the Hong Kong
transit path.

This is the highest-risk option and is not recommended as the immediate next
step. A future cutover plan would need separate approval, fresh health checks,
rollback steps, user communication, and explicit decisions about whether any
database field should change.

Option C must remain blocked unless the user explicitly approves a separate
cutover stage.

## Short-Term Recommendation

Use Option A or Option B before any formal cutover work:

- Keep the original direct node.
- Keep the manually validated test client profile available.
- Do not overwrite the original node.
- Do not mutate `nodes.share_link`.
- Do not auto-generate or store a full route-derived link.
- Keep route promotion as an explicit operator decision rather than an implicit
  cutover.

Option A is preferred first because it records and presents the candidate path
without increasing link exposure.

## Future Option B Interface Requirements

If a later stage implements the transient candidate export flow, the interface
must satisfy all of the following:

- The request must require administrator confirmation.
- The response must be transient and must not be persisted as
  `nodes.share_link`.
- The export must be audited.
- Default UI display must be masked.
- Full candidate material may be copied only after explicit confirmation.
- The response must clearly state that no cutover occurred.
- The API must not expose Reality private material or unrelated node fields.
- The API must not write the full candidate link to logs or task results.

## No-Go Conditions

Route promotion implementation must remain No-Go if any of the following are
true:

- The candidate link becomes unstable.
- The observed exit is not the landing VPS / landing region.
- The original direct node is abnormal.
- The user has not explicitly approved the next implementation stage.
- The implementation would require writing `nodes.share_link`.
- Any secret, token, full node link, private key, database password, or provider
  credential could be exposed.

## Stage Boundary

Stage 3.3.75b did not:

- perform cutover
- modify `nodes.share_link`
- read or export full `nodes.share_link`
- generate a full node link
- create a Worker command
- restart, stop, disable, or delete `socat`
- modify Xray
- modify firewall, cloud firewall, or cloud security group rules
- add a database migration
- change backend or frontend code
- execute SSH or remote commands

## Next Stage Recommendation

Proceed to `Stage 3.3.75c-route-promotion-ui-design` if the operator wants a
UI design for Option A or Option B.

Alternatively, proceed to `Stage 3.3.76-longer-stability-observation` if the
candidate should remain under manual observation before any promotion UI work.
