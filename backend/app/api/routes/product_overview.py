from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import auth_error, require_admin_session
from app.db.session import get_db
from app.schemas.common import success_response
from app.services.product_overview import build_product_overview

router = APIRouter()


@router.get("/overview")
def product_overview(request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    return success_response(build_product_overview(db), "overview generated")
