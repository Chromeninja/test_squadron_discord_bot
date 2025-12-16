import discord

from helpers.embeds import (
    create_cooldown_embed,
    create_embed,
    create_error_embed,
    create_success_embed,
    create_token_embed,
    create_verification_embed,
)


def test_basic_embed() -> None:
    e = create_embed("Title", "Desc", color=0x123456, thumbnail_url="http://x")
    assert isinstance(e, discord.Embed)
    assert e.title == "Title"
    assert e.description == "Desc"


def test_verification_embed() -> None:
    e = create_verification_embed()
    assert e.title and "Account Verification" in e.title
    assert "Get Token" in (e.description or "")


def test_token_embed() -> None:
    e = create_token_embed("1234", 1700000000)
    # Field name includes an emoji prefix; match substring
    assert any("Your Verification PIN" in (f.name or "") for f in e.fields)
    assert "1234" in (e.fields[0].value or "")


def test_error_and_success_embeds() -> None:
    err = create_error_embed("Oops")
    ok = create_success_embed("Great")
    assert err.title and "Failed" in err.title
    assert ok.title and "Successful" in ok.title


def test_cooldown_embed() -> None:
    e = create_cooldown_embed(1700000000)
    assert e.title and "Cooldown" in e.title
    assert ["try", "again"][0].lower() in (e.description or "").lower()
