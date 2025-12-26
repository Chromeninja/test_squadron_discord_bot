"""
HTML Sample Factories

Provides factory functions for generating RSI HTML samples and loading real samples.
Use these to test RSI parsing without hitting live RSI endpoints.
"""

from __future__ import annotations

from pathlib import Path


def load_sample_html(filename: str) -> str:
    """
    Load a sample HTML file from the tests directory.

    Args:
        filename: Name of the HTML file (e.g., "sample_rsi_profile.html")

    Returns:
        The HTML content as a string.

    Raises:
        FileNotFoundError: If the sample file doesn't exist.
    """
    tests_dir = Path(__file__).parent.parent
    sample_path = tests_dir / filename
    return sample_path.read_text(encoding="utf-8")


def make_org_html(
    main_org: str | None = None,
    main_visible: bool = True,
    affiliates: list[tuple[str, bool]] | None = None,
    malformed: bool = False,
) -> str:
    """
    Generate RSI organization HTML for testing.

    Args:
        main_org: Name of the main organization (None for no main org)
        main_visible: Whether the main org is visible (True) or hidden (False)
        affiliates: List of (org_name, is_visible) tuples for affiliate orgs
        malformed: If True, generate intentionally malformed HTML

    Returns:
        Generated HTML string.

    Examples:
        # User with TEST as visible main org and one hidden affiliate
        html = make_org_html(
            main_org="TEST Squadron - Best Squadron!",
            main_visible=True,
            affiliates=[("Hidden Org", False)]
        )

        # User with no organizations
        html = make_org_html()

        # Malformed HTML for error handling tests
        html = make_org_html(main_org="TEST", malformed=True)
    """
    if malformed:
        return "<div><span>broken html with no closing tags"

    parts = ["<html><body>"]

    if main_org:
        visibility = "V" if main_visible else "H"
        parts.append(f'''
    <div class="box-content org main visibility-{visibility}">
        <a class="value">{main_org}</a>
    </div>''')

    if affiliates:
        for org_name, is_visible in affiliates:
            visibility = "V" if is_visible else "H"
            parts.append(f'''
    <div class="box-content org affiliation visibility-{visibility}">
        <a class="value">{org_name}</a>
    </div>''')

    if not main_org and not affiliates:
        parts.append('''
    <div class="container">
        <p>No organizations found</p>
    </div>''')

    parts.append("</body></html>")
    return "".join(parts)


def make_bio_html(
    bio_text: str | None = None,
    token: str | None = None,
    selector_type: str = "standard",
    missing_bio: bool = False,
) -> str:
    """
    Generate RSI profile bio HTML for testing.

    Args:
        bio_text: Custom bio text (overrides token insertion)
        token: Verification token to embed in bio (e.g., "1234")
        selector_type: Which HTML structure to use:
            - "standard": Standard .entry.bio .value structure
            - "alternative": Alternative .user-bio structure
            - "nested": Deeply nested structure
        missing_bio: If True, generate HTML with no bio section

    Returns:
        Generated HTML string.

    Examples:
        # Bio with token 1234
        html = make_bio_html(token="1234")

        # Bio with custom text
        html = make_bio_html(bio_text="Hello world!")

        # Alternative selector structure
        html = make_bio_html(token="5678", selector_type="alternative")

        # No bio section at all
        html = make_bio_html(missing_bio=True)
    """
    if missing_bio:
        return """<html><body>
    <div class="profile">
        <div class="info">
            <p>No bio section found</p>
        </div>
    </div>
</body></html>"""

    # Build bio content
    if bio_text:
        content = bio_text
    elif token:
        content = f"Welcome to my profile! My verification token is {token} and I love Star Citizen."
    else:
        content = "This is my bio without any verification tokens. Just some regular text."

    if selector_type == "standard":
        return f"""<html><body>
    <div class="profile">
        <div class="info">
            <div class="entry bio">
                <div class="value">
                    {content}
                </div>
            </div>
        </div>
    </div>
</body></html>"""

    elif selector_type == "alternative":
        return f"""<html><body>
    <div class="user-bio">
        {content}
    </div>
</body></html>"""

    elif selector_type == "nested":
        return f"""<html><body>
    <div class="profile-wrapper">
        <div class="profile-content">
            <div class="bio-section">
                <div class="entry bio">
                    <div class="label">Bio</div>
                    <div class="value">{content}</div>
                </div>
            </div>
        </div>
    </div>
</body></html>"""

    else:
        raise ValueError(f"Unknown selector_type: {selector_type}")


def make_profile_html(
    handle: str = "TestUser",
    community_moniker: str | None = None,
    enlisted: str = "January 1, 2020",
    bio: str | None = None,
    location: str | None = None,
    fluency: list[str] | None = None,
) -> str:
    """
    Generate a complete RSI profile HTML page for testing.

    Args:
        handle: RSI handle/username
        community_moniker: Display name (defaults to handle)
        enlisted: Enlistment date string
        bio: Bio text
        location: Location string
        fluency: List of languages

    Returns:
        Generated HTML string representing a full profile page.
    """
    moniker = community_moniker or handle
    fluency_html = ""
    if fluency:
        fluency_items = "".join(f"<li>{lang}</li>" for lang in fluency)
        fluency_html = f'<div class="entry fluency"><div class="value"><ul>{fluency_items}</ul></div></div>'

    location_html = ""
    if location:
        location_html = f'<div class="entry location"><div class="value">{location}</div></div>'

    bio_html = ""
    if bio:
        bio_html = f'<div class="entry bio"><div class="value">{bio}</div></div>'

    return f"""<html>
<head><title>{handle} - Roberts Space Industries</title></head>
<body>
    <div class="profile-wrapper">
        <div class="profile-content">
            <div class="info">
                <div class="entry handle">
                    <div class="value">{handle}</div>
                </div>
                <div class="entry community-moniker">
                    <div class="value">{moniker}</div>
                </div>
                <div class="entry enlisted">
                    <div class="value">{enlisted}</div>
                </div>
                {location_html}
                {fluency_html}
                {bio_html}
            </div>
        </div>
    </div>
</body>
</html>"""
