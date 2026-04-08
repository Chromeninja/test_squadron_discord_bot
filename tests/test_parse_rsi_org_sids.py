# tests/test_parse_rsi_org_sids.py
"""Tests for parse_rsi_org_sids — HTML-based SID extraction edge cases."""

from verification.rsi_verification import parse_rsi_org_sids

# ---------------------------------------------------------------------------
# Helpers — minimal HTML builders
# ---------------------------------------------------------------------------


def _org_div(
    kind: str,
    *,
    sid: str | None = None,
    visibility: str | None = None,
    label: str = "Spectrum Identification (SID)",
    extra_entry_before: str = "",
) -> str:
    """Build a single org div for testing.

    Args:
        kind: "main" or "affiliation" CSS class suffix.
        sid: The SID string. If None, no SID entry is emitted.
        visibility: "R" or "H" for redacted/hidden, else visible.
        label: Label text for the SID entry.
        extra_entry_before: Extra <p class="entry"> to inject before the SID entry.
    """
    vis_class = f" visibility-{visibility}" if visibility else ""
    inner = ""
    if extra_entry_before:
        inner += extra_entry_before
    if sid is not None:
        inner += (
            f'<p class="entry"><span class="label">{label}</span>'
            f'<strong class="value">{sid}</strong></p>'
        )
    return f'<div class="box-content org {kind}{vis_class}">{inner}</div>'


def _wrap_html(*divs: str) -> str:
    return f"<html><body>{''.join(divs)}</body></html>"


# ---------------------------------------------------------------------------
# Main org tests
# ---------------------------------------------------------------------------


def test_main_org_sid_basic() -> None:
    """Parse a simple visible main org with SID."""
    html = _wrap_html(_org_div("main", sid="TEST"))
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["TEST"]
    assert result["affiliate_orgs"] == []


def test_main_org_sid_not_in_first_entry() -> None:
    """SID entry is not the first p.entry — parser must iterate all entries."""
    extra = (
        '<p class="entry"><span class="label">Organization</span>'
        '<strong class="value">Test Squadron</strong></p>'
    )
    html = _wrap_html(_org_div("main", sid="TEST", extra_entry_before=extra))
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["TEST"]


def test_main_org_redacted_visibility_r() -> None:
    """Main org with visibility-R class → REDACTED."""
    html = _wrap_html(_org_div("main", sid="SECRET", visibility="R"))
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["REDACTED"]


def test_main_org_hidden_visibility_h() -> None:
    """Main org with visibility-H class → REDACTED."""
    html = _wrap_html(_org_div("main", sid="HIDDEN", visibility="H"))
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["REDACTED"]


def test_main_org_empty_sid_treated_as_redacted() -> None:
    """Main org with empty SID value → REDACTED."""
    html = _wrap_html(_org_div("main", sid=""))
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["REDACTED"]


def test_main_org_nbsp_sid_treated_as_redacted() -> None:
    """Main org with non-breaking space SID → REDACTED."""
    html = _wrap_html(_org_div("main", sid="\xa0"))
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["REDACTED"]


def test_main_org_no_sid_entry() -> None:
    """Main org div exists but has no SID p.entry → REDACTED."""
    extra = (
        '<p class="entry"><span class="label">Organization</span>'
        '<strong class="value">Some Org</strong></p>'
    )
    html = _wrap_html(_org_div("main", sid=None, extra_entry_before=extra))
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["REDACTED"]


def test_main_org_sid_label_variant() -> None:
    """SID entry with 'SID' in label text (not full 'Spectrum Identification')."""
    html = _wrap_html(_org_div("main", sid="TESTSID", label="SID"))
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["TESTSID"]


def test_no_orgs_at_all() -> None:
    """HTML with no org divs → empty lists."""
    html = _wrap_html("<div>No org data</div>")
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == []
    assert result["affiliate_orgs"] == []


# ---------------------------------------------------------------------------
# Affiliate org tests
# ---------------------------------------------------------------------------


def test_affiliate_org_basic() -> None:
    """Parse a simple visible affiliate org with SID."""
    html = _wrap_html(_org_div("affiliation", sid="XVII"))
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == []
    assert result["affiliate_orgs"] == ["XVII"]


def test_affiliate_missing_label() -> None:
    """Affiliate div has p.entry but no span.label → REDACTED fallback."""
    div = (
        '<div class="box-content org affiliation">'
        '<p class="entry"><strong class="value">NOSID</strong></p>'
        "</div>"
    )
    html = _wrap_html(div)
    result = parse_rsi_org_sids(html)
    assert result["affiliate_orgs"] == ["REDACTED"]


def test_affiliate_whitespace_only_sid() -> None:
    """Affiliate SID value is whitespace-only → REDACTED."""
    html = _wrap_html(_org_div("affiliation", sid="   "))
    result = parse_rsi_org_sids(html)
    assert result["affiliate_orgs"] == ["REDACTED"]


def test_affiliate_nbsp_sid() -> None:
    """Affiliate SID value is non-breaking space → REDACTED."""
    html = _wrap_html(_org_div("affiliation", sid="\xa0"))
    result = parse_rsi_org_sids(html)
    assert result["affiliate_orgs"] == ["REDACTED"]


def test_affiliate_redacted_visibility() -> None:
    """Affiliate with visibility-R → REDACTED."""
    html = _wrap_html(_org_div("affiliation", sid="VISIBLE", visibility="R"))
    result = parse_rsi_org_sids(html)
    assert result["affiliate_orgs"] == ["REDACTED"]


def test_multiple_affiliates() -> None:
    """Multiple affiliate divs with different SIDs."""
    html = _wrap_html(
        _org_div("affiliation", sid="XVII"),
        _org_div("affiliation", sid="AVOCADO"),
        _org_div("affiliation", visibility="R"),
    )
    result = parse_rsi_org_sids(html)
    assert result["affiliate_orgs"] == ["XVII", "AVOCADO", "REDACTED"]


# ---------------------------------------------------------------------------
# Mixed main + affiliate tests
# ---------------------------------------------------------------------------


def test_main_and_affiliates_combined() -> None:
    """Main org + affiliates parsed together."""
    html = _wrap_html(
        _org_div("main", sid="TEST"),
        _org_div("affiliation", sid="XVII"),
        _org_div("affiliation", sid="AVOCADO"),
    )
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["TEST"]
    assert result["affiliate_orgs"] == ["XVII", "AVOCADO"]


def test_main_redacted_affiliates_visible() -> None:
    """Main org redacted, affiliates visible."""
    html = _wrap_html(
        _org_div("main", visibility="R"),
        _org_div("affiliation", sid="XVII"),
    )
    result = parse_rsi_org_sids(html)
    assert result["main_orgs"] == ["REDACTED"]
    assert result["affiliate_orgs"] == ["XVII"]
