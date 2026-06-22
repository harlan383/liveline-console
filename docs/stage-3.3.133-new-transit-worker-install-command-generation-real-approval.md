# Stage 3.3.133 New Transit Worker Install Command Generation Real Approval

## Stage Goal

Stage 3.3.133 adds the final approval gate before any future real one-time
Transit Worker token and install command generation.

Stage 3.3.132 already added the no-real-VPS dry-run view. This stage assumes a
real test VPS may be used later, but it is still an approval-only stage. It does
not generate a Worker token, does not generate a real install command, does not
install Worker, does not create Worker command, and does not execute SSH or any
remote command.

## Implemented UI/API Changes

UI changes:

- Added a `真实生成命令最终审批` section below the Stage 3.3.132 dry-run result.
- The final approval section is shown only when:
  - the resource status is `pending_worker`
  - the Stage 3.3.131 typed confirmation is correct
  - the dry-run area is visible
- The section displays resource identity, SSH metadata, public controller URL,
  target Worker version, Worker binary checksum, and explicit `not_generated`
  / `仍未执行` statuses.
- Added the stricter typed confirmation:
  `CONFIRM_REAL_WORKER_INSTALL_COMMAND_GENERATION_NEXT_STAGE`
- Added a copy action for the final approval package.

API changes:

- None. This stage intentionally avoids backend changes.
- No token/bootstrap endpoint is called.
- No Worker command endpoint is called.
- No remote execution endpoint is called.

## Real VPS Testing Context

The UI now records the readiness checks needed before a later stage can generate
a real one-time Worker token and install command:

- test VPS exists
- public VPS IP / domain is confirmed
- SSH host / port / username are confirmed
- root or sudo access is confirmed
- systemd is confirmed
- curl is confirmed
- the VPS can access `http://my-con.golirong.xyz:8200`
- any install command must use the public controller URL
- localhost and 127.0.0.1 are forbidden
- a real token must not be stored in docs, README, PR, logs, chat, or notes
- real installation must still be performed only in a later independent stage

## Final Approval Gate Behavior

Before the final typed confirmation is entered, the UI says:

`尚未确认进入真实命令生成阶段。`

After the operator enters the required phrase, the UI says:

`最终审批门已通过。下一阶段才允许在明确授权下生成一次性 Worker token / install command。`

Even after that confirmation, this stage still does not generate a Worker token,
does not generate a real install command, does not install Worker, does not SSH,
and does not create Worker command.

## Final Approval Package

The copied package contains:

- resource name, status, entry host, SSH summary, regions, planned interface,
  and protocol intent
- required Worker version: `0.1.24-stage-3.3.122`
- Worker binary checksum:
  `cf7990f3ba0f85348fa714edb69a94d36b8752323fe9c843fa676cf50f38fcce`
- public controller URL: `http://my-con.golirong.xyz:8200`
- real VPS readiness checklist
- typed confirmation requirement:
  `CONFIRM_REAL_WORKER_INSTALL_COMMAND_GENERATION_NEXT_STAGE`
- token status: `not_generated`
- install command status: `not_generated`
- remote execution: `disabled`
- next-stage requirement

The package does not contain a real Worker token or a real install command.

## Safety Boundary

This stage did not:

- deploy the public controller
- generate Worker token
- generate a real Worker install command
- install Worker
- execute SSH or any remote command
- create Worker command
- create a HAProxy route
- install HAProxy
- stop, restart, or delete socat
- modify Xray
- modify firewall, cloud security group, or cloud firewall
- cutover
- read, print, or record full `nodes.share_link`
- write `transit_routes.share_link`
- output full VLESS/V2Ray links
- fake Worker online state
- fake HAProxy readiness
- fake route availability

## Validation

Local validation for this PR:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- frontend production build
- Docker-based frontend build was unavailable because the Docker daemon was not
  running, so the frontend build was run through the local bundled Node runtime
- sensitive information scan for real tokens, SSH private keys, database
  passwords, full candidate links, full node links, and real `nodes.share_link`
  values

## Next Recommended Stage

Stage 3.3.134-new-transit-worker-install-command-generation-execution

In that later stage, if the user explicitly approves, a one-time Worker token
and install command may be generated. That next stage still must not
automatically SSH into or install Worker on a VPS unless a separate installation
execution stage is explicitly approved.
