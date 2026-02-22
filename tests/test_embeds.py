import discord

from helpers.embeds import (
    DEFAULT_THUMBNAIL,
    EmbedColors,
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


# ---------------------------------------------------------------------------
# EmbedColors constants
# ---------------------------------------------------------------------------


def test_embed_colors_are_valid_hex() -> None:
    """Every EmbedColors attribute should be a positive int within 24-bit range."""
    for attr in dir(EmbedColors):
        if attr.startswith("_"):
            continue
        val = getattr(EmbedColors, attr)
        assert isinstance(val, int), f"{attr} is not int"
        assert 0 <= val <= 0xFFFFFF, f"{attr}=0x{val:06X} out of 24-bit range"


def test_embed_colors_known_values() -> None:
    """Spot-check canonical values haven't drifted."""
    assert EmbedColors.SUCCESS == 0x00FF00
    assert EmbedColors.ERROR == 0xFF0000
    assert EmbedColors.WARNING == 0xFFA500
    assert EmbedColors.INFO == 0x3498DB
    assert EmbedColors.PRIMARY == 0xFFBB00
    assert EmbedColors.BLURPLE == 0x5865F2


# ---------------------------------------------------------------------------
# DEFAULT_THUMBNAIL constant and usage
# ---------------------------------------------------------------------------


def test_default_thumbnail_is_https_url() -> None:
    assert DEFAULT_THUMBNAIL.startswith("https://")


def test_create_embed_uses_default_thumbnail() -> None:
    """create_embed() with no thumbnail_url arg should use DEFAULT_THUMBNAIL."""
    e = create_embed("T", "D")
    assert e.thumbnail is not None
    assert e.thumbnail.url == DEFAULT_THUMBNAIL


def test_create_embed_uses_embed_colors_success_default() -> None:
    """create_embed() default color should be EmbedColors.SUCCESS."""
    e = create_embed("T", "D")
    assert e.color is not None
    assert e.color.value == EmbedColors.SUCCESS


def test_verification_embed_uses_constants() -> None:
    e = create_verification_embed()
    assert e.color is not None
    assert e.color.value == EmbedColors.VERIFICATION
    assert e.thumbnail is not None
    assert e.thumbnail.url == DEFAULT_THUMBNAIL


def test_error_embed_uses_error_color() -> None:
    e = create_error_embed("fail")
    assert e.color is not None
    assert e.color.value == EmbedColors.ERROR


def test_success_embed_uses_success_color() -> None:
    e = create_success_embed("ok")
    assert e.color is not None
    assert e.color.value == EmbedColors.SUCCESS


def test_cooldown_embed_uses_warning_color() -> None:
    e = create_cooldown_embed(9999999999)
    assert e.color is not None
    assert e.color.value == EmbedColors.WARNING
