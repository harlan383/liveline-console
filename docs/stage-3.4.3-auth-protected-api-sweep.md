# Stage 3.4.3 Auth Protected API Sweep

## Stage Goal

Stage 3.4.3 reviews the backend API authentication boundary after the Stage
3.4.1 login gate and Stage 3.4.2 local browser acceptance. The goal is to make
sure important backend APIs cannot be called by unauthenticated users who bypass
the frontend.

This stage is an Auth security review stage. It does not modify the production
link state and does not perform any network cutover action.

## Route Review Summary

The backend route modules under `backend/app/api/routes/` were reviewed:

- `health.py`
- `auth.py`
- `admin.py`
- `nodes.py`
- `vps.py`
- `tasks.py`
- `transit_resources.py`
- `transit_routes.py`

Important data APIs already reuse the existing `require_admin_session`
dependency from `backend/app/api/deps.py`. No backend route code change was
required for this sweep.

## Public Interfaces

| Interface | Status | Notes |
| --- | --- | --- |
| `GET /api/health` | Public | Health check only. |
| `POST /api/auth/login` | Public | Authenticates the admin and creates an HttpOnly session. |
| `POST /api/auth/logout` | Public callable | Revokes a session when present and clears the cookie when absent. |
| `GET /api/auth/me` | Public callable | Returns `401` when unauthenticated. |
| `GET /api/auth/csrf` | Session required | Returns `401` when unauthenticated. |
| `POST /api/admin/init` | Bootstrap exception | Protected by init token / one-time admin initialization rules; it does not expose system data. |

## Protected Interfaces

The following API groups must require login and were confirmed to use the
existing admin session dependency:

| API group | Protected scope |
| --- | --- |
| `/api/nodes` | Node list, node detail, node creation, refresh, restart, delete, and SSH-backed node tasks. |
| `/api/vps` | Host-key confirmation and Xray backup read / preview / delete-candidate task entry points. |
| `/api/tasks` | Task detail and task logs. |
| `/api/transit-resources` | Transit resource list, detail, create, edit, enable, disable, and SSH-backed resource tasks. |
| `/api/transit-routes` | Transit route list, detail, create, diagnose, and restart-socat task entry points. |

Unauthenticated access to protected APIs must return `401`.

## Frontend 401 Behavior

`frontend/lib/api.ts` already dispatches the `livelines:auth-expired` event when
a protected API returns `401`. `AppShell` listens for that event and returns the
operator to the login screen with an expired-login message.

The auth endpoints themselves are excluded from the global 401 event to avoid a
login loop.

## Local Acceptance Results

| Check | Result |
| --- | --- |
| `GET /api/health` without login | `200` |
| `GET /api/nodes` without login | `401` |
| `POST /api/vps/<id>/xray-backups` without login | `401` |
| `GET /api/tasks/<id>` without login | `401` |
| `GET /api/transit-routes` without login | `401` |
| `GET /api/transit-resources` without login | `401` |
| `POST /api/auth/login` with wrong password | `401` |
| `GET /api/auth/me` without login | `401` |
| `POST /api/auth/logout` without login | `200`, clears cookie |
| Redis `temp_credential:*` after sweep | `0` |
| Pending / running tasks after sweep | `0` |

Authenticated browser acceptance was already recorded in Stage 3.4.2: correct
credentials enter the system panel, refresh keeps the session, logout returns
to the login page, and the system panel is hidden after logout. The real admin
password was not entered into terminal commands for this sweep.

## Modified Files

- `README.md`
- `docs/stage-3.4.3-auth-protected-api-sweep.md`

No backend code change was required because the protected API dependency was
already present on the reviewed data routes.

## Production Link Boundary

- The formal production link remains `socat` 18443.
- The fallback link remains `gost` 8443.
- `node.share_link` was not read, printed, or modified.
- No full node link was written to documents, logs, task results, or Git.
- No listening port was added.
- No firewall rule was modified.
- No SSH or remote command was executed.
- No backend task was triggered.
- No cutover was performed.
- `socat` did not take over 8443.
- `gost` 8443 was not closed, stopped, disabled, downgraded, or replaced.

## Stage Result

Stage 3.4.3 confirms that the important backend data APIs are guarded by the
existing admin session dependency and return `401` when accessed without login.
No protected API gap was found during this sweep.
