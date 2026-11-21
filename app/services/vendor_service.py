import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Vendor, VendorBankAccount
from app.schemas.invoice import ExtractedInvoice
from app.schemas.validation import Check


def primary_account(session: Session, vendor: Vendor) -> VendorBankAccount | None:
    return session.scalar(select(VendorBankAccount).where(
        VendorBankAccount.business_id == vendor.business_id,
        VendorBankAccount.vendor_id == vendor.id,
        VendorBankAccount.is_primary.is_(True),
        VendorBankAccount.retired_at.is_(None),
    ))


def normalized_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def verify_vendor(session: Session, business_id: int, data: ExtractedInvoice
                  ) -> tuple[Vendor | None, VendorBankAccount | None, list[Check]]:
    if not data.gstin:
        return None, None, []
    if not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]", data.gstin):
        return None, None, [Check(code="INVALID_GSTIN", status="BLOCK", detail="GSTIN format is invalid.")]
    vendor = session.scalar(select(Vendor).where(
        Vendor.business_id == business_id, Vendor.gstin == data.gstin,
    ))
    if vendor is None:
        return None, None, [Check(code="UNKNOWN_VENDOR", status="BLOCK", detail="GSTIN is absent from the vendor register.")]

    checks = [Check(code="TRUSTED_GSTIN", status="PASS", detail="GSTIN matches the vendor register.")]
    if data.legal_name:
        matches = normalized_name(data.legal_name) == normalized_name(vendor.legal_name)
        checks.append(Check(code="VENDOR_NAME", status="PASS" if matches else "BLOCK",
                            detail="Legal name matches." if matches else "Legal name differs from the vendor register."))

    account = primary_account(session, vendor)
    if not data.bank_reference:
        return vendor, None, checks
    if not account or account.reference != data.bank_reference:
        checks.append(Check(code="BANK_CHANGE", status="HOLD",
                            detail="Bank reference requires independent verification and fresh approval."))
        return vendor, None, checks
    if not account.verified_at:
        checks.append(Check(code="BANK_UNVERIFIED", status="HOLD", detail="Primary account is awaiting verification."))
        return vendor, None, checks
    checks.append(Check(code="VERIFIED_BANK", status="PASS", detail="Bank matches the verified primary account."))
    return vendor, account, checks
