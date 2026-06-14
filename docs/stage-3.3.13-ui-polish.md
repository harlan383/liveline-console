# Stage 3.3.13 UI Polish

## Current Stage Conclusion

Stage 3.3.13 UI polish upgrades the local console from a development-style
debug panel toward a clearer dark SaaS operations console.

This stage changes frontend presentation and documentation only. It does not
perform formal cutover, modify `node.share_link`, execute SSH or remote
commands, add database migrations, add listening ports, change backend core
deployment logic, change existing API compatibility, or remove existing
features.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` remains pointed at `socat` 18443.

## Stage Goal

The goal is to make LiveLine Console feel more like an operator-facing VPS and
transit-route management console:

- Clearer navigation.
- Better dark visual hierarchy.
- More readable Dashboard metrics.
- Consistent status labels.
- Safer transit-route and formal cutover messaging.
- Clearer task progress and result display.

## Modified Scope

Modified frontend areas:

- `AppShell`: navigation, top status bar, dashboard, settings/safety overview.
- Global CSS: dark operations-console theme, panels, cards, status tags,
  buttons, route safety blocks, and responsive behavior.
- Servers page: readonly operations summary for SSH, Xray, 3x-ui, and last
  check state.
- Nodes page: status labels and `share_link` state presentation.
- Transit Routes page: route-flow visualization and formal/candidate/rollback
  safety banner.
- Tasks page: task progress card and progress bar.

Documentation updates:

- `README.md`
- `docs/stage-3.3.13-ui-polish.md`

## UI Improvements

### Overall Style

- Updated the interface to a darker technology / operations-console style.
- Improved cards, panel contrast, borders, spacing, and focus states.
- Kept card radius restrained and consistent with the existing console layout.

### Left Navigation

The left navigation now presents the console as operational sections:

- Dashboard
- Servers
- Nodes
- Transit Routes
- Tasks
- Diagnostics
- Settings

The active page is highlighted.

### Dashboard

The Dashboard now summarizes local console state with readonly cards:

- VPS total estimate.
- Online VPS estimate.
- Total nodes.
- Healthy nodes.
- Abnormal nodes.
- Transit route count.
- Recent task status.
- Local health status.

These metrics are derived from existing API reads only.

### Status Labels

Status labels were visually normalized:

- Success: green, for healthy / success states.
- Warning: yellow, for caution / pending confirmation.
- Danger: red, for failures or dangerous boundaries.
- Muted: gray, for unknown / unchecked / no data states.

### Servers

The Servers entry now has a clearer readonly operations summary:

- SSH status source.
- Xray status source.
- 3x-ui status is explicitly shown as not connected / not used.
- Last check time when available.

No server-side behavior changed.

### Nodes

Node rows and details now show clearer status labels and a safer `share_link`
state. The UI may display whether a share link exists, but this stage does not
modify `node.share_link`.

### Transit Routes

Transit route cards now emphasize the route structure:

```text
Local client
  -> Transit server: listen port
  -> Landing VPS: target port
  -> Xray Reality node
```

The page also highlights:

- Candidate link: `socat` 18443.
- Formal link: `node.share_link -> socat` 18443.
- Rollback link: `gost` 8443.

The safety reminder is preserved and strengthened:

- Any new or changed listening port must be checked against cloud security
  groups, cloud firewall, and server firewall TCP allow rules.

### Tasks

Task details now show a clearer progress block:

- Task status.
- Current step.
- Progress percentage.
- Visual progress bar.
- Result and log sections remain available.

### Formal Cutover Boundary

Formal cutover remains locked behind separate approval. The UI distinguishes:

- Candidate link.
- Formal link.
- Rollback link.

Dangerous formal cutover actions are not enabled by this stage. The page states
that this stage is not formal cutover.

## Unchanged Backend and Safety Boundaries

This stage does not:

- Modify backend core deployment logic.
- Change existing API compatibility.
- Add database migrations.
- Add listening ports.
- Execute SSH.
- Execute remote commands.
- Trigger Worker/RQ tasks.
- Create real forwarding.
- Perform formal cutover.
- Modify `node.share_link`.
- Close, stop, downgrade, or replace `gost` 8443.
- Let `socat` take over 8443.

## Risk Boundary

This stage is visual polish and documentation. It improves readability and
operator safety messaging but does not grant permission to perform any network
or production-link operation.

If a future stage creates or changes real listening ports, it must separately
confirm cloud security group, cloud firewall, and server firewall TCP rules.

If a future stage modifies `node.share_link`, it must enter a separate formal
cutover approval stage.

## Acceptance Checklist

- Dashboard uses the new dark operations-console layout.
- Left navigation includes Dashboard, Servers, Nodes, Transit Routes, Tasks,
  Diagnostics, and Settings.
- Active navigation state is visible.
- Dashboard overview cards are visible.
- Status labels are visually consistent.
- Servers page shows readonly SSH / Xray / 3x-ui / last-check summary.
- Nodes page shows clearer node and share-link status.
- Transit Routes page shows candidate / formal / rollback link boundaries.
- Transit Routes page shows the route structure from client to transit server
  to landing node.
- Tasks page shows clearer task progress.
- The UI warns that new or changed listening ports require cloud and server
  firewall checks.
- No full node link is written into documentation.
- `node.share_link` is not modified.
- No database migration is added.
- No listening port is added.
- No SSH or remote command is executed.
- No formal cutover is performed.
