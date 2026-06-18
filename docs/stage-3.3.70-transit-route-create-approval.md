# Stage 3.3.70 Transit Route Create Approval

## Stage Goal

Record the formal approval packet before creating a real transit route from the
Hong Kong transit server to the accepted landing Reality node.

This stage is documentation only. It does not create the transit route and does
not execute any Worker command.

## Preceding Validation

Stage 3.3.68-hotfix-14 has passed production validation. The Hong Kong transit
Worker is running `0.1.16-stage-3.3.68`, and compact readonly preflight result
submission is working.

The real UI-triggered readonly preflight succeeded:

| Field | Result |
| --- | --- |
| command id | `50055a0a-8bd1-416b-84ce-c101df4c2cd7` |
| command type | `transit_readonly_preflight` |
| status | `succeeded` |
| attempts | `1` |
| result status | `passed` |
| Worker version | `0.1.16-stage-3.3.68` |
| checks count | `6` |
| failed check names | `[]` |
| summary | `Remote readonly preflight passed for planned listen 23843 to landing target port 27939.` |

The controlled command-line compact validation also succeeded:

| Field | Result |
| --- | --- |
| command id | `bbbbbbbb-cccc-dddd-eeee-ffffffffffff` |
| status | `succeeded` |
| result status | `passed` |
| Worker version | `0.1.16-stage-3.3.68` |

Compact result evidence:

| Field | Result |
| --- | --- |
| original submit payload size | `2306` |
| compact submit payload size | `622` |
| compact applied | `true` |
| submitted body size | `622` |
| response status | `200` |

## Proposed Transit Route

The following values are recorded only as approval inputs. They are not applied
by this stage.

### Transit Server

| Field | Value |
| --- | --- |
| transit resource id | `1e222459-9fa2-4c62-800f-a3b35edb7df8` |
| transit resource name | `香港中转服务器` |
| server IP | `163.223.216.108` |
| hostname | `WEPC202605221223335` |
| interface name | `eth0` |

### Landing Node

| Field | Value |
| --- | --- |
| landing node id | `a71472c6-f62c-43b5-a223-9f5f070ae4ef` |
| landing node name | `liveline-reality-27939` |
| landing target host | `64.90.13.19` |
| landing target port | `27939` |

### Planned Listener

| Field | Value |
| --- | --- |
| planned listen port | `23843` |
| protocol | `TCP` |
| forwarding method | `socat` |
| purpose | `直播` |

## Execution Boundary

This approval record does not:

- execute SSH or remote commands,
- deploy the public console,
- upgrade the Worker,
- trigger a Worker command,
- create a transit route,
- add or bind a listening port,
- modify firewall, cloud firewall, or cloud security group rules,
- install, start, stop, or restart `socat` / `gost`,
- modify Xray,
- read or modify `nodes.share_link`,
- generate or display a real client link,
- perform cutover.

## Required Manual Confirmation Before Execution

Before any future execution stage, the operator must explicitly confirm:

- Hong Kong transit server cloud security group allows `23843/TCP`.
- Hong Kong transit server cloud firewall allows `23843/TCP`.
- Hong Kong transit server local firewall allows `23843/TCP`, or no blocking
  rule is present.
- `23843/TCP` is still not occupied on the transit server.
- `64.90.13.19:27939` is still TCP reachable from the Hong Kong transit server.
- Complete node links remain hidden and must not be pasted into chat, PRs,
  docs, terminal logs, or screenshots.
- `nodes.share_link` must not be read or modified by the approval stage.
- The future transit route creation stage is not a cutover.

## Not A Real Creation Stage

This stage records that the readonly preflight passed and that the proposed
route is ready for a separate execution approval. It does not install or start
`socat`, does not create a service, does not bind `23843/TCP`, and does not
write any transit route execution result.

## Next Stage Suggestion

The next possible stage is:

`Stage 3.3.71-transit-route-create-execution`

That stage must require a fresh, explicit user authorization before any real
Worker command, service creation, listener binding, route persistence, or
follow-up verification is allowed.
