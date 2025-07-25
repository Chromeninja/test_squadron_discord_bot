# helpers/announcement.py

import discord
import random
from helpers.discord_api import channel_send_message
from helpers.logger import get_logger
from helpers.announcement_templates import MAIN_TEMPLATES, AFFILIATE_TEMPLATES

logger = get_logger(__name__)

async def send_verification_announcements(
    bot,
    member: discord.Member,
    old_status: str,
    new_status: str,
    is_recheck: bool,
    by_admin: str = None
):
    config = bot.config
    public_channel_id = config['channels'].get('public_announcement_channel_id')
    lead_channel_id = config['channels'].get('leadership_announcement_channel_id')
    guild = member.guild

    if not isinstance(member, discord.Member) or guild.get_member(member.id) is None:
        try:
            member = await guild.fetch_member(member.id)
        except Exception as e:
            logger.warning(f"Failed to fetch full member object for {member.id}: {e}")

    public_channel = guild.get_channel(public_channel_id) if public_channel_id else None
    lead_channel = guild.get_channel(lead_channel_id) if lead_channel_id else None

    # Normalize status for all logic
    old_status = (old_status or '').lower()
    new_status = (new_status or '').lower()

    public_embed = None

    def status_str(s):
        if s == "main": return "**TEST Main**"
        if s == "affiliate": return "**TEST Affiliate**"
        return "*Not a Member*" if s == "non_member" else str(s)

    should_announce_public = (
        (not is_recheck) or
        (is_recheck and old_status != new_status)
    )

    if should_announce_public:
        if new_status == "main":
            public_embed = discord.Embed(
                title="<:test:230176729380028417> <:best:230176763173535745> TEST Membership Update - Main Verified",
                description=random.choice(MAIN_TEMPLATES).format(member=member),
                color=discord.Color.gold()
            )
        elif new_status == "affiliate":
            public_embed = discord.Embed(
                title="<:test:230176729380028417> <:best:230176763173535745> TEST Membership Update - Affiliate Verified",
                description=random.choice(AFFILIATE_TEMPLATES).format(member=member),
                color=discord.Color.yellow()
            )

    if public_channel and public_embed:
        try:
            await channel_send_message(public_channel, content=None, embed=public_embed)
        except Exception as e:
            logger.warning(f"Could not send announcement to public channel: {e}")

    # Leadership/admin channel always logs
    log_action = "re-checked" if is_recheck else "verified"
    admin_phrase = ""

    # Show (AdminName Initiated) only if it's set and not a self-action
    if is_recheck and by_admin and by_admin != member.display_name:
        admin_phrase = f" (**{by_admin}** Initiated)"

    if lead_channel:
        try:
            if is_recheck:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.mention} {log_action}{admin_phrase}: **{status_str(old_status)}** → **{status_str(new_status)}**"
                )
            else:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.mention} verified as {status_str(new_status)}"
                )
        except Exception as e:
            logger.warning(f"Could not send log to leadership channel: {e}")