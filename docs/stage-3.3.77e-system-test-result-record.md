# Stage 3.3.77e System Test Result Record

## Stage Goal

Stage 3.3.77e records the system test results for Stage 3.3.77 and
Stage 3.3.77c. This stage is documentation-only.

No production action was executed in this stage.

## Deployment State Verified

The public console has been deployed with main that includes:

- Stage 3.3.77 transit candidate UI and transient export.
- Stage 3.3.77c HTTP-safe manual copy fallback.

The system test confirmed:

- frontend was rebuilt and recreated;
- backend health check was normal;
- frontend returned HTTP 200;
- `中转链路` displayed the `hk-socat-live-23843` candidate panel.

## Candidate UI Verification

The candidate panel showed the expected route context:

- route name: `hk-socat-live-23843`
- candidate name after export: `hk-socat-live-23843-test`
- server: `163.223.216.108`
- port: `23843`
- target: `64.90.13.19:27939`
- service: `liveline-socat-23843.service`
- cutover status: not cut over
- route share-link status: not written / NULL

The candidate summary action worked and did not display a full node link.

## Transient Export Verification

The transient export action completed successfully after the required
confirmations.

The export result showed:

- candidate name: `hk-socat-live-23843-test`
- server: `163.223.216.108`
- port: `23843`
- masked link displayed normally

The full candidate link was not recorded in this document, README, logs, or PR
text.

## HTTP Manual Copy Fallback Verification

The public console is currently accessed over HTTP. In that context, Chrome did
not expose the Clipboard API.

Stage 3.3.77c behavior was verified:

- automatic copy did not falsely report success;
- the page showed the manual-copy textarea fallback;
- the manual-copy prompt made clear that the candidate link is for temporary
  client import testing only;
- the UI continued to state that no `nodes.share_link` mutation and no cutover
  occurred.

## Client Import Verification

After manually copying the transient candidate link into the client:

- the candidate node could browse normally;
- the exit remained the landing VPS / landing region;
- `hk-socat-live-23843-test` became usable after a short warm-up period.

Known observation:

- the client could not browse for about one minute immediately after import,
  then recovered and worked normally. This is recorded as a warm-up delay and
  is not considered a blocker for this result record.

## Database Verification

The system test confirmed:

- `transit_routes.share_link` for route
  `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af` remained NULL / empty;
- the original landing node `nodes.share_link` still existed;
- the original landing node share-link length remained `250`;
- the original landing node share-link was not rewritten.

Only presence and length were checked for the node share link. The full
`nodes.share_link` value was not selected, printed, copied into docs, or
otherwise recorded.

## Transit Service Verification

The existing transit service remained healthy:

- `liveline-socat-23843.service` remained active;
- `23843/TCP` remained listening;
- the candidate route remained usable from the client.

Known observation:

- the `socat` journal showed some `Broken pipe` / `Connection reset by peer`
  entries. The service remained active and the client was usable, so this is
  recorded as an observation item for later longer stability testing.

## Safety Boundary

Stage 3.3.77e did not:

- perform cutover;
- mutate `nodes.share_link`;
- write `transit_routes.share_link`;
- generate or record a full node link;
- create a Worker command;
- restart, stop, disable, or delete `socat`;
- modify Xray;
- modify firewall, cloud firewall, or cloud security group rules;
- execute SSH or remote commands;
- add a database migration;
- change backend or frontend code.

## Result

Stage 3.3.77 / 3.3.77c system testing is accepted for the candidate UI,
transient export, and HTTP manual-copy fallback.

The route is still not cut over. The candidate remains a manually imported test
candidate, and the original direct node remains retained.

## Next Stage Recommendation

Suggested next stage:

- `Stage 3.3.78-route-promotion-decision`

Alternative:

- continue longer candidate observation before any promotion decision.
