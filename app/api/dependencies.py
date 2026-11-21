from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import Principal
from app.core.exceptions import reject
from app.core.security import token_hash
from app.models import Business

bearer = HTTPBearer(auto_error=False)


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


Database = Annotated[Engine, Depends(get_engine)]


def authenticate(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    engine: Database,
) -> Principal:
    if credentials:
        for key, principal in request.app.state.settings.bearer_keys.items():
            if key and compare_digest(key.encode(), credentials.credentials.encode()):
                with Session(engine) as session:
                    if session.get(Business, principal.business_id):
                        if principal.subject is None:
                            return principal.model_copy(update={"subject": f"credential:{token_hash(key)}"})
                        return principal
    error = reject(401, "UNAUTHENTICATED", "A valid business bearer credential is required.")
    error.headers = {"WWW-Authenticate": "Bearer"}
    raise error


Actor = Annotated[Principal, Depends(authenticate)]


def require_owner(actor: Actor) -> Principal:
    if actor.role != "owner":
        raise reject(403, "OWNER_REQUIRED", "Owner authentication is required.")
    return actor


Owner = Annotated[Principal, Depends(require_owner)]
