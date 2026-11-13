"""High-confidence exclusions; the model still handles the rest of the scope contract.

An excluded approach can appear in an in-scope comparison, so mere mention is insufficient.
Keep deterministic refusals narrow: requests to calculate its capital or risk weight.
"""

import re


def refusal_reason(question: str) -> str | None:
    approach = re.search(r"\bSEC[-\s]?(?:IRBA|ERBA|SA)\b", question, re.I)
    calculation = re.search(
        r"calculat\w*|comput\w*|formula", question, re.I,
    )
    if approach and calculation:
        return "Securitisation approach calculations are outside the RegLens MVP corpus scope."
    return None
