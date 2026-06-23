from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, auth, health, nodes, tasks, transit_resources, transit_routes, vps, workers
from app.api.routes import transit_haproxy_real_execution_gate
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="LiveLine Console API", version="0.0.1-stage0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

transit_haproxy_real_execution_gate.install()

app.include_router(health.router, prefix="/api")
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(nodes.router, prefix="/api/nodes", tags=["nodes"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(
    transit_resources.router,
    prefix="/api/transit-resources",
    tags=["transit-resources"],
)
app.include_router(
    transit_routes.router,
    prefix="/api/transit-routes",
    tags=["transit-routes"],
)
app.include_router(vps.router, prefix="/api/vps", tags=["vps"])
app.include_router(workers.router, prefix="/api", tags=["workers"])
app.include_router(workers.setup_router, tags=["worker-setup"])
