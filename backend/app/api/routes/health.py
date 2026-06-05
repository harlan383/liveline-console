from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis import RedisError
from rq import Worker
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.redis import get_redis_client, get_rq_redis_client
from app.db.session import get_db

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    data = {
        "backend": {"status": "ok", "detail": "FastAPI is running"},
        "database": {"status": "unknown", "detail": None},
        "redis": {"status": "unknown", "detail": None},
        "worker": {"status": "unknown", "detail": None},
    }

    try:
        db.execute(text("select 1"))
        data["database"] = {"status": "ok", "detail": "PostgreSQL query succeeded"}
    except SQLAlchemyError as exc:
        data["database"] = {"status": "error", "detail": exc.__class__.__name__}

    try:
        redis_client = get_redis_client()
        redis_client.ping()
        data["redis"] = {"status": "ok", "detail": "Redis ping succeeded"}
        workers = Worker.all(connection=get_rq_redis_client())
        if workers:
            data["worker"] = {
                "status": "ok",
                "detail": f"{len(workers)} RQ worker(s) registered",
            }
        else:
            data["worker"] = {"status": "missing", "detail": "No RQ worker registered"}
    except RedisError as exc:
        data["redis"] = {"status": "error", "detail": exc.__class__.__name__}
        data["worker"] = {"status": "unknown", "detail": "Redis unavailable"}

    success = all(component["status"] == "ok" for component in data.values())
    return JSONResponse(
        status_code=200 if success else 503,
        content={
            "success": success,
            "data": data,
            "message": "ok" if success else "one or more components are unavailable",
        },
    )
