# Stage 3.3.90 Landing Server Node Usability Polish

## Purpose

Stage 3.3.90 improves the `落地服务器` / direct node page for lightweight self-use network setup.

LiveLine Console remains a small personal network-building and troubleshooting helper, not a complex commercial node platform. The priority in this stage is making the existing network-building flow easier to understand:

- view landing VPS records
- view direct Reality node summaries
- copy or temporarily export client configuration
- keep advanced read/debug actions out of the daily path

Troubleshooting remains a later independent module and is not expanded in this stage.

## Product Principle

The page should help the operator quickly answer:

- Which landing VPS records exist?
- Which direct nodes are already attached?
- Is there a client configuration available to copy?
- Which actions are normal setup actions, and which are advanced read/debug actions?

The page should not introduce multi-node platform features, automatic cutover, route recommendation, automatic switching, or a full troubleshooting workflow.

## Changes

### Landing Server List

The landing server page now has a compact status strip:

- landing server count
- direct node count
- copy-ready client configuration count
- online Worker count

Each server row keeps normal setup actions visible:

- create node plan
- generate or regenerate Worker install command
- edit server metadata

Advanced actions are moved behind `高级读取与调试`:

- Worker check
- landing readonly preflight
- delete system record

The folded advanced section warns that these actions are mainly for development or troubleshooting and are not needed for daily network setup.

### Direct Node Summary

Direct node child rows are rewritten as a clearer summary:

- node name
- entry address and port
- protocol summary
- node status
- whether client configuration can be copied
- whether `share_link` exists

The primary node actions now use more explicit wording:

- `查看摘要`
- `复制客户端链接`
- `临时二维码`

Complete node links are not displayed in the main list.

### Copy / Export Flow

The node detail modal now describes the link as a client configuration link. It keeps the complete link hidden by default and only exports it after an explicit confirmation.

When Clipboard API is unavailable, such as in an HTTP browser context, the page opens the detail flow and shows the temporary link field for manual copy. The complete link is still not written to docs, README, logs, or audit text.

### Advanced Debug Boundary

This stage does not create a troubleshooting module. It only makes existing advanced read/debug actions less prominent so the daily setup path is easier to use.

## Not Implemented

This stage does not add:

- one VPS with multiple active nodes
- node port pools
- batch node creation
- automatic node switching
- node deletion or replacement flows
- database unique-constraint changes
- full troubleshooting diagnostics

Those remain outside the current network-building polish scope.

## Safety Boundary

This stage does not:

- create VPS records
- create, delete, or modify nodes
- modify `nodes.share_link`
- read or export complete `nodes.share_link` into README, docs, logs, or audit text
- create Worker commands
- execute SSH or remote commands
- install, restart, stop, or modify Xray
- modify Xray configuration
- add listening ports
- modify firewalls, cloud firewalls, or cloud security groups
- create transit routes
- execute cutover
- add database migrations
- deploy the public console
- run client tests
- modify backend APIs
- modify Worker binaries

## Validation

Required validation for this stage:

- `git diff --check`
- `git diff --cached --check`
- `docker compose exec -T frontend npm run build`
- sensitive information scan

Backend tests and Go builds are not required because this stage modifies only frontend display/CSS and documentation.

## Result

The landing server page now presents direct node status and client-copy readiness more clearly, keeps daily setup actions visible, and folds advanced read/debug actions by default. No backend behavior, Worker behavior, database state, node link, Xray configuration, or production network state is changed.
