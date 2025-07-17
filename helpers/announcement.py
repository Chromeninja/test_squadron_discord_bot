# helpers/announcement.py

import discord
from helpers.discord_api import channel_send_message
from helpers.logger import get_logger

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

    # Announce in public channel
    public_message = None

    # Helper for pretty status string
    def status_str(s):
        if s == "main": return "**TEST Main** <:BESTSquad:1332572087524790334>"
        if s == "affiliate": return "**TEST Affiliate**"
        if s == "non_member": return "*Not a Member* :sob:"
        return s

    if not is_recheck:
        # Initial verification
        if new_status == "main":
            public_message = f"🎉 Welcome {member.mention} who has joined TEST as their **MAIN ORG**! <:BESTSquad:1332572087524790334>"
        elif new_status == "affiliate":
            public_message = f"🤝 Welcome {member.mention} who has joined TEST as their **Affiliate ORG**!"
        elif new_status == "non_member":
            public_message = f"👋 Welcome {member.mention} who is **not yet a member of TEST** 😢"
    else:
        # Re-check: compare old and new
        if (old_status in ("affiliate", "non_member") and new_status == "main"):
            public_message = f"🎊 **Congrats** to {member.mention} for setting TEST as their **Main Org!** <:BESTSquad:1332572087524790334>"
        elif (old_status == "main" and new_status == "affiliate"):
            public_message = f"😱 **Shame!** {member.mention} dropped TEST as their **Main Org!**"
        # Affiliate or Main to non_member: no public message

    if public_channel and public_message:
        try:
            await channel_send_message(public_channel, public_message)
        except Exception as e:
            logger.warning(f"Could not send announcement to public channel: {e}")

    # Leadership/admin channel always logs
    log_action = "re-checked" if is_recheck else "verified"
    admin_phrase = " (admin initiated)" if by_admin else ""
    if lead_channel:
        try:
            if is_recheck:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.display_name} {log_action}{admin_phrase}: **{status_str(old_status)}** → **{status_str(new_status)}**"
                )
            else:
                await channel_send_message(
                    lead_channel,
                    f"🗂️ {member.display_name} verified as {status_str(new_status)}"
                )
        except Exception as e:
            logger.warning(f"Could not send log to leadership channel: {e}")
