from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import Actor, Database
from app.core.exceptions import reject
from app.database.session import write_transaction
from app.models import Business, Payment
from app.schemas.payment import InitiateRequest, PaymentView
from app.services.payment_service import initiate, payment_view

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/initiate", status_code=201, responses={200: {"model": PaymentView}})
def initiate_payment(data: InitiateRequest, actor: Actor, engine: Database, response: Response) -> PaymentView:
    with write_transaction(engine) as session:
        result, created = initiate(session, session.get(Business, actor.business_id), data)
    response.status_code = 201 if created else 200
    return result


@router.get("/{payment_id}")
def get_payment(payment_id: int, actor: Actor, engine: Database) -> PaymentView:
    with Session(engine) as session:
        attempt = session.scalar(select(Payment).where(
            Payment.business_id == actor.business_id, Payment.id == payment_id,
        ))
        if attempt is None:
            raise reject(404, "PAYMENT_NOT_FOUND", "Payment was not found.")
        return payment_view(attempt)
