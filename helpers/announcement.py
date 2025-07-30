# helpers/announcement.py

import discord
import datetime
from discord.ext import tasks
from discord.ext import commands

from helpers.discord_api import channel_send_message
from helpers.logger import get_logger
from helpers.database import Database

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
    lead_channel_id = config['channels'].get('leadership_announcement_channel_id')
    guild = member.guild

    if not isinstance(member, discord.Member) or guild.get_member(member.id) is None:
        try:
            member = await guild.fetch_member(member.id)
        except Exception as e:
            logger.warning(f"Failed to fetch full member object for {member.id}: {e}")

    lead_channel = guild.get_channel(lead_channel_id) if lead_channel_id else None

    old_status = (old_status or '').lower()
    new_status = (new_status or '').lower()

    def status_str(s):
        if s == "main": return "**TEST Main**"
        if s == "affiliate": return "**TEST Affiliate**"
        return "*Not a Member*" if s == "non_member" else str(s)

    log_action = "re-checked" if is_recheck else "verified"
    admin_phrase = ""
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


class DailyBulkAnnouncer(commands.Cog):
    """
    Sends a once-daily bulk welcome for all new 'main' and 'affiliate' members.
    Announcement message is hardcoded here.
    """
    def __init__(self, bot):
        self.bot = bot
        config = bot.config
        bulk_cfg = config.get('bulk_announcement', {})
        hour = bulk_cfg.get('hour_utc', 18)
        minute = bulk_cfg.get('minute_utc', 0)
        self.send_daily_welcome.change_interval(
            time=datetime.time(hour=hour, minute=minute, tzinfo=datetime.timezone.utc)
        )
        self.send_daily_welcome.reconnect = False
        self.send_daily_welcome.start()

    @tasks.loop()
    async def send_daily_welcome(self):
        async with Database.get_connection() as db:
            today_start = int(datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
            main_rows = await db.execute(
                "SELECT user_id FROM verification WHERE membership_status = 'main' AND last_updated >= ?",
                (today_start,)
            )
            affiliate_rows = await db.execute(
                "SELECT user_id FROM verification WHERE membership_status = 'affiliate' AND last_updated >= ?",
                (today_start,)
            )
            mains = [row[0] for row in await main_rows.fetchall()]
            affiliates = [row[0] for row in await affiliate_rows.fetchall()]

        if not mains and not affiliates:
            logger.info("No new TEST Main or Affiliate members to welcome today.")
            return

        channel_id = self.bot.config['channels']['public_announcement_channel_id']
        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.warning("DailyBulkAnnouncer: Could not find public announcement channel.")
            return

        msg_parts = []
        if mains:
            mentions = [channel.guild.get_member(uid).mention for uid in mains if channel.guild.get_member(uid)]
            if mentions:
                msg_parts.append(
                    "🎉 **Welcome the following new members to TEST Main:**\n"
                    f"{chr(10).join(mentions)}\n\n"
                    "You made the best possible decision. 🍻"
                )
        if affiliates:
            mentions = [channel.guild.get_member(uid).mention for uid in affiliates if channel.guild.get_member(uid)]
            if mentions:
                msg_parts.append(
                    "👋 **Welcome our new TEST Affiliates:**\n"
                    f"{chr(10).join(mentions)}\n\n"
                    "Next step: Set TEST as your Main Org for full glory!"
                )

        if msg_parts:
            try:
                await channel.send("\n\n".join(msg_parts))
                logger.info("Daily TEST Main/Affiliate welcome message sent.")
            except Exception as e:
                logger.warning(f"Failed to send daily welcome message: {e}")

    @send_daily_welcome.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()
