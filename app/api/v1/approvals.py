from fastapi import APIRouter, Response

from app.api.dependencies import Database, Owner
from app.database.session import write_transaction
from app.models import Business
from app.schemas.approval import ApprovalChallenge, ApprovalRequest, ApprovalView, ConfirmRequest
from app.services.approval_service import confirm, issue

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("", status_code=201)
def create_approval(data: ApprovalRequest, owner: Owner, engine: Database, response: Response) -> ApprovalChallenge:
    response.headers["Cache-Control"] = "no-store"
    with write_transaction(engine) as session:
        return issue(session, session.get(Business, owner.business_id), data)


@router.post("/confirm")
def confirm_approval(data: ConfirmRequest, owner: Owner, engine: Database) -> ApprovalView:
    with write_transaction(engine) as session:
        return confirm(session, session.get(Business, owner.business_id), data.token.get_secret_value())
