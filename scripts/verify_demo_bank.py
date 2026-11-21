import argparse

from sqlalchemy import Engine, select

from app.core.config import Settings
from app.database.base import utc_now
from app.database.engine import make_engine
from app.database.session import write_transaction
from app.models import AuditLog, Vendor, VendorBankAccount
from app.services.vendor_service import primary_account


def verify_demo_bank(engine: Engine, *, business_id: int, vendor_id: int, reference: str) -> None:
    if not reference.startswith("demo:"):
        raise ValueError("This command accepts only fictional demo references")
    with write_transaction(engine) as session:
        vendor = session.scalar(select(Vendor).where(Vendor.id == vendor_id, Vendor.business_id == business_id))
        account = session.scalar(select(VendorBankAccount).where(
            VendorBankAccount.business_id == business_id, VendorBankAccount.vendor_id == vendor_id,
            VendorBankAccount.reference == reference, VendorBankAccount.retired_at.is_(None),
        ))
        if vendor is None or account is None:
            raise ValueError("Active demo account was not found")
        old = primary_account(session, vendor)
        if old and old.id != account.id:
            old.is_primary = False
            old.retired_at = utc_now()
            session.flush()
        account.is_primary = True
        account.verified_at = utc_now()
        session.add(AuditLog(business_id=business_id, action="independent_demo_bank_verification",
                             entity_id=account.id, details={"previous_account_id": old.id if old else None}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record an independent fictional bank verification for a demo.")
    parser.add_argument("--business-id", type=int, required=True)
    parser.add_argument("--vendor-id", type=int, required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--attest-demo-verification", action="store_true", required=True)
    args = parser.parse_args()
    verify_demo_bank(make_engine(Settings.from_env().database_url), business_id=args.business_id,
                     vendor_id=args.vendor_id, reference=args.reference)
