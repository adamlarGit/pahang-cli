"""Expected failures for diagnosed changes in live project data.

A plain xfail marker excuses every failure in a test. Call this helper at the
point the named data condition matters instead: a failure before that point, or
any failure once the condition has cleared, is still a failure.
"""
from __future__ import annotations

import pytest


def xfail_while_data_condition(detected: bool, *, condition: str, evidence: str, removal: str) -> None:
    """Stop the test as an expected failure while a diagnosed data condition holds.

    `detected` must come from inspecting the data, not be a fixed True. Call this
    immediately before the affected assertion: the test stops here, so nothing
    after this call is checked while the condition holds.

    The removal condition is only text, because an imperative xfail cannot report
    an unexpected pass. Once the condition clears the test runs normally.
    """
    if detected:
        pytest.xfail(f"Live data: {condition}. Evidence: {evidence}. Remove when: {removal}.")
