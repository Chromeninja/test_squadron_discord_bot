import pytest
from types import SimpleNamespace
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
