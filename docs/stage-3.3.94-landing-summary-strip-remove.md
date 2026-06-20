# Stage 3.3.94 Landing Summary Strip Remove

## Purpose

Stage 3.3.94 removes the redundant landing-server summary strip from the landing server page UI.

The removed visible area is the four-card summary strip near the top of the landing server page:

- landing server count
- direct node count
- client configuration count
- Worker online count

This block duplicated information already available in the lower server table and made the page visually noisy. The daily-use page should stay focused on the actual landing server and direct-node records.

## Change

UI-only change:

- Add `frontend/app/ui-overrides.css`.
- Import the override stylesheet from `frontend/app/layout.tsx`.
- Hide `.server-management-panel .landing-status-strip`.

This removes the red-boxed summary strip from the rendered UI while keeping the underlying table, node rows, copy action, QR action, and advanced debug sections unchanged.

## Safety Boundary

This stage does not:

- execute cutover
- modify `nodes.share_link`
- write `transit_routes.share_link`
- read or export complete `nodes.share_link`
- generate or record complete node links
- create Worker commands
- create VPS records
- create nodes
- create transit routes
- add listening ports
- restart, stop, or delete `socat`
- modify Xray
- modify firewalls, cloud firewalls, or cloud security groups
- execute SSH or remote commands
- add database migrations
- deploy the public console
- change backend APIs
- change Worker code or binaries

## Validation

Connector-side validation for this stage:

- changed files are limited to frontend CSS import / CSS override and this documentation file
- no backend files changed
- no Worker files changed
- no database migration changed
- no link-bearing files or runtime logs changed

Runtime validation after deployment should confirm:

- the landing server page no longer shows the four-card summary strip
- the landing server table still loads
- direct node rows still show under the server
- copy client link and temporary QR actions remain available
- advanced read/debug sections remain collapsed by default

## Result

The unnecessary top summary strip is removed from the landing server UI.

The actual network-build functionality is unchanged.