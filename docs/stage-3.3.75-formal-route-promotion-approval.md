# Stage 3.3.75 Formal Route Promotion Approval

## Stage Goal

Stage 3.3.75 creates the formal route promotion approval packet for the Hong
Kong `socat` `23843/TCP` candidate path.

This stage is approval documentation only. It does not perform cutover, mutate
`nodes.share_link`, export or generate a full node link, modify Xray, restart or
stop the transit service, create a Worker command, add listeners, change
firewall rules, or execute SSH / remote commands.

## Current Promotion Candidate

The candidate route selected for a future promotion discussion is:

| Field | Value |
| --- | --- |
| route id | `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af` |
| route name | `hk-socat-live-23843` |
| transit entry | `163.223.216.108:23843` |
| forwarding target | `64.90.13.19:27939` |
| forwarding method | `socat` |
| service | `liveline-socat-23843.service` |
| service status | `active / enabled` |
| database route status | `active` |
| route share_link | `NULL / empty` |

The candidate path is:

```text
163.223.216.108:23843 -> 64.90.13.19:27939
```

## Client Candidate Validation

Stage 3.3.74c recorded that client-side candidate validation passed:

- The operator manually copied the original landing Reality node.
- Only the client server / address was changed to `163.223.216.108`.
- Only the client port was changed to `23843`.
- Other Reality, transport, security, flow, network, fingerprint, and client
  parameters were left unchanged and are not reproduced in this document.
- The test node `hk-socat-live-23843-test` could open normal web pages.
- `ipinfo.io` / `ip.sb` showed the exit as the landing VPS
  `64.90.13.19` or the expected landing region.
- Continuous use for roughly 3 to 5 minutes did not show frequent disconnects.
- The original direct node remains retained.

## Required Confirmation Before Formal Promotion

Before any later formal promotion or cutover design stage, the operator must
confirm all of the following again:

- Hong Kong transit `23843/TCP` is still listening.
- `liveline-socat-23843.service` is still `active / enabled`.
- `transit_routes` route `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af` is still
  `active`.
- The client candidate node can still open normal web pages.
- The observed exit is still the landing VPS / landing region.
- The original direct node is still usable.
- The user explicitly approves the next formal promotion / cutover planning
  step.

## No-Go Conditions

Formal promotion must remain No-Go if any of the following are true:

- `23843/TCP` is not reachable.
- `liveline-socat-23843.service` is not active.
- The route is not active in `transit_routes`.
- The client candidate node cannot open normal web pages.
- The observed exit is not the landing VPS / landing region.
- The original direct node is abnormal.
- The user has not explicitly approved the next stage.
- A future step would need to modify `nodes.share_link` without separate,
  explicit authorization.
- Any secret, token, full node link, private key, database password, or other
  sensitive material is at risk of being exposed.

## Rollback Principles

The rollback and safety principles for later promotion work are:

- The original direct node must be retained.
- If promotion fails, clients should manually switch back to the original direct
  node.
- The Hong Kong transit route must not be deleted automatically.
- `liveline-socat-23843.service` must not be stopped automatically.
- Database links must not be rewritten automatically.
- Cutover must not happen automatically.

## Required Approval Phrase For Next Stage

To proceed into a later formal route promotion design stage, the user must
confirm the following phrase exactly:

```text
批准执行正式 route promotion：将 hk-socat-live-23843 作为客户端推荐中转候选；不删除原直连节点；不修改 nodes.share_link；不生成完整节点链接；不自动 cutover。
```

This approval phrase does not authorize automatic `nodes.share_link` mutation.
It only authorizes entering the next stage to design the route promotion plan.

## Stage Boundary

Stage 3.3.75 did not:

- perform cutover
- modify `nodes.share_link`
- read or export full `nodes.share_link`
- generate a full node link
- modify Xray
- modify landing node configuration
- restart, stop, disable, or delete `liveline-socat-23843.service`
- create a Worker command
- add a listener
- modify firewall, cloud firewall, or cloud security group rules
- execute SSH or remote commands

## Next Stage Recommendation

Proceed to `Stage 3.3.75b-route-promotion-implementation-plan` only after the
required approval phrase is provided.

If the operator does not want to proceed, keep using the candidate as a manual
test node and leave the original direct node unchanged.
