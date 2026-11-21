"""Parse a bounded grammar for English INR amounts from invoice extraction."""

import re
from unicodedata import decimal

SMALL = {
    word: number
    for number, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen".split()
    )
}
TENS = {
    word: number * 10
    for number, word in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)
}
SCALES = {"crore": 10_000_000, "lakh": 100_000, "thousand": 1_000}
RUPEE_MARKERS = {"rupee", "rupees", "inr", "rs", "rs.", "₹"}


def under_hundred(words: list[str]) -> int:
    if len(words) == 1 and words[0] in SMALL:
        return SMALL[words[0]]
    if words and words[0] in TENS:
        tens = TENS[words[0]]
        if len(words) == 1:
            return tens
        if len(words) == 2 and 1 <= SMALL.get(words[1], 0) <= 9:
            return tens + SMALL[words[1]]
    raise ValueError("Unsupported number group")


def number_group(words: list[str]) -> int:
    if len(words) < 2 or words[1] != "hundred":
        return under_hundred(words)
    hundreds = SMALL.get(words[0], 0)
    if not 1 <= hundreds <= 9:
        raise ValueError("Invalid hundreds")
    remainder = words[2:]
    if remainder[:1] == ["and"]:
        remainder = remainder[1:]
        if not remainder:
            raise ValueError("Incomplete number group")
    if remainder:
        value = under_hundred(remainder)
        if value == 0:
            raise ValueError("Invalid zero after hundreds")
        return hundreds * 100 + value
    return hundreds * 100


def cardinal(words: list[str]) -> int:
    total = 0
    start = 0
    previous_scale = max(SCALES.values()) + 1
    for index, word in enumerate(words):
        scale = SCALES.get(word.removesuffix("s"))
        if scale is None:
            continue
        group = number_group(words[start:index])
        if group == 0 or scale >= previous_scale:
            raise ValueError("Invalid scale order")
        total += group * scale
        start = index + 1
        previous_scale = scale
    remainder = words[start:]
    if total and remainder[:1] == ["and"]:
        remainder = remainder[1:]
        if not remainder:
            raise ValueError("Incomplete amount")
    return total + number_group(remainder) if remainder or not total else total


def parse_minor(text: str) -> int:
    """Return exact paise, or raise ValueError for unsupported or ambiguous wording."""
    normalized = text.strip().casefold().removesuffix(".")
    normalized = re.sub(r"(?<=[a-z])[-–](?=[a-z])", " ", normalized)
    words = normalized.split()
    if words[-1:] == ["only"]:
        words.pop()
    prefixed = bool(words and words[0] in RUPEE_MARKERS)
    if prefixed:
        words.pop(0)
    if not words:
        raise ValueError("Amount is missing")

    if words[-1] not in {"paise", "paisa"}:
        if words[-1] in RUPEE_MARKERS:
            words.pop()
        if len(words) == 1:
            digits = "".join(str(decimal(char)) if char.isdecimal() else char for char in words[0])
            if re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", digits):
                rupees, _, fraction = digits.partition(".")
                return int(rupees) * 100 + int(fraction.ljust(2, "0"))
        return cardinal(words) * 100

    words.pop()
    markers = [index for index, word in enumerate(words) if word in {"rupee", "rupees"}]
    if len(markers) == 1:
        split = markers[0]
        rupees = cardinal(words[:split])
        paise_words = words[split + 1:]
        if paise_words[:1] == ["and"]:
            paise_words = paise_words[1:]
    elif not markers and not prefixed:
        rupees, paise_words = 0, words
    elif not markers and prefixed and "and" in words:
        # With a leading currency marker, a single valid cardinal followed by
        # 'paise' is ambiguous. Require an explicit rupee/paise separator then.
        try:
            cardinal(words)
        except ValueError:
            split = len(words) - 1 - words[::-1].index("and")
            rupees, paise_words = cardinal(words[:split]), words[split + 1:]
        else:
            raise ValueError("Ambiguous rupee and paise split")
    else:
        raise ValueError("Invalid rupee or paise marker")
    paise = cardinal(paise_words)
    if paise > 99:
        raise ValueError("Paise must be less than one rupee")
    return rupees * 100 + paise
