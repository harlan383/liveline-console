# Stage 3.4.1 Auth Login Gate

## Stage Goal

Stage 3.4.1 adds a system login gate for LiveLine Console. When an operator
opens the frontend without an active admin session, the app must render only the
login screen. VPS, node, transit resource, transit route, and task panels are
rendered only after a successful admin login.

This stage is a UI / Auth feature stage. It is not a network-link stage and is
not related to cutover execution.

## Implemented Flow

1. The frontend calls `GET /api/auth/me` on startup.
2. If the session is missing or invalid, only the login screen is shown.
3. The login screen posts credentials to `POST /api/auth/login`.
4. The backend verifies the admin password with the existing password hash
   method. It supports the existing admin table hash and an optional
   `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` configured hash for the matching
   active admin user.
5. A successful login renders the existing system shell and management panels.
6. Refreshing the page keeps the user logged in while the HttpOnly session is
   valid.
7. The top bar shows the logged-in admin username and a logout button.
8. Logout gets a CSRF token through the existing session flow, calls
   `POST /api/auth/logout`, clears the session cookie, and returns to the login
   screen.
9. Protected API calls that receive `401` notify the frontend and return the UI
   to the login screen.

## Backend Auth Interfaces

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- Existing CSRF endpoint remains available at `GET /api/auth/csrf`.

The stage reuses the existing admin database model, password hash verification,
HttpOnly cookie session, CSRF handling, and `require_admin_session` dependency.
Protected backend APIs continue to require an authenticated admin session and
return `401` when unauthenticated.

## Environment Variables

- `SESSION_SECRET`: signs and protects admin sessions.
- `INIT_TOKEN`: protects initial admin creation.
- `ADMIN_USERNAME`: optional configured admin username.
- `ADMIN_PASSWORD_HASH`: optional configured password hash for the matching
  active admin user. Do not put a plaintext password here.
- `COOKIE_SECURE`, `COOKIE_SAMESITE`, `SESSION_TTL_SECONDS`: session cookie and
  lifetime controls.

`.env.example` contains placeholders only. It does not contain real passwords,
tokens, SSH keys, node links, or private keys.

## Security Boundary

- Passwords are never stored in the frontend.
- Real passwords are not written to code, docs, or `.env.example`.
- The backend uses the existing password hash verifier instead of plaintext
  comparison for both database-stored and optional env-configured hashes.
- Sessions are stored in HttpOnly cookies.
- Protected APIs are guarded on the backend, not only hidden in the frontend.
- Unauthenticated users cannot see backend management panels in the frontend.

## Production Link Boundary

- `node.share_link` is not read, printed, or modified by this stage.
- No full node links are written to documents, logs, or task results.
- No database migration is added.
- No listening port is added.
- No SSH or remote command is executed.
- No backend Worker/RQ task is triggered.
- No firewall rule is changed.
- No cutover action is executed.
- `socat` 18443 remains the formal production link.
- `gost` 8443 remains the fallback link.
- `socat` does not take over 8443.
- `gost` 8443 is not stopped, disabled, downgraded, or replaced.

## Acceptance Steps

1. Open `http://localhost:3000` without a valid session.
2. Confirm that only the login page is visible.
3. Enter an incorrect username or password and confirm an error is shown.
4. Enter the correct admin credentials and confirm the system panel opens.
5. Refresh the page and confirm the session remains active.
6. Click logout and confirm the login page returns.
7. Call a protected API without a session and confirm it returns `401`.
8. Call the same protected API after login and confirm it returns normally.
9. Confirm no backend task was triggered.
10. Confirm no network-link state changed.

## Modified Files

- `backend/app/api/routes/auth.py`
- `backend/app/core/config.py`
- `frontend/components/AppShell.tsx`
- `frontend/components/LoginScreen.tsx`
- `frontend/lib/api.ts`
- `frontend/app/globals.css`
- `.env.example`
- `README.md`
- `docs/stage-3.4.1-auth-login-gate.md`

## Stage Result

Stage 3.4.1 implements the admin login gate while preserving the current
C-minimal cutover state. It does not modify `node.share_link`, does not add
ports, does not perform SSH, does not trigger backend tasks, and does not affect
the `socat` 18443 formal link or `gost` 8443 fallback link.
