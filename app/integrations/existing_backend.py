from pydantic import BaseModel, ConfigDict, PositiveInt
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Vendor


class GetVendorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor_id: PositiveInt


async def get_vendor(args: GetVendorArgs, context: dict) -> dict:
    with Session(context["engine"]) as session:
        vendor = session.scalar(select(Vendor).where(
            Vendor.business_id == context["business_id"], Vendor.id == args.vendor_id,
        ))
        if vendor is None:
            return {"found": False}
        return {"found": True, "vendor": {"id": vendor.id, "name": vendor.legal_name,
                                          "classification": vendor.classification}}
