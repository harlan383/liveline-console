# Stage 3.3.76 Longer Stability Observation

## Stage Goal

Stage 3.3.76 establishes a longer stability observation plan for the validated
Hong Kong `socat` `23843/TCP` candidate route before any future promotion
decision.

This stage is observation planning only. It does not perform cutover, mutate
`nodes.share_link`, read or export full `nodes.share_link`, generate a full node
link, create Worker commands, restart or stop `socat`, modify Xray, change
firewall rules, add database migrations, or execute SSH / remote commands.

## Current Candidate State

The current candidate route has already passed short client validation:

| Field | Value |
| --- | --- |
| route id | `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af` |
| route name | `hk-socat-live-23843` |
| transit entry | `163.223.216.108:23843` |
| forwarding target | `64.90.13.19:27939` |
| forwarding method | `socat` |
| service | `liveline-socat-23843.service` |
| route status | `active` |
| client test node | `hk-socat-live-23843-test` |
| client browsing | `passed` |
| exit IP / region | landing VPS / landing region |
| short stability | 3 to 5 minutes passed |
| route share_link | `NULL / empty` |
| cutover status | `not performed` |

## Observation Plan

The recommended longer observation path is:

1. Run a 30-minute ordinary browsing / video observation window.
2. Run a 1-hour live-stream or push-stream simulation observation window.
3. Before any real live event, run one additional 5 to 6 hour long observation
   window if operationally feasible.

These observation windows should use the manually prepared candidate client
profile and should not require any database mutation or link rewrite.

## Observation Metrics

During each observation window, record:

- whether the client disconnects or stalls frequently
- whether the exit IP / region remains stable as the landing VPS / landing
  region
- whether normal web pages, video playback, and platform access remain healthy
- whether `liveline-socat-23843.service` remains active
- whether there are active client connections to `23843/TCP`
- whether `journalctl` for `liveline-socat-23843.service` shows excessive
  `Broken pipe`, `reset`, or similar connection errors

Operational checks such as `systemctl status`, `ss -antp`, and `journalctl`
should be run only in a separately authorized validation stage. This document
records what to observe, not permission to execute remote commands.

## Go Conditions

The candidate can remain eligible for a later promotion discussion only if all
of the following hold:

- 30 minutes of ordinary browsing / video use shows no obvious disconnects.
- 1 hour of live-stream or push-stream simulation shows no obvious disconnects.
- `liveline-socat-23843.service` remains continuously active.
- The observed exit region remains stable as the landing VPS / landing region.
- The original direct node remains usable.

## No-Go Conditions

Promotion must remain No-Go if any of the following occur:

- frequent client disconnects or stalls
- abnormal exit IP / region
- `liveline-socat-23843.service` restarts, fails, or becomes inactive
- `23843/TCP` is not listening
- the original direct node becomes abnormal
- any future step requires `nodes.share_link` mutation without separate
  explicit approval
- any full node link, secret, token, private key, database password, or provider
  credential is at risk of being exposed

## Stage Boundary

Stage 3.3.76 did not:

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

Proceed to `Stage 3.3.76b-stability-observation-result-record` after completing
the longer observation windows.

Alternatively, proceed to `Stage 3.3.75c-route-promotion-ui-design` if the
operator wants to design the non-cutover promotion UI while longer stability
observation continues.
