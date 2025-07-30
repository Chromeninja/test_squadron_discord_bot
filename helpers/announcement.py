# helpers/announcement.py

import discord
import datetime
from discord.ext import tasks, commands

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
        # Validate hour and minute
        try:
            hour = int(bulk_cfg.get('hour_utc', 18))
            if not (0 <= hour < 24):
                raise ValueError
        except Exception:
            logger.warning("Invalid hour_utc in config. Falling back to 18.")
            hour = 18
        try:
            minute = int(bulk_cfg.get('minute_utc', 0))
            if not (0 <= minute < 60):
                raise ValueError
        except Exception:
            logger.warning("Invalid minute_utc in config. Falling back to 0.")
            minute = 0
        self.send_daily_welcome.change_interval(
            time=datetime.time(hour=hour, minute=minute, tzinfo=datetime.timezone.utc)
        )
        self.send_daily_welcome.reconnect = False
        self.send_daily_welcome.start()

    def cog_unload(self):
        self.send_daily_welcome.cancel()

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

        channel_id = self.bot.config['channels'].get('public_announcement_channel_id')
        if not channel_id:
            logger.warning("DailyBulkAnnouncer: public_announcement_channel_id missing in config.")
            return
        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.warning("DailyBulkAnnouncer: Could not find public announcement channel.")
            return

        # Message batching (80 mentions per message max)
        MAX_MENTIONS_PER_MESSAGE = 80

        # Main members batching
        if mains:
            mentions = [channel.guild.get_member(uid).mention for uid in mains if channel.guild.get_member(uid)]
            for i in range(0, len(mentions), MAX_MENTIONS_PER_MESSAGE):
                batch = mentions[i:i+MAX_MENTIONS_PER_MESSAGE]
                msg = (
                    "🎉 **Welcome the following new members to TEST Main:**\n"
                    f"{chr(10).join(batch)}\n\n"
                    "You made the best possible decision. 🍻"
                )
                try:
                    await channel.send(msg)
                    logger.info(f"Daily TEST Main welcome message sent for batch {i//MAX_MENTIONS_PER_MESSAGE + 1}.")
                except Exception as e:
                    logger.warning(f"Failed to send daily main welcome message batch {i//MAX_MENTIONS_PER_MESSAGE + 1}: {e}")

        # Affiliate members batching
        if affiliates:
            mentions = [channel.guild.get_member(uid).mention for uid in affiliates if channel.guild.get_member(uid)]
            for i in range(0, len(mentions), MAX_MENTIONS_PER_MESSAGE):
                batch = mentions[i:i+MAX_MENTIONS_PER_MESSAGE]
                msg = (
                    "👋 **Welcome our new TEST Affiliates:**\n"
                    f"{chr(10).join(batch)}\n\n"
                    "Next step: Set TEST as your Main Org for full glory!"
                )
                try:
                    await channel.send(msg)
                    logger.info(f"Daily TEST Affiliate welcome message sent for batch {i//MAX_MENTIONS_PER_MESSAGE + 1}.")
                except Exception as e:
                    logger.warning(f"Failed to send daily affiliate welcome message batch {i//MAX_MENTIONS_PER_MESSAGE + 1}: {e}")

    @send_daily_welcome.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()
