# Stage 0 Notes

Stage 0 is a local skeleton and connectivity milestone only.

Implemented:

- Docker Compose services.
- Next.js empty management layout.
- FastAPI health endpoint.
- PostgreSQL and Redis checks.
- RQ Worker process.
- Admin initialization and login skeleton.
- Initial Alembic migration for all base tables.

Frontend dependency security closure:

- Next.js was upgraded from `14.2.18` to `15.5.18`.
- The upgrade addresses the `npm audit` moderate and critical security
  warnings reported against `next@14.2.18`.
- `postcss` is pinned through npm `overrides` to `8.5.10`.
- `frontend/package-lock.json` is retained so resolved dependency versions are
  reproducible.
- `frontend/Dockerfile` uses `package-lock.json` with `npm ci` so Docker builds
  install the audited dependency set.

Not implemented:

- VPS connection.
- SSH key upload, paste, storage, or processing.
- Remote SSH commands.
- Xray installation or configuration.
- 3x-ui usage.
- VPS reading.
- Node creation, editing, deletion, checking, links, or QR codes.
