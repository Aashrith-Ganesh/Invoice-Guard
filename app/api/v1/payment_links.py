from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import Database, Owner
from app.core.exceptions import reject
from app.database.session import write_transaction
from app.models import Business
from app.schemas.payment_link import CreatedPaymentLink, CreatePaymentLink, PaymentLinkToken, PublicPaymentLink
from app.services import payment_link_service

router = APIRouter(tags=["simulated-payment-links"])


def simulator_secret(request: Request, response: Response) -> str:
    response.headers["Cache-Control"] = "no-store"
    secret = request.app.state.settings.simulator_secret
    if not secret:
        raise reject(503, "SIMULATOR_DISABLED", "The payment simulator is unavailable.")
    return secret


Secret = Annotated[str, Depends(simulator_secret)]


@router.post("/payments/links", status_code=201)
def create_link(data: CreatePaymentLink, request: Request, owner: Owner, engine: Database,
                secret: Secret, response: Response) -> CreatedPaymentLink:
    with write_transaction(engine) as session:
        result, created = payment_link_service.create(session, session.get(Business, owner.business_id), data, secret)
    response.status_code = 201 if created else 200
    origin = request.app.state.settings.hosted_payment_origin
    return result.model_copy(update={"path": origin + result.path}) if origin else result


@router.post("/simulated-payment/status")
def payment_link_status(data: PaymentLinkToken, engine: Database, secret: Secret) -> PublicPaymentLink:
    with Session(engine) as session:
        return payment_link_service.view(session, payment_link_service.find(session, data.token, secret))


@router.post("/simulated-payment/simulate")
def simulate_payment_link(data: PaymentLinkToken, engine: Database, secret: Secret) -> PublicPaymentLink:
    with write_transaction(engine) as session:
        return payment_link_service.settle(session, payment_link_service.find(session, data.token, secret), secret)
