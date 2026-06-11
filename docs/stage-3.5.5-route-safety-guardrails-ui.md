# Stage 3.5.5 Route Safety Guardrails UI

## Current Stage Conclusion

Stage 3.5.5 adds local UI safety guardrails for the current route state. This
stage is a frontend display and documentation update only. It does not change
business logic, authentication logic, database schema, ports, remote services,
or any live route.

Current route state:

- Formal link: `socat 18443`.
- Fallback link: `gost 8443`.
- `node.share_link`: already points to `socat 18443`.

## Frontend Components Updated

- `frontend/components/RouteSafetyGuardrails.tsx`
  - Adds a reusable local UI guardrail panel.
  - Shows the current formal link, fallback link, and `node.share_link` state.
  - Records page-specific safety notes for global layout, transit resources,
    topology preview, and transit routes.
- `frontend/components/AppShell.tsx`
  - Shows the global route guardrail after login and before the panel content.
- `frontend/components/TransitResourcesPanel.tsx`
  - Adds a resource-specific reminder that transit resources are metadata
    records, not usable routes.
- `frontend/components/TransitTopologyPreviewPanel.tsx`
  - Adds a compact current-link protection block alongside the existing
    `PREVIEW ONLY` / `NOT USABLE` topology warnings.
- `frontend/components/TransitRoutesPanel.tsx`
  - Adds single-route safety reminders around port changes, `8443`, `socat`
    18443, and formal cutover approval boundaries.
- `frontend/app/globals.css`
  - Adds the visual style for the route guardrail panel.

## UI Safety Prompts Added

The local UI now reminds the operator:

- Current formal link is `socat 18443`.
- Current fallback link is `gost 8443`.
- `node.share_link` already points to `socat 18443`.
- Do not accidentally modify `node.share_link`.
- Do not close, disable, downgrade, replace, or delete `gost 8443`.
- Do not let `socat` take over `8443`.
- Do not accidentally delete or overwrite `socat 18443`.
- Topology preview does not create a real route.
- Single-route operations must stay inside their explicit stage boundary.

## Port And Firewall Reminder

Before adding or changing any listening port in a future stage, the operator
must confirm that the corresponding TCP port is allowed by:

- Cloud server security group.
- Cloud firewall, if the provider has a separate firewall product.
- Server firewall.

`8443` remains reserved for the `gost` fallback link. This stage does not add
or change any listening port.

## Explicit Non-Changes

- `node.share_link` was not read, printed, or modified.
- No full node link was displayed or written to documentation.
- No database migration was added.
- No listening port was added.
- No SSH command was executed.
- No remote command was executed.
- No backend task was triggered.
- No firewall rule was changed.
- No cutover was performed.
- `socat` was not allowed to take over `8443`.
- `gost 8443` was not closed, disabled, downgraded, replaced, or deleted.

## Future Boundary

If a future stage needs to modify the formal route, change `node.share_link`,
delete a fallback route, or make `socat` take over `8443`, it must enter a
separate formal cutover or route-change approval stage.

## Acceptance Checklist

- The logged-in console shows a current route protection panel.
- Transit resources page states that resource records are not usable routes.
- Topology preview remains clearly marked as preview-only and not usable.
- Single-route page reminds the operator not to use `8443` for new socat
  routes and to check cloud/server firewalls before port changes.
- Pages do not display a full node link.
- No remote operation, backend task, database migration, or port change occurs.

## Safety Boundary

- Do not write real passwords.
- Do not write real hashes.
- Do not write real `SESSION_SECRET` values.
- Do not write SSH Keys.
- Do not write Passphrases.
- Do not write tokens.
- Do not write full node links.
- Do not read or modify `node.share_link`.
- Do not add database migrations.
- Do not add listening ports.
- Do not execute SSH or remote commands.
- Do not trigger backend tasks.
- Do not modify firewalls.
- Do not let `socat` take over `8443`.
- Do not close `gost 8443`.
- Do not perform cutover.
