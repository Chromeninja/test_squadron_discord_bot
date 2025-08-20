import discord

from helpers.embeds import (
    create_embed,
    create_verification_embed,
    create_token_embed,
    create_error_embed,
    create_success_embed,
    create_cooldown_embed,
)


def test_basic_embed():
    e = create_embed("Title", "Desc", color=0x123456, thumbnail_url="http://x")
    assert isinstance(e, discord.Embed)
    assert e.title == "Title"
    assert e.description == "Desc"


def test_verification_embed():
    e = create_verification_embed()
    assert "Account Verification" in e.title
    assert "Get Token" in (e.description or "")


def test_token_embed():
    e = create_token_embed("1234", 1700000000)
    # Field name includes an emoji prefix; match substring
    assert any("Your Verification PIN" in f.name for f in e.fields)
    assert "1234" in e.fields[0].value


def test_error_and_success_embeds():
    err = create_error_embed("Oops")
    ok = create_success_embed("Great")
    assert "Failed" in err.title
    assert "Successful" in ok.title


def test_cooldown_embed():
    e = create_cooldown_embed(1700000000)
    assert "Cooldown" in e.title
    assert "try again".split()[0].lower() in (e.description or "").lower()
