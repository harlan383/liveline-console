# Stage 2.7 Notes

Stage 2.7.1 implements only Xray backup-file read-only viewing and manual
restore instructions.

Implemented:

- `POST /api/vps/{vps_id}/xray-backups` creates a `list_xray_backups` task.
- The API requires an admin session, CSRF, `multipart/form-data`, and a fresh
  SSH Key upload or pasted SSH Key.
- SSH Key and Passphrase are encrypted into Redis temporary credentials and are
  deleted by the Worker after reading.
- RQ job arguments contain only `task_id`, `vps_id`, and `temp_credential_id`.
- The Worker scans `/usr/local/etc/xray/` for `config.json*` file metadata.
- Results are written to `tasks.result_data` and `task_logs`.
- The frontend shows backup file metadata and short manual restore instructions.

Read-only remote commands:

- `test -d /usr/local/etc/xray`
- `test -e /usr/local/etc/xray/config.json`
- `find /usr/local/etc/xray -maxdepth 1 -type f -name 'config.json*' -printf ...`
- `systemctl is-active xray`
- `ss -ltnH`

Displayed metadata:

- File name.
- Full path.
- File type: `current`, `backup`, `disabled`, `failed`, or `unknown`.
- File size.
- Modified time.
- Whether the current `config.json` exists.
- Whether `xray.service` is active.
- Whether port 443 is listening.

Security notes:

- Stage 2.7.1 does not read full `config.json` content.
- Stage 2.7.1 does not run `cat`, `head`, or `tail` on config files.
- Stage 2.7.1 does not download or upload backup files.
- Stage 2.7.1 does not return or print Reality privateKey.
- `task_logs` must not contain SSH private keys, Passphrase, Cookie, database
  connection strings, Reality privateKey, or full config content.
- Backup file metadata is stored only in `tasks.result_data`; no backup table or
  backup database fields are added.

Manual restore instructions:

- The frontend shows command templates only.
- The system does not execute restore commands in this stage.
- Restore commands require manual SSH execution by the operator.
- Restoring an old config may make an old client link usable again.
- Do not restore during a live stream.

Not implemented:

- No automatic restore.
- No backup deletion.
- No backup cleanup.
- No full config reading.
- No backend config download API.
- No database fields.
- No Alembic migration.
- No node creation.
- No node deletion.
- No node rebuild.
- No node refresh.
- No Xray restart, stop, or start.
- No Xray config modification.
- No IEPL / IPLC relay.
- No `dokodemo-door`.
- No iptables forwarding.
- No firewall modification or port opening.
- No 3x-ui installation or API calls.
- No subscription links.
- No traffic statistics.
- No automatic speed tests.
- No SSH daemon configuration changes.

## Stage 2.7.1 Freeze Conclusion

Stage 2.7.1 is frozen after real Xray backup-file read-only viewing acceptance.
This stage only provides backup-file metadata viewing and manual restore
instructions. It does not automatically restore config, delete backups, modify
remote files, restart Xray, or read full config contents.

Acceptance basis:

- Docker Compose had all 5 containers running.
- `/api/health` returned ok for backend, database, Redis, and Worker.
- `POST /api/vps/{vps_id}/xray-backups` was present in OpenAPI.
- Alembic current version remained `0003`.
- Redis `temp_credential:*` count was 0.
- Pending/running task count was 0.
- `npm audit` reported `found 0 vulnerabilities`.
- `GET /api/nodes` returned one active node: `direct-reality-recreated`.
- `GET /api/nodes/{id}` worked.
- The frontend showed the "Xray 备份文件" panel, "查看备份文件" button, and
  manual restore instructions.
- Task `a3f685c7-fb12-48cb-95ef-581ee5dcefd9` completed with
  `status=success`, `classification=list_xray_backups`, `listed=true`, and
  `failures=[]`.
- The backup list contained only metadata for:
  - `config.json`, `type=current`, `size=1054 B`
  - `config.json.bak.20260602070219`, `type=backup`, `size=1054 B`
  - `config.json.disabled.20260602070219`, `type=disabled`, `size=1054 B`
- Each file entry contained only `name`, `path`, `type`, `size_bytes`, and
  `modified_at`.
- Xray status was read as `config_exists=true`, `service_active=true`, and
  `port_443_listening=true`.
- Task logs contained the expected steps: `queued`, `load_credentials`,
  `list_xray_backups`, `check_config_dir`, `scan_backup_files`,
  `check_service`, `check_port`, `save_result`, and `complete`.
- Task logs had no `raw_output`, did not record raw `find -printf` output, and
  did not contain config file contents.
- The frontend showed the file table, current config existence, service active
  state, port 443 listening state, safety warning, and manual restore
  instructions.
- The frontend did not provide restore, delete, or download buttons.
- Remote no-change verification passed: no `cp`, `mv`, `rm`, `tee`, `sed`,
  `systemctl restart/stop/start`, or `xray run -test` was executed; no config
  or backup file was changed; Xray remained active and port 443 remained
  listening.
- Security checks passed: Redis temporary credentials were cleared; logs and
  result data did not expose SSH private keys, Passphrase, Cookie, database
  connection strings, Reality privateKey, or full config content; backup files
  were not downloaded or uploaded; backup contents were not written to the
  database.

Final allowed scope:

- Use SSH only to read `/usr/local/etc/xray/config.json*` file metadata.
- Display file name, path, size, modified time, and type.
- Classify files as `current`, `backup`, `disabled`, `failed`, or `unknown`.
- Display whether `config.json` exists.
- Display whether `xray.service` is active.
- Display whether port 443 is listening.
- Display manual restore instructions.
- Write results to `tasks.result_data`.
- Write task step logs.
- Delete Redis temporary credentials after the task reads them.

Final prohibited scope:

- Do not read full `config.json` content.
- Do not run `cat`, `head`, or `tail` on config files.
- Do not display Reality privateKey.
- Do not download backup files.
- Do not upload backup files.
- Do not restore config.
- Do not delete backup files.
- Do not clean backup files.
- Do not modify any remote file.
- Do not execute `cp`, `mv`, `rm`, `tee`, or `sed`.
- Do not restart, stop, or start Xray.
- Do not execute `systemctl restart`, `systemctl stop`, or `systemctl start`.
- Do not create nodes.
- Do not delete nodes.
- Do not rebuild nodes.
- Do not refresh node status.
- Do not modify Xray config.
- Do not configure relay.
- Do not configure `dokodemo-door`.
- Do not configure iptables.
- Do not modify firewall rules.
- Do not open ports.
- Do not call 3x-ui.
- Do not create subscription links.
- Do not add traffic statistics.
- Do not add automatic speed tests.
- Do not modify `sshd_config`.
- Do not add database fields.
- Do not add Alembic migrations.

## Stage 2.7.2.1 Backup Cleanup Preview

Stage 2.7.2.1 implements only Xray backup cleanup dry-run preview. It calculates
which backup files would be cleanup candidates under a conservative retention
policy, but it does not delete, move, copy, restore, download, upload, or modify
any remote file.

Implemented:

- `POST /api/vps/{vps_id}/xray-backups/cleanup-preview` creates a
  `preview_xray_backup_cleanup` task.
- The API requires an admin session, CSRF, `multipart/form-data`, and a fresh
  SSH Key upload or pasted SSH Key.
- SSH Key and Passphrase are encrypted into Redis temporary credentials and are
  deleted by the Worker after reading.
- RQ job arguments contain only `task_id`, `vps_id`, and `temp_credential_id`.
- Results are written to `tasks.result_data` and `task_logs`.
- The frontend adds a "清理预览" button inside the existing Xray backup panel.
- The frontend shows summary data, candidate files, retained files, and an
  explicit dry-run warning.

Dry-run policy:

- `keep_latest_per_type` is `3`.
- `dry_run` is `true`.
- `delete_enabled` is `false`.
- `config.json` is always retained with reason `current_config`.
- Unknown file types are always retained with reason `unknown_type`.
- `backup`, `disabled`, and `failed` files are grouped by type.
- The newest 3 files per cleanable type are retained with reason
  `within_keep_latest_3`.
- Older cleanable files become candidates with reason
  `older_than_keep_latest_3`.
- Risk levels are `failed=low`, `disabled=medium`, `backup=high`, and
  `current/unknown=protected`.

Read-only remote commands:

- `test -d /usr/local/etc/xray`
- `find /usr/local/etc/xray -maxdepth 1 -type f -name 'config.json*' -printf '%f|%p|%s|%T@\n'`
- `systemctl is-active xray`
- `ss -ltnH`

Result data:

- `classification=preview_xray_backup_cleanup`
- `previewed=true`
- `message=Xray 备份清理预览完成，本阶段未删除任何文件`
- `policy`
- `summary`
- `candidate_files`
- `retained_files`
- `xray`
- `warnings`
- `failures`

Security notes:

- Stage 2.7.2.1 does not read full `config.json` content.
- Stage 2.7.2.1 does not run `cat`, `head`, or `tail` on config files.
- Stage 2.7.2.1 does not execute `rm`, `mv`, `cp`, `tee`, or `sed`.
- Stage 2.7.2.1 does not restart, stop, or start Xray.
- Stage 2.7.2.1 does not expose Reality privateKey.
- `task_logs` must not contain SSH private keys, Passphrase, Cookie, database
  connection strings, Reality privateKey, full config content, or raw command
  output.
- No database fields or Alembic migrations are added.

Not implemented:

- No actual cleanup or deletion.
- No automatic restore.
- No backup download or upload.
- No config content display.
- No node creation, deletion, rebuild, refresh, or Xray restart.
- No relay, `dokodemo-door`, iptables forwarding, firewall changes, port
  opening, 3x-ui, subscription links, traffic statistics, automatic speed
  tests, or `sshd_config` changes.

## Stage 2.7.2.1 Freeze Conclusion

Stage 2.7.2.1 is frozen after real backup cleanup dry-run preview acceptance.
This stage only previews cleanup candidates for Xray backup files. It does not
delete backup files, modify remote files, restart Xray, restore config, read
full config contents, or add any real cleanup task/API.

Acceptance basis:

- Docker Compose had all 5 containers running.
- `/api/health` returned ok for backend, database, Redis, and Worker.
- `POST /api/vps/{vps_id}/xray-backups/cleanup-preview` was present in OpenAPI.
- Alembic current version remained `0003`.
- Redis `temp_credential:*` count was 0.
- Pending/running task count was 0.
- `npm audit` reported `found 0 vulnerabilities`.
- `GET /api/nodes` returned one active node: `direct-reality-recreated`.
- `GET /api/nodes/{id}` worked.
- The frontend showed the "清理预览" button and the "不会删除文件" warning.
- Task `88197478-a8fa-4bbf-8181-6e0d29d16084` completed with
  `status=success`, `classification=preview_xray_backup_cleanup`,
  `previewed=true`, and `failures=[]`.
- The task policy was `dry_run=true`, `delete_enabled=false`, and
  `keep_latest_per_type=3`.
- The task warnings included "本阶段仅预览，不会删除任何文件".
- Dry-run summary was correct: `total_files=3`, `retained_count=3`,
  `candidate_count=0`, `total_size_bytes=3162`, `candidate_size_bytes=0`, and
  `estimated_reclaim_bytes=0`.
- Retained files were correct:
  - `config.json`: `type=current`, `reason=current_config`,
    `risk_level=protected`
  - `config.json.bak.*`: `type=backup`, `reason=within_keep_latest_3`,
    `risk_level=high`
  - `config.json.disabled.*`: `type=disabled`,
    `reason=within_keep_latest_3`, `risk_level=medium`
- `candidate_files=[]`, matching the keep-latest-3 rule for the current file
  set.
- Task logs contained the expected steps: `queued`, `load_credentials`,
  `preview_xray_backup_cleanup`, `check_config_dir`, `scan_backup_files`,
  `calculate_cleanup_candidates`, `check_service`, `check_port`, `save_result`,
  and `complete`.
- Task logs had no `raw_output` and did not contain config file contents.
- The frontend showed total count, size, candidates, retained summary,
  candidate `reason` and `risk_level`, retained `reason`, and explicit warnings
  that this stage does not delete files or execute `rm`, `mv`, or `cp`.
- The frontend did not provide delete, batch delete, or automatic cleanup
  buttons.
- Remote no-change verification passed: no `rm`, `mv`, `cp`, `tee`, `sed`,
  `cat/head/tail`, `systemctl restart/stop/start`, or `xray run -test` was
  executed; `config.json` was unchanged; backup/disabled files remained; file
  count and modified times did not change; Xray remained active; port 443
  remained listening.
- Security checks passed: Redis temporary credentials were cleared; logs and
  result data did not expose SSH private keys, Passphrase, Cookie, database
  connection strings, Reality privateKey, full config contents, or backup file
  contents; backup files were not downloaded or uploaded; backup contents were
  not written to the database.
- No database fields or Alembic migrations were added.
- No `cleanup_xray_backups` real deletion task type or real deletion API was
  added.

Frozen dry-run rules:

- `current` is always retained with `risk_level=protected`.
- `unknown` is always retained with `risk_level=protected`.
- `backup`, `disabled`, and `failed` are grouped by type.
- The newest 3 files per cleanable type are retained.
- Older files beyond the retained count enter `candidate_files`.
- Candidate reason is `older_than_keep_latest_3`.
- Retained reasons are `current_config`, `unknown_type`, or
  `within_keep_latest_3`.
- Risk levels are `failed=low`, `disabled=medium`, and `backup=high`.
- This stage calculates only. It never deletes.

Final allowed scope:

- Scan backup file metadata.
- Calculate cleanup candidate files by policy.
- Return `retained_files`.
- Return `candidate_files`.
- Return `estimated_reclaim_bytes`.
- Return each file's `reason`.
- Return each file's `risk_level`.
- Show cleanup preview in the frontend.
- Write results to `tasks.result_data`.
- Write task step logs.
- Delete Redis temporary credentials after the task reads them.

Final prohibited scope:

- Do not actually delete backup files.
- Do not execute `rm`.
- Do not execute `mv`.
- Do not execute `cp`.
- Do not execute `tee`.
- Do not execute `sed`.
- Do not read full `config.json`.
- Do not run `cat`, `head`, or `tail` on config files.
- Do not restore config.
- Do not modify remote files.
- Do not restart, stop, or start Xray.
- Do not execute `systemctl restart`, `systemctl stop`, or `systemctl start`.
- Do not execute `xray run -test`.
- Do not create nodes.
- Do not delete nodes.
- Do not rebuild nodes.
- Do not refresh node status.
- Do not modify Xray config.
- Do not configure relay.
- Do not configure `dokodemo-door`.
- Do not configure iptables.
- Do not modify firewall rules.
- Do not open ports.
- Do not call 3x-ui.
- Do not create subscription links.
- Do not add traffic statistics.
- Do not add automatic speed tests.
- Do not modify `sshd_config`.
- Do not add database fields.
- Do not add Alembic migrations.
- Do not add a real deletion API.
- Do not add a `cleanup_xray_backups` real deletion task type.

## Stage 2.7.2.2-a Failed Candidate Delete

Stage 2.7.2.2-a implements only real deletion for one `failed` dry-run cleanup
candidate at a time. It does not delete current config, backup files, disabled
files, unknown files, retained files, directories, or multiple files.

Implemented:

- `POST /api/vps/{vps_id}/xray-backups/delete-candidate` creates a
  `delete_xray_backup_candidate` task.
- The API requires an admin session, CSRF, `multipart/form-data`, and a fresh
  SSH Key upload or pasted SSH Key.
- The request must include `filename`, `confirm=true`, and
  `confirm_filename=<filename>`.
- The only accepted filename pattern is
  `^config\.json\.failed\.\d{14}$`.
- SSH Key and Passphrase are encrypted into Redis temporary credentials and are
  deleted by the Worker after reading.
- RQ job arguments contain only `task_id`, `vps_id`, `temp_credential_id`,
  `filename`, `confirm`, and `confirm_filename`.
- The Worker reconnects over SSH, rescans backup metadata, recalculates dry-run
  candidates, confirms the file is still a `failed` candidate, deletes only that
  fixed path, and rescans to verify it no longer exists.
- Results are written to `tasks.result_data` and `task_logs`.
- The frontend shows a delete button only for `failed` candidate files.

Remote operation:

- Read-only pre-delete scan commands remain:
  - `test -d /usr/local/etc/xray`
  - `find /usr/local/etc/xray -maxdepth 1 -type f -name 'config.json*' -printf '%f|%p|%s|%T@\n'`
  - `systemctl is-active xray`
  - `ss -ltnH`
- The delete operation uses Paramiko SFTP `remove()` on the fixed path
  `/usr/local/etc/xray/<validated filename>`.
- No wildcard delete command is used.

Allowed scope:

- Delete one `config.json.failed.<14 digit timestamp>` file.
- Delete only when the file is still in recalculated `candidate_files`.
- Delete only after `confirm=true` and exact `confirm_filename` match.
- Verify deletion by rescanning metadata.
- Save file metadata, verification result, warnings, and failures in
  `tasks.result_data`.
- Write step logs.
- Delete Redis temporary credentials after reading.

Prohibited scope:

- Do not delete `config.json`.
- Do not delete `config.json.bak.*`.
- Do not delete `config.json.disabled.*`.
- Do not delete unknown file types.
- Do not delete retained files.
- Do not batch delete.
- Do not automatically clean.
- Do not use wildcards.
- Do not allow arbitrary paths or path traversal.
- Do not delete directories.
- Do not restore config.
- Do not modify Xray config content.
- Do not restart, stop, or start Xray.
- Do not create, delete, rebuild, or refresh nodes.
- Do not configure relay, `dokodemo-door`, iptables, firewall rules, port
  opening, 3x-ui, subscriptions, traffic statistics, speed tests, or
  `sshd_config`.
- Do not add database fields or Alembic migrations.

Safety notes:

- Full config contents are never read or returned.
- Reality privateKey must not enter result data, task logs, frontend state, or
  the database.
- `task_logs` must not contain SSH private keys, Passphrase, Cookie, database
  connection strings, full config content, or raw command output.
- Real deletion is irreversible; the UI requires exact filename confirmation
  and two explicit acknowledgment checkboxes.

## Stage 2.7.2.2-a Freeze Conclusion

Stage 2.7.2.2-a is frozen after real single failed-candidate deletion
acceptance. This stage only deletes one `config.json.failed.<14 digit
timestamp>` file when it is still present in recalculated dry-run
`candidate_files`. It does not delete current config, backup files, disabled
files, unknown files, retained files, directories, or multiple files.

Acceptance basis:

- Docker Compose had all 5 containers running.
- `/api/health` returned ok for backend, database, Redis, and Worker.
- `POST /api/vps/{vps_id}/xray-backups/delete-candidate` was present in
  OpenAPI.
- No restore API, batch delete API, or automatic cleanup API was added.
- Alembic current version remained `0003`.
- Redis `temp_credential:*` count was 0.
- Pending/running task count was 0.
- `npm audit` reported `found 0 vulnerabilities`.
- `GET /api/nodes` returned one active node: `direct-reality-recreated`.
- VPS verification showed `config.json` existed, `xray.service` was active, and
  port 443 was listening.
- Acceptance preparation created four zero-byte failed test files:
  - `config.json.failed.20000101000000`
  - `config.json.failed.20000102000000`
  - `config.json.failed.20000103000000`
  - `config.json.failed.20000104000000`
- `cleanup-preview` produced exactly one candidate:
  `config.json.failed.20000101000000`.
- Task `f5286832-4a7e-438f-8ab6-90caed413685` completed with
  `status=success`, `classification=delete_xray_backup_candidate`,
  `deleted=true`, and `failures=[]`.
- The deleted file was `config.json.failed.20000101000000`, with
  `type=failed`, `risk_level=low`, `reason=older_than_keep_latest_3`, and
  `verify.file_exists_after_delete=false`.
- Task logs contained the expected steps: `queued`, `load_credentials`,
  `delete_xray_backup_candidate`, `validate_request`, `scan_backup_files`,
  `calculate_cleanup_candidates`, `validate_candidate`, `delete_file`,
  `verify_deleted`, `save_result`, and `complete`.
- Task logs had no `raw_output`, did not contain config contents, and did not
  expose SSH Key, Passphrase, Cookie, database connection strings, or Reality
  privateKey.
- VPS verification showed the target failed file was deleted; `config.json`,
  `config.json.bak.*`, and `config.json.disabled.*` remained; other non-target
  failed test files remained until acceptance cleanup; Xray stayed active; port
  443 stayed listening; the active node was not affected.
- Failure protections passed at the API layer: mismatched `confirm_filename`
  returned `FILENAME_MISMATCH`; `config.json`, `config.json.bak.*`,
  `config.json.disabled.*`, filenames containing `../`, `/`, or spaces all
  returned `INVALID_FILENAME`; no Worker task was reached and no file was
  deleted.
- Security checks passed: Redis temporary credentials were cleared; logs and
  result data did not expose SSH private keys, Passphrase, Cookie, database
  connection strings, Reality privateKey, or config contents; no privateKey
  database field was added.
- Out-of-scope checks passed: no current/backup/disabled/unknown/retained file
  deletion, no batch deletion, no automatic cleanup, no wildcard deletion, no
  arbitrary path deletion, no path traversal, no directory deletion, no config
  restore, no Xray config modification, no Xray restart/stop, no node changes,
  no relay, no `dokodemo-door`, no iptables, no firewall changes, no port
  opening, no 3x-ui, no subscriptions, no traffic statistics, no speed tests, no
  `sshd_config` change, no database fields, no Alembic migration, no
  `cleanup_xray_backups`, no restore task, no batch delete task, and no wildcard
  deletion logs.

Frozen filename validation rules:

- `filename` must match `^config\.json\.failed\.\d{14}$`.
- `confirm_filename` must exactly equal `filename`.
- `filename` must not contain `/`.
- `filename` must not contain `..`.
- `filename` must not contain whitespace.
- `filename` must not contain shell special characters.
- Arbitrary paths are forbidden.
- Wildcards are forbidden.
- Batch filenames are forbidden.

Final allowed scope:

- Delete a single `failed` file that appears in recalculated dry-run
  `candidate_files`.
- Require `config.json.failed.<14 digit timestamp>` filename format.
- Require `confirm=true`.
- Require exact `confirm_filename` match.
- Rescan before deletion.
- Recalculate `candidate_files` before deletion.
- Confirm the target is still a `failed` candidate.
- Confirm the target is not a retained file.
- Confirm fixed directory and fixed filename.
- Delete the fixed path through Paramiko SFTP `remove()`.
- Rescan after deletion and confirm the file no longer exists.
- Write results to `tasks.result_data`.
- Write task step logs.
- Delete Redis temporary credentials after reading.

Final prohibited scope:

- Do not delete `config.json`.
- Do not delete `config.json.bak.*`.
- Do not delete `config.json.disabled.*`.
- Do not delete unknown file types.
- Do not delete retained files.
- Do not batch delete.
- Do not automatically clean.
- Do not use wildcards.
- Do not allow arbitrary paths.
- Do not allow path traversal.
- Do not delete directories.
- Do not restore config.
- Do not modify Xray config content.
- Do not restart Xray.
- Do not stop Xray.
- Do not create nodes.
- Do not delete nodes.
- Do not rebuild nodes.
- Do not refresh node status.
- Do not configure relay.
- Do not configure `dokodemo-door`.
- Do not configure iptables.
- Do not modify firewall rules.
- Do not open ports.
- Do not call 3x-ui.
- Do not create subscription links.
- Do not add traffic statistics.
- Do not add automatic speed tests.
- Do not modify `sshd_config`.
- Do not add database fields.
- Do not add Alembic migrations.
- Do not add `cleanup_xray_backups`.
- Do not add restore tasks.
- Do not add batch delete tasks.
