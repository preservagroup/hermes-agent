"""Anthropic usage windows are percents, not fractions (#73901).

``GET /api/oauth/usage`` answers ``{"five_hour": {"utilization": 3.0}, "seven_day": {"utilization": 1.0}}``
— i.e. 3% of the session and 1% of the week used. The old ``_usage_windows(fraction=True)`` scaled any
value ``<= 1`` by 100, so a genuinely-1% week rendered as "Current week 100% used" on every surface.
These tests pin the pass-through: utilization is taken as-is, including 0.0 (never billed as 100%).
"""

from agent import account_usage


def _payload(five_hour, seven_day):
    return {"five_hour": {"utilization": five_hour, "resets_at": "2026-10-27T22:50:00Z"},
            "seven_day": {"utilization": seven_day, "resets_at": "2026-10-30T15:00:00Z"}}


def _anthropic_snapshot(monkeypatch, payload):
    monkeypatch.setattr(account_usage, "_get_json", lambda url, headers, *, timeout: payload)
    monkeypatch.setattr(account_usage, "resolve_anthropic_token", lambda **kw: "sk-ant-oat01-test")
    snapshot = account_usage.fetch_account_usage("anthropic", api_key="sk-ant-oat01-test")
    assert snapshot is not None and snapshot.windows
    return snapshot


def _percents(snapshot):
    return {w.label: w.used_percent for w in snapshot.windows}


def test_live_shaped_anthropic_utilization_is_not_rescaled(monkeypatch):
    """The real Pro payload (1% week, 3% session) must stay 1.0 / 3.0 — not 100.0 / 300.0."""
    percents = _percents(_anthropic_snapshot(monkeypatch, _payload(3.0, 1.0)))

    assert percents["Current session"] == 3.0
    assert percents["Current week"] == 1.0
    assert percents["Current week"] != 100.0


def test_zero_utilization_stays_zero(monkeypatch):
    """0.0 is an untouched quota, not "0 <= 1 → 100% used"."""
    percents = _percents(_anthropic_snapshot(monkeypatch, _payload(0.0, 0.0)))

    assert percents == {"Current session": 0.0, "Current week": 0.0}


def test_whole_percents_above_one_pass_through(monkeypatch):
    """Values that were already unambiguous (>1) keep rendering identically."""
    percents = _percents(_anthropic_snapshot(monkeypatch, _payload(42.5, 100.0)))

    assert percents == {"Current session": 42.5, "Current week": 100.0}


def test_usage_windows_takes_values_as_percent_for_every_source():
    """No caller may opt back into fraction guessing: the shared helper is percent-only."""
    windows = account_usage._usage_windows(
        {"five_hour": {"utilization": 1.0}, "seven_day": {"utilization": 0.0}},
        (("five_hour", "Current session"), ("seven_day", "Current week")), "utilization", "resets_at",
    )

    assert [w.used_percent for w in windows] == [1.0, 0.0]
