# Stage 3.3.74c Client Candidate Success Record

## Stage Goal

Stage 3.3.74c records client-side validation evidence for the Hong Kong
`socat` `23843/TCP` candidate transit route.

This stage is evidence-only. It does not execute production commands, deploy the
console, upgrade Workers, trigger Worker commands, restart services, change
firewall rules, modify Xray, read or modify `nodes.share_link`, generate full
node links, delete nodes, or perform cutover.

## Candidate Route Under Validation

| Field | Value |
| --- | --- |
| candidate name | `hk-socat-live-23843-test` |
| transit service | `liveline-socat-23843.service` |
| transit listener | `163.223.216.108:23843` |
| forwarding method | `socat` |
| landing target | `64.90.13.19:27939` |
| route id | `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af` |
| route status | `active` |
| route share_link | `NULL / empty` |

## Client Validation Evidence

The candidate was validated through client import as a test candidate. The
client-side result was:

- `hk-socat-live-23843-test` can open normal web pages.
- `ipinfo.io` / `ip.sb` show the exit IP as the landing VPS
  `64.90.13.19` or the expected landing region.
- Continuous use for roughly 3 to 5 minutes did not show frequent disconnects.
- Hong Kong transit host `ss` output previously showed the client public IP
  connected to `163.223.216.108:23843`.

## Service And Route Evidence

The transit service and database route remained in the expected active state:

- `liveline-socat-23843.service` is active.
- `liveline-socat-23843.service` is enabled.
- `transit_routes` route `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af` is active.
- `share_link` remains `NULL / empty`.

## Security Notes

- No full client link is recorded in this document.
- No secret, token, SSH private key, database password, or provider credential is
  recorded in this document.
- `nodes.share_link` was not read or modified by this record stage.
- No full node link was generated or displayed by this record stage.
- The original direct node was not deleted.
- This is a candidate connectivity success record, not a cutover record.

## Stage Boundary

Stage 3.3.74c did not:

- perform cutover
- modify `nodes.share_link`
- generate a full node link
- delete the original direct node
- modify Xray
- restart `liveline-socat-23843.service`
- stop, disable, or delete the service
- modify firewall, cloud firewall, or cloud security group rules
- trigger a Worker command
- execute SSH or remote commands

## Current Conclusion

The Hong Kong `socat` `23843/TCP` candidate transit route passed client-side
candidate validation: browsing works, the observed exit remains the landing
region, short continuous use was stable, and the route/service remained active.

The current state remains candidate validation. No cutover has been performed.

## Next Stage Recommendation

Proceed to a separate approval stage before any formal cutover or route
promotion discussion.
