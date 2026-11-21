"""Red line 5: never log full bank account numbers. Mask to the last 4 digits."""
import logging
import re

_ACCOUNT_RE = re.compile(r"(?<!\d)\d{9,18}(?!\d)")
_installed = False


def mask_account(account: str) -> str:
    """Keep only the last 4 characters of a bank account number."""
    if len(account) <= 4:
        return "X" * len(account)
    return "X" * (len(account) - 4) + account[-4:]


def mask_text(text: str) -> str:
    return _ACCOUNT_RE.sub(lambda match: mask_account(match.group()), text)


def install_account_masking() -> None:
    """Mask account-number-like digit runs in every log record. Idempotent."""
    global _installed
    if _installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            # Uvicorn's formatter reads the structured access-log arguments directly.
            record.args = tuple(mask_text(arg) if isinstance(arg, str) else arg for arg in record.args)
        else:
            record.msg = mask_text(record.getMessage())
            record.args = None
        return record

    logging.setLogRecordFactory(factory)
    _installed = True
