# Stage 3.3.73h Production Success Record

## Stage Goal

Stage 3.3.73h records the successful production execution result for the
approved Hong Kong `socat` transit route.

This stage is evidence-only. It does not execute production commands, deploy the
console, upgrade Workers, create new commands, restart services, change
firewall rules, modify Xray, read or modify `nodes.share_link`, generate client
links, or perform cutover.

## Production Execution Result

Stage 3.3.73g completed the approved real-create execution for the Hong Kong
transit route.

Worker command result:

| Field | Value |
| --- | --- |
| command id | `e615ea29-07ca-463b-bf50-b73daf13ab80` |
| command type | `transit_route_create` |
| status | `succeeded` |
| worker id | `f2e16197-e953-46dd-90af-66f64759a2a9` |
| server type | `transit` |
| server id | `1e222459-9fa2-4c62-800f-a3b35edb7df8` |
| attempts | `1` |
| claimed at | `2026-06-18 17:00:40+00` |
| completed at | `2026-06-18 17:00:41+00` |
| error message | empty |

## Route Record

The `transit_routes` record was created successfully.

| Field | Value |
| --- | --- |
| route id | `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af` |
| name | `hk-socat-live-23843` |
| listen port | `23843` |
| target host | `64.90.13.19` |
| target port | `27939` |
| forwarding method | `socat` |
| service name | `liveline-socat-23843.service` |
| service path | `/etc/systemd/system/liveline-socat-23843.service` |
| status | `active` |
| share link | `NULL / empty` |
| created at | `2026-06-18 17:00:41+00` |

The route record does not contain a generated or exported client link.
`share_link` remains empty.

## Systemd Acceptance

Hong Kong transit host service acceptance:

| Field | Value |
| --- | --- |
| service | `liveline-socat-23843.service` |
| loaded state | loaded / enabled |
| active state | active / running |
| main PID | `944691` |
| ExecStart | `/usr/bin/socat TCP-LISTEN:23843,fork,reuseaddr TCP:64.90.13.19:27939` |

## Listener Acceptance

Hong Kong transit host listener acceptance:

| Field | Value |
| --- | --- |
| listen address | `0.0.0.0:23843` |
| protocol | TCP |
| state | LISTEN |
| process | `socat` |
| PID | `944691` |

## Security Notes

- No full client link is recorded in this document.
- No secret, token, SSH private key, database password, or provider credential is
  recorded in this document.
- `nodes.share_link` was not read or modified by this record stage.
- No full node link was generated or displayed by this record stage.
- `transit_routes.share_link` remains `NULL / empty`.
- The route is active, but this is not a cutover record.

## Stage Boundary

Stage 3.3.73h did not:

- trigger `worker-create-execute`
- create a new Worker command
- modify the existing route
- restart `liveline-socat-23843.service`
- stop, disable, or delete the service
- modify firewall, cloud firewall, or cloud security group rules
- modify Xray
- read or modify `nodes.share_link`
- generate a complete client link
- perform cutover
- execute SSH or remote commands

## Current Conclusion

The approved Hong Kong `socat` `23843/TCP` transit route has been created and
verified as active. The database route is active, the systemd service is active,
and the listener is present on `23843/TCP`.

The current state is a candidate transit route validation state, not a formal
cutover.

## Next Stage Recommendation

Proceed to:

```text
Stage 3.3.74-client-candidate-connectivity-validation
```

That next stage should validate client connectivity through the candidate
transit route before any cutover discussion.
