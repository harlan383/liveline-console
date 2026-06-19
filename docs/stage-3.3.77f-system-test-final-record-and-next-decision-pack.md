# Stage 3.3.77f System Test Final Record And Next Decision Pack

## Stage Goal

Stage 3.3.77f consolidates the remaining record, decision, and backlog notes
after the Stage 3.3.77 candidate UI/export work.

This stage intentionally replaces several smaller record-only stages:

- copy fallback retest record;
- candidate export system test final record;
- HTTPS backlog record;
- next decision pack record.

This stage is documentation-only. It does not change code, deploy the public
console, execute production commands, or run client tests.

## Stage 3.3.77c Retest Result

The Stage 3.3.77c copy fallback fix was deployed and retested with the public
console.

Verified facts:

- main included `17d9ac8b0b0ad34b56aebc11a2d5fa422428ec53`;
- frontend was rebuilt and recreated;
- clicking `复制完整候选链接` on the HTTP page no longer falsely reported
  successful automatic copy;
- when the Clipboard API was unavailable, the page displayed the manual-copy
  textarea fallback;
- after manually copying the transient candidate link, the client import could
  browse normally;
- the exit remained the landing VPS / landing region;
- `transit_routes.share_link` remained unwritten for route
  `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af`;
- `has_share_link=false` for the transit route;
- the original landing node `nodes.share_link` remained present and unchanged;
- node id `a71472c6-f62c-43b5-a223-9f5f070ae4ef` still had
  `has_share_link=true`;
- the original landing node share-link length remained `250`;
- `liveline-socat-23843.service` remained active;
- `23843/TCP` remained listening;
- no cutover occurred.

Only presence and length were checked for `nodes.share_link`. The full value was
not selected, printed, copied into docs, or recorded.

## Stage 3.3.77 Functional Closure

The current system is closed through the candidate UI/export loop:

- the Hong Kong transit route was created successfully in earlier execution
  stages;
- the route is active;
- `liveline-socat-23843.service` is active / enabled;
- `23843/TCP` is listening;
- the client candidate path is usable;
- the candidate route UI is visible;
- candidate configuration summary can be viewed;
- transient test configuration export works;
- HTTP manual-copy fallback works;
- full candidate links were not written to README, docs, audit logs, or PR text;
- `nodes.share_link` was not modified;
- `transit_routes.share_link` was not written;
- no cutover occurred.

## Known Observations

These observations are recorded for later stability review and are not current
blockers:

- client import had an approximately one-minute warm-up delay before browsing
  recovered and worked normally;
- the `socat` journal showed some `Broken pipe` / `Connection reset by peer`
  entries, while the service remained active, `23843/TCP` remained listening,
  and the client path was usable.

Future longer observation should decide whether these entries are normal client
churn or an abnormal high-frequency stability signal.

## Backlog And Next Decisions

### Stage 3.3.78 Route Promotion Decision

Purpose:

- decide whether `hk-socat-live-23843` should become a recommended candidate
  entry;
- require explicit user approval before any promotion step;
- avoid default cutover.

No promotion or cutover is approved by this document.

### Stage 3.3.79 Longer Stability Test Result

Purpose:

- record 30-minute, 1-hour, and 5-6-hour pre-live stability observations;
- track disconnects, exit region, service state, and `socat` journal patterns;
- keep the original direct node available during observation.

### Stage 3.3.80 Public Console HTTPS Reverse Proxy

Purpose:

- move public console access from HTTP to HTTPS;
- improve browser secure-context behavior and Clipboard API availability;
- review secure login cookie behavior;
- harden public management console access.

Stage 3.3.80 is a backlog item only. HTTPS reverse proxy work is not executed
in Stage 3.3.77f.

### Repository Privacy Reminder

The GitHub repository was temporarily made public for public VPS clone and
deployment work. After public deployment, clone, and testing stabilize, the
operator should review whether to switch the repository back to private.

## Safety Boundary

Stage 3.3.77f did not:

- perform cutover;
- mutate `nodes.share_link`;
- write `transit_routes.share_link`;
- read or export the full `nodes.share_link`;
- generate or record a full node link;
- create a Worker command;
- restart, stop, disable, or delete `socat`;
- modify Xray;
- modify firewall, cloud firewall, or cloud security group rules;
- execute SSH or remote commands;
- add a database migration;
- change backend or frontend code;
- deploy the public console;
- execute client tests.

## Result

Stage 3.3.77 candidate UI/export and Stage 3.3.77c manual copy fallback are
accepted as system-tested.

The remaining work should proceed through one of these explicit next stages:

- `Stage 3.3.78-route-promotion-decision`
- `Stage 3.3.79-longer-stability-test-result`
- `Stage 3.3.80-public-console-https-reverse-proxy`
