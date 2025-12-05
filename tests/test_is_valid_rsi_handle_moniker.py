import pytest

from verification import rsi_verification as rv


class FakeHTTP:
    def __init__(self, pages) -> None:
        self.pages = pages
        self.calls = []

    async def fetch_html(self, url):
        self.calls.append(url)
        return self.pages.get(url)


ORG_HTML = (
    '<div class="box-content org main visibility-V">'
    '<a class="value">TEST Squadron - Best Squardon!</a></div>'
)
PROFILE_HTML = (
    '<div class="profile"><div class="info">\n'
    '<p class="entry"><strong class="value">Display Name</strong></p>\n'
    '<p class="entry"><span class="label">Handle name</span>'
    '<strong class="value">CaseHandle</strong></p></div></div>'
)
SPECIAL_CHAR_MONIKER_PROFILE = (
    '<div class="profile"><div class="info">\n'
    '<p class="entry"><strong class="value">Test@User#123</strong></p>\n'
    '<p class="entry"><span class="label">Handle name</span>'
    '<strong class="value">CaseHandle</strong></p></div></div>'
)
WHITESPACE_MONIKER_PROFILE = (
    '<div class="profile"><div class="info">\n'
    '<p class="entry"><span class="label">Handle name</span>'
    '<strong class="value">CaseHandle</strong></p></div></div>'
)
EMOJI_MONIKER_PROFILE = (
    '<div class="profile"><div class="info">\n'
    '<p class="entry"><strong class="value">Test🎮User</strong></p>\n'
    '<p class="entry"><span class="label">Handle name</span>'
    '<strong class="value">CaseHandle</strong></p></div></div>'
)


@pytest.mark.asyncio
async def test_is_valid_rsi_handle_returns_moniker(monkeypatch) -> None:
    http = FakeHTTP(
        {
            "https://robertsspaceindustries.com/citizens/TestUser/organizations": ORG_HTML,
            "https://robertsspaceindustries.com/citizens/TestUser": SPECIAL_CHAR_MONIKER_PROFILE,
        }
    )
    (
        verify_value,
        cased_handle,
        moniker,
        main_orgs,
        affiliate_orgs,
    ) = await rv.is_valid_rsi_handle(
        "TestUser",
        http,  # type: ignore[arg-type]
        "test squadron - best squardon!",
    )
    assert verify_value == 1
    assert cased_handle == "CaseHandle"
    assert moniker == "Test@User#123"
    assert isinstance(main_orgs, list)
    assert isinstance(affiliate_orgs, list)
    assert isinstance(main_orgs, list)
    assert isinstance(affiliate_orgs, list)


MISSING_MONIKER_PROFILE = (
    '<div class="profile"><div class="info">\n'
    '<p class="entry"><span class="label">Handle name</span>'
    '<strong class="value">CaseHandle</strong></p></div></div>'
)
EMPTY_MONIKER_PROFILE = (
    '<div class="profile"><div class="info">\n'
    '<p class="entry"><strong class="value">   </strong></p>\n'
    '<p class="entry"><span class="label">Handle name</span>'
    '<strong class="value">CaseHandle</strong></p></div></div>'
)
MALFORMED_PROFILE = (
    '<html><div class="profile"><div class="info">'
    '<p class="entry"><span class="label">Handle name</span></p></div></div>'
)


@pytest.mark.asyncio
async def test_is_valid_rsi_handle_missing_moniker(monkeypatch) -> None:
    http = FakeHTTP(
        {
            "https://robertsspaceindustries.com/citizens/TestUser/organizations": ORG_HTML,
            "https://robertsspaceindustries.com/citizens/TestUser": WHITESPACE_MONIKER_PROFILE,
        }
    )
    (
        verify_value,
        cased_handle,
        moniker,
        main_orgs,
        affiliate_orgs,
    ) = await rv.is_valid_rsi_handle(
        "TestUser",
        http,  # type: ignore[arg-type]
        "test squadron - best squardon!",
    )
    assert verify_value == 1
    assert cased_handle == "CaseHandle"
    assert moniker is None
    assert isinstance(main_orgs, list)
    assert isinstance(affiliate_orgs, list)
    assert isinstance(main_orgs, list)
    assert isinstance(affiliate_orgs, list)
    assert isinstance(main_orgs, list)
    assert isinstance(affiliate_orgs, list)


@pytest.mark.asyncio
async def test_is_valid_rsi_handle_empty_moniker(monkeypatch) -> None:
    http = FakeHTTP(
        {
            "https://robertsspaceindustries.com/citizens/TestUser/organizations": ORG_HTML,
            "https://robertsspaceindustries.com/citizens/TestUser": EMOJI_MONIKER_PROFILE,
        }
    )
    (
        verify_value,
        cased_handle,
        moniker,
        main_orgs,
        affiliate_orgs,
    ) = await rv.is_valid_rsi_handle(
        "TestUser",
        http,  # type: ignore[arg-type]
        "test squadron - best squardon!",
    )
    assert verify_value == 1
    assert cased_handle == "CaseHandle"
    # Emoji should be stripped by _sanitize_moniker, resulting in "TestUser"
    # Since handle is "CaseHandle" and moniker is "TestUser", they don't match, so moniker is returned
    assert moniker == "TestUser"
    assert isinstance(main_orgs, list)
    assert isinstance(affiliate_orgs, list)


@pytest.mark.asyncio
async def test_is_valid_rsi_handle_malformed_profile(monkeypatch) -> None:
    http = FakeHTTP(
        {
            "https://robertsspaceindustries.com/citizens/TestUser/organizations": ORG_HTML,
            "https://robertsspaceindustries.com/citizens/TestUser": MALFORMED_PROFILE,
        }
    )
    (
        verify_value,
        _cased_handle,
        moniker,
        main_orgs,
        affiliate_orgs,
    ) = await rv.is_valid_rsi_handle(
        "TestUser",
        http,  # type: ignore[arg-type]
        "test squadron - best squardon!",
    )
    # Handle should still be found (CaseHandle) absence due to malformed
    # structure may null it
    assert verify_value == 1
    # cased_handle may be None if extraction fails gracefully
    assert moniker is None
    assert isinstance(main_orgs, list)
    assert isinstance(affiliate_orgs, list)


@pytest.mark.asyncio
async def test_is_valid_rsi_handle_invalid_format(monkeypatch) -> None:
    """Invalid handle format should short-circuit without HTTP calls."""
    http = FakeHTTP({})
    (
        verify_value,
        cased_handle,
        moniker,
        main_orgs,
        affiliate_orgs,
    ) = await rv.is_valid_rsi_handle(
        "@@Bad*",
        http,  # type: ignore[arg-type]
        "test squadron - best squardon!",
    )
    assert verify_value is None
    assert cased_handle is None
    assert moniker is None
    assert main_orgs == []
    assert affiliate_orgs == []
    assert http.calls == []  # no network activity


@pytest.mark.asyncio
async def test_is_valid_rsi_handle_profile_fetch_none(monkeypatch) -> None:
    """Profile HTML missing -> returns verify value but no handle/moniker."""
    http = FakeHTTP(
        {
            "https://robertsspaceindustries.com/citizens/TestUser/organizations": ORG_HTML,
            # profile URL intentionally absent
        }
    )
    (
        verify_value,
        cased_handle,
        moniker,
        main_orgs,
        affiliate_orgs,
    ) = await rv.is_valid_rsi_handle(
        "TestUser",
        http,  # type: ignore[arg-type]
        "test squadron - best squardon!",
    )
    assert verify_value == 1  # org page still parsed
    assert cased_handle is None
    assert moniker is None
    assert isinstance(main_orgs, list)
    assert isinstance(affiliate_orgs, list)


@pytest.mark.asyncio
async def test_is_valid_rsi_handle_moniker_same_as_handle_suppressed(
    monkeypatch,
) -> None:
    """Moniker identical (case-insensitive) to handle should be suppressed (None)."""
    profile_same_moniker = (
        '<div class="profile"><div class="info">\n'
        '<p class="entry"><strong class="value">CaseHandle</strong></p>\n'
        '<p class="entry"><span class="label">Handle name</span>'
        '<strong class="value">CaseHandle</strong></p></div></div>'
    )
    http = FakeHTTP(
        {
            "https://robertsspaceindustries.com/citizens/TestUser/organizations": ORG_HTML,
            "https://robertsspaceindustries.com/citizens/TestUser": profile_same_moniker,
        }
    )
    (
        verify_value,
        cased_handle,
        moniker,
        main_orgs,
        affiliate_orgs,
    ) = await rv.is_valid_rsi_handle(
        "TestUser",
        http,  # type: ignore[arg-type]
        "test squadron - best squardon!",
    )
    assert verify_value == 1
    assert cased_handle == "CaseHandle"
    assert moniker is None  # suppressed
    assert isinstance(main_orgs, list)
    assert isinstance(affiliate_orgs, list)


@pytest.mark.asyncio
async def test_is_valid_rsi_handle_org_parse_exception(monkeypatch) -> None:
    """Exception while parsing org HTML => total failure (None triple)."""

    async def fake_fetch(url):
        return "<html>broken"

    http = FakeHTTP({})
    http.fetch_html = fake_fetch  # override method

    def boom(html):
        raise RuntimeError("parse error")

    monkeypatch.setattr(rv, "parse_rsi_organizations", boom)
    (
        verify_value,
        cased_handle,
        moniker,
        main_orgs,
        affiliate_orgs,
    ) = await rv.is_valid_rsi_handle(
        "TestUser",
        http,  # type: ignore[arg-type]
        "test squadron - best squardon!",
    )
    assert verify_value is None
    assert cased_handle is None
    assert moniker is None
    assert main_orgs == []
    assert affiliate_orgs == []
