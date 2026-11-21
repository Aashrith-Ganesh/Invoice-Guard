from uuid import uuid4


def simulated_reference() -> str:
    return f"sim_{uuid4().hex}"


# A simulator acceptance only establishes INITIATED. Signed events settle it.
TRANSITIONS = {
    "INITIATED": frozenset({"SUCCESS", "FAILED", "UNKNOWN"}),
    "UNKNOWN": frozenset({"SUCCESS", "FAILED"}),
    "SUCCESS": frozenset({"REVERSED"}),
}
