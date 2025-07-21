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
    by_admin: bool = False
):
    config = bot.config
    public_channel_id = config['channels'].get('public_announcement_channel_id')
    lead_channel_id = config['channels'].get('leadership_announcement_channel_id')
    guild = member.guild

    public_channel = guild.get_channel(public_channel_id) if public_channel_id else None
    lead_channel = guild.get_channel(lead_channel_id) if lead_channel_id else None

    # Normalize status for all logic
    old_status = (old_status or '').lower()
    new_status = (new_status or '').lower()

    public_message = None

    # Helper for pretty status string
    def status_str(s):
        if s == "main": return "**TEST Main**"
        if s == "affiliate": return "**TEST Affiliate**"
        if s == "non_member": return "*Not a Member*"
        return str(s)

    if new_status == "main":
        public_message = random.choice(MAIN_TEMPLATES).format(member=member)
    elif new_status == "affiliate":
        public_message = random.choice(AFFILIATE_TEMPLATES).format(member=member)

    if public_channel and public_message:
        try:
            await channel_send_message(public_channel, public_message)
        except Exception as e:
            logger.warning(f"Could not send announcement to public channel: {e}")

    # Leadership/admin channel always logs
    log_action = "re-checked" if is_recheck else "verified"
    admin_phrase = f" (**{by_admin}** Initiated)" if isinstance(by_admin, str) and by_admin else (" (admin initiated)" if by_admin else "")
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
