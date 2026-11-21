import argparse
from decimal import Decimal

from sqlalchemy import Engine

from app.core.config import Settings
from app.database.base import utc_now
from app.database.engine import make_engine
from app.database.session import write_transaction
from app.models import Business, Vendor, VendorBankAccount
from app.services.validation_service import minor


def seed(engine: Engine, cash: Decimal = Decimal("100000.00")) -> None:
    if not cash.is_finite() or not 0 <= cash <= Decimal("9999999999.99") or cash * 100 != int(cash * 100):
        raise ValueError("Cash must be a nonnegative amount with at most two decimal places")
    with write_transaction(engine) as session:
        if session.get(Business, 1):
            raise ValueError("Business 1 already exists. Seed a fresh demo database.")
        session.add(Business(id=1, name="Fictional Weddings & Events", cash_minor=minor(cash)))
        session.flush()
        classifications = ("Micro", "Small", "Medium", "Non-MSME")
        for number in range(1, 11):
            vendor = Vendor(business_id=1, gstin=f"99ZZZZZ{number - 1:04d}Z0Z0",
                            legal_name=f"Fictional Vendor {number}",
                            classification=classifications[(number - 1) % 4])
            session.add(vendor)
            session.flush()
            session.add_all([
                VendorBankAccount(business_id=1, vendor_id=vendor.id, is_primary=True,
                                  reference=f"demo:vendor-{number}:current",
                                  verified_at=utc_now() if number < 10 else None),
                VendorBankAccount(business_id=1, vendor_id=vendor.id,
                                  reference=f"demo:vendor-{number}:alternate"),
                VendorBankAccount(business_id=1, vendor_id=vendor.id,
                                  reference=f"demo:vendor-{number}:historical",
                                  verified_at=utc_now(), retired_at=utc_now()),
            ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed a migrated synthetic accounts payable database.")
    parser.add_argument("--cash", type=Decimal, default=Decimal("100000.00"))
    args = parser.parse_args()
    seed(make_engine(Settings.from_env().database_url), args.cash)
