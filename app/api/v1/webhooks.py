from hmac import compare_digest, digest
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.api.dependencies import Database
from app.core.exceptions import reject
from app.database.session import write_transaction
from app.schemas.payment import PaymentView, SimulatorEvent
from app.services.payment_service import apply_event

router = APIRouter(prefix="/webhooks", tags=["simulator"])


async def verified_simulator_event(request: Request) -> SimulatorEvent:
    secret = request.app.state.settings.simulator_secret
    signature = request.headers.get("X-Simulator-Signature", "")
    if not secret or len(signature) != 64:
        raise reject(401, "INVALID_SIMULATOR_SIGNATURE", "Simulator HMAC verification failed.")
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > 4096:
            raise reject(413, "EVENT_TOO_LARGE", "Simulator payload exceeds 4096 bytes.")
        payload.extend(chunk)
    expected = digest(secret.encode(), bytes(payload), "sha256").hex()
    if not compare_digest(expected.encode(), signature.encode()):
        raise reject(401, "INVALID_SIMULATOR_SIGNATURE", "Simulator HMAC verification failed.")
    try:
        return SimulatorEvent.model_validate_json(payload)
    except ValidationError:
        raise reject(422, "INVALID_SIMULATOR_EVENT", "Payload does not match the simulator event schema.") from None


@router.post("/payout")
def payout_webhook(event: Annotated[SimulatorEvent, Depends(verified_simulator_event)], engine: Database) -> PaymentView:
    with write_transaction(engine) as session:
        return apply_event(session, event)
