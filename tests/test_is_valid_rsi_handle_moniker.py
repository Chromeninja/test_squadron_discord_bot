import pytest
from verification import rsi_verification as rv

class FakeHTTP:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
    async def fetch_html(self, url):
        self.calls.append(url)
        return self.pages.get(url)

ORG_HTML = '<div class="box-content org main visibility-V"><a class="value">TEST Squadron - Best Squardon!</a></div>'
PROFILE_HTML = '<div class="profile"><div class="info">\n<p class="entry"><strong class="value">Display Name</strong></p>\n<p class="entry"><span class="label">Handle name</span><strong class="value">CaseHandle</strong></p></div></div>'

@pytest.mark.asyncio
async def test_is_valid_rsi_handle_returns_moniker(monkeypatch):
    http = FakeHTTP({
        'https://robertsspaceindustries.com/citizens/TestUser/organizations': ORG_HTML,
        'https://robertsspaceindustries.com/citizens/TestUser': PROFILE_HTML,
    })
    verify_value, cased_handle, moniker = await rv.is_valid_rsi_handle('TestUser', http)
    assert verify_value == 1
    assert cased_handle == 'CaseHandle'
    assert moniker == 'Display Name'

MISSING_MONIKER_PROFILE = '<div class="profile"><div class="info">\n<p class="entry"><span class="label">Handle name</span><strong class="value">CaseHandle</strong></p></div></div>'
EMPTY_MONIKER_PROFILE = '<div class="profile"><div class="info">\n<p class="entry"><strong class="value">   </strong></p>\n<p class="entry"><span class="label">Handle name</span><strong class="value">CaseHandle</strong></p></div></div>'
MALFORMED_PROFILE = '<html><div class="profile"><div class="info"><p class="entry"><span class="label">Handle name</span></p></div></div>'

@pytest.mark.asyncio
async def test_is_valid_rsi_handle_missing_moniker(monkeypatch):
    http = FakeHTTP({
        'https://robertsspaceindustries.com/citizens/TestUser/organizations': ORG_HTML,
        'https://robertsspaceindustries.com/citizens/TestUser': MISSING_MONIKER_PROFILE,
    })
    verify_value, cased_handle, moniker = await rv.is_valid_rsi_handle('TestUser', http)
    assert verify_value == 1
    assert cased_handle == 'CaseHandle'
    assert moniker is None

@pytest.mark.asyncio
async def test_is_valid_rsi_handle_empty_moniker(monkeypatch):
    http = FakeHTTP({
        'https://robertsspaceindustries.com/citizens/TestUser/organizations': ORG_HTML,
        'https://robertsspaceindustries.com/citizens/TestUser': EMPTY_MONIKER_PROFILE,
    })
    verify_value, cased_handle, moniker = await rv.is_valid_rsi_handle('TestUser', http)
    assert verify_value == 1
    assert cased_handle == 'CaseHandle'
    assert moniker is None

@pytest.mark.asyncio
async def test_is_valid_rsi_handle_malformed_profile(monkeypatch):
    http = FakeHTTP({
        'https://robertsspaceindustries.com/citizens/TestUser/organizations': ORG_HTML,
        'https://robertsspaceindustries.com/citizens/TestUser': MALFORMED_PROFILE,
    })
    verify_value, cased_handle, moniker = await rv.is_valid_rsi_handle('TestUser', http)
    # Handle should still be found (CaseHandle) absence due to malformed structure may null it
    assert verify_value == 1
    # cased_handle may be None if extraction fails gracefully
    assert moniker is None
