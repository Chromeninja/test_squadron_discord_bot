import pytest

from verification.rsi_verification import _sanitize_moniker, extract_moniker

SAMPLE_HTML = """<div class="profile"><div class="info">
<p class="entry"><strong class="value">Cool Moniker</strong></p>
<p class="entry"><span class="label">Handle name</span><strong class="value">CaseHandle</strong></p>
</div></div>"""


@pytest.mark.asyncio
async def test_extract_moniker_parses_value_above_handle() -> None:
    moniker = extract_moniker(SAMPLE_HTML, handle="CaseHandle")
    assert moniker == "Cool Moniker"


@pytest.mark.asyncio
async def test_extract_moniker_skips_if_same_as_handle() -> None:
    html = SAMPLE_HTML.replace("Cool Moniker", "CaseHandle")
    moniker = extract_moniker(html, handle="CaseHandle")
    assert moniker is None


@pytest.mark.asyncio
async def test_sanitize_truncates_control_chars() -> None:
    raw = "C\u200bool\x00 Name"
    cleaned = _sanitize_moniker(raw)
    assert "\u200b" not in cleaned
    assert "\x00" not in cleaned
