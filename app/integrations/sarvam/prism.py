"""Prism rating adapters.

`HeuristicPrism` is the offline stand-in for `sarvam-prism` (`client.decisions.create`). It scores how
far a person can trust the extraction, 0..100. The score is a signal: the lane rule in
`app/services/review_policy.py` combines it with the deterministic checks, and a high score can never
clear a rule HOLD or BLOCK.
"""
from decimal import Decimal, InvalidOperation

from app.integrations.sarvam.types import Extraction, Rating, Signal
from app.schemas.validation import Decision

CRITICAL = ("invoice_number", "invoice_date", "gstin", "legal_name", "bank_reference", "subtotal", "tax_total",
            "grand_total")
CLEAR = Decimal("0.95")


class HeuristicPrism:
    name = "prism-heuristic"

    def rate(self, extraction: Extraction, decision: Decision | None) -> Rating:
        if extraction.invoice is None:
            return Rating(self.name, 0, [Signal("PRISM_UNREADABLE", "The document could not be read.", 100)])
        signals: list[Signal] = []
        if extraction.display.get("handwritten"):
            signals.append(Signal("PRISM_HANDWRITTEN", "Handwritten document; figures are harder to read.", 14))
        confidence = extraction.invoice.get("confidence") if isinstance(extraction.invoice.get("confidence"), dict) else {}
        unclear = []
        penalty = Decimal(0)
        for field in CRITICAL:
            try:
                value = Decimal(str(confidence[field]))
            except (KeyError, InvalidOperation):
                continue
            if value < CLEAR:
                unclear.append(field)
                penalty += (CLEAR - value) * 80
        if unclear:
            signals.append(Signal("PRISM_FIELD_CONFIDENCE",
                                  f"Read with less than 95% certainty: {', '.join(unclear)}.", int(penalty)))
        score = 100 - sum(signal.impact for signal in signals)
        if decision is not None and decision.overall_status != "PASS":
            cap = 35 if decision.overall_status == "BLOCK" else 60
            if score > cap:
                signals.append(Signal(f"PRISM_RULE_{decision.overall_status}",
                                      f"Rule checks returned {decision.overall_status}.", score - cap))
                score = cap
        if not signals:
            signals.append(Signal("PRISM_CLEAR", "Clear, consistent document.", 0))
        return Rating(self.name, max(0, min(100, score)), signals)
