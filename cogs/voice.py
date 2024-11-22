# cogs/voice.py

import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import time  # For timestamp handling

from config.config_loader import ConfigLoader
from helpers.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

class Voice(commands.GroupCog, name="voice"):
    """
    Cog for managing dynamic voice channels.
    """

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = ConfigLoader.load_config()
        self.database_path = self.config['voice'].get('database_path', 'voice.db')
        self.bot_admin_role_ids = [int(role_id) for role_id in self.config['roles'].get('bot_admins', [])]
        self.cooldown_seconds = self.config['voice'].get('cooldown_seconds', 60)  # Default to 60 seconds if not set
        self.bot.loop.create_task(self.initialize_database())

    async def initialize_database(self):
        """
        Initializes the database tables if they don't exist.
        """
        try:
            async with aiosqlite.connect(self.database_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS guild (
                        guildID BIGINT PRIMARY KEY,
                        ownerID BIGINT NOT NULL,
                        voiceChannelID BIGINT NOT NULL,
                        voiceCategoryID BIGINT NOT NULL
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS voiceChannel (
                        userID BIGINT PRIMARY KEY,
                        voiceID BIGINT NOT NULL
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS userSettings (
                        userID BIGINT PRIMARY KEY,
                        channelName TEXT NOT NULL,
                        channelLimit INTEGER NOT NULL
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS guildSettings (
                        guildID BIGINT PRIMARY KEY,
                        channelName TEXT NOT NULL,
                        channelLimit INTEGER NOT NULL
                    )
                """)
                # New table for cooldowns
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS voiceCooldowns (
                        userID BIGINT PRIMARY KEY,
                        lastCreated TIMESTAMP NOT NULL
                    )
                """)
                await db.commit()
                logger.info("VoiceMaster database initialized.")
        except Exception as e:
            logger.exception(f"Failed to initialize VoiceMaster database: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """
        Listener for voice state updates to create and delete dynamic voice channels.
        """
        if after.channel is None:
            return  # User left a voice channel

        async with aiosqlite.connect(self.database_path) as db:
            guild_id = member.guild.id
            cursor = await db.execute("SELECT voiceChannelID FROM guild WHERE guildID = ?", (guild_id,))
            row = await cursor.fetchone()
            if row is None:
                return  # No setup for this guild
            voice_channel_id = row[0]

            if after.channel.id != voice_channel_id:
                return  # Not the designated voice channel

            # Check for cooldown
            current_time = int(time.time())
            cursor = await db.execute("SELECT lastCreated FROM voiceCooldowns WHERE userID = ?", (member.id,))
            cooldown_row = await cursor.fetchone()
            if cooldown_row:
                last_created = cooldown_row[0]
                elapsed_time = current_time - last_created
                if elapsed_time < self.cooldown_seconds:
                    remaining_time = self.cooldown_seconds - elapsed_time
                    try:
                        await member.send(f"You're creating channels too quickly. Please wait {remaining_time} seconds.")
                    except discord.Forbidden:
                        logger.warning(f"Cannot send DM to {member.display_name}.")
                    return

            # Fetch settings
            cursor = await db.execute("SELECT voiceCategoryID FROM guild WHERE guildID = ?", (guild_id,))
            row = await cursor.fetchone()
            if row is None:
                logger.error(f"No category ID found for guild {guild_id}")
                return
            category_id = row[0]
            category = self.bot.get_channel(category_id)

            # Fetch user settings
            cursor = await db.execute("SELECT channelName, channelLimit FROM userSettings WHERE userID = ?", (member.id,))
            user_setting = await cursor.fetchone()
            if user_setting:
                channel_name, channel_limit = user_setting
            else:
                # Fetch guild default settings
                cursor = await db.execute("SELECT channelLimit FROM guildSettings WHERE guildID = ?", (guild_id,))
                guild_setting = await cursor.fetchone()
                channel_name = f"{member.display_name}'s Channel"
                channel_limit = guild_setting[0] if guild_setting else 0  # Default limit

            # Create voice channel
            try:
                new_channel = await member.guild.create_voice_channel(
                    name=channel_name,
                    category=category
                )
                await new_channel.set_permissions(member, manage_channels=True, connect=True)
                await member.move_to(new_channel)
                await new_channel.edit(user_limit=channel_limit)
                await db.execute("INSERT INTO voiceChannel (userID, voiceID) VALUES (?, ?)", (member.id, new_channel.id))

                # Update cooldown
                await db.execute("""
                    INSERT OR REPLACE INTO voiceCooldowns (userID, lastCreated)
                    VALUES (?, ?)
                """, (member.id, current_time))

                await db.commit()
                logger.info(f"Created voice channel '{new_channel.name}' for {member.display_name}")

                # Wait until the channel is empty
                def check(a, b, c):
                    return len(new_channel.members) == 0

                await self.bot.wait_for('voice_state_update', check=check)
                await new_channel.delete()
                await db.execute("DELETE FROM voiceChannel WHERE userID = ?", (member.id,))
                await db.commit()
                logger.info(f"Deleted voice channel '{new_channel.name}'")
            except Exception as e:
                logger.exception(f"Error creating voice channel for {member.display_name}: {e}")

    # Define your subcommands within the 'voice' group
    @app_commands.command(name="setup", description="Set up the voice channel system")
    @app_commands.guild_only()
    async def setup_voice(self, interaction: discord.Interaction):
        """
        Sets up the voice channel system in the guild.
        """
        logger.debug(f"Received /voice setup command from {interaction.user.display_name} in guild '{interaction.guild.name}'")
        guild = interaction.guild
        member = interaction.user
        if not guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        # Updated permission check: Only bot admins can set up
        if not any(role.id in self.bot_admin_role_ids for role in member.roles):
            logger.warning(f"{member.display_name} attempted to execute a bot admin command without proper roles.")
            await interaction.response.send_message("Only bot admins can set up the bot.", ephemeral=True)
            return

        await interaction.response.send_message("Starting setup...", ephemeral=True)

        # Create category
        try:
            category_name = self.config['voice'].get('default_category_name', "Voice Channels")
            category = await guild.create_category_channel(category_name)
            logger.info(f"Created category '{category_name}' in guild '{guild.name}'")
        except Exception as e:
            logger.exception(f"Error creating category in guild '{guild.name}': {e}")
            await interaction.followup.send("Failed to create category. Please ensure the bot has the necessary permissions.", ephemeral=True)
            return

        # Create voice channel
        try:
            voice_channel_name = "Join to Create"
            voice_channel = await guild.create_voice_channel(voice_channel_name, category=category)
            logger.info(f"Created voice channel '{voice_channel_name}' in guild '{guild.name}'")
        except Exception as e:
            logger.exception(f"Error creating voice channel in guild '{guild.name}': {e}")
            await interaction.followup.send("Failed to create voice channel. Please ensure the bot has the necessary permissions.", ephemeral=True)
            return

        # Save to database
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO guild (guildID, ownerID, voiceChannelID, voiceCategoryID)
                VALUES (?, ?, ?, ?)
            """, (guild.id, guild.owner_id, voice_channel.id, category.id))
            await db.commit()

        await interaction.followup.send("Setup complete!", ephemeral=True)

    @app_commands.command(name="lock", description="Lock your voice channel")
    @app_commands.guild_only()
    async def lock_voice(self, interaction: discord.Interaction):
        """
        Locks the user's voice channel.
        """
        logger.debug(f"Received /voice lock command from {interaction.user.display_name} in guild '{interaction.guild.name}'")
        member = interaction.user
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (member.id,))
            row = await cursor.fetchone()
            if row is None:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return
            channel_id = row[0]
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.set_permissions(interaction.guild.default_role, connect=False)
                await interaction.response.send_message("Your voice channel has been locked.", ephemeral=True)
                logger.info(f"{member.display_name} locked their voice channel.")
            else:
                await interaction.response.send_message("Channel not found.", ephemeral=True)

    @app_commands.command(name="unlock", description="Unlock your voice channel")
    @app_commands.guild_only()
    async def unlock_voice(self, interaction: discord.Interaction):
        """
        Unlocks the user's voice channel.
        """
        logger.debug(f"Received /voice unlock command from {interaction.user.display_name} in guild '{interaction.guild.name}'")
        member = interaction.user
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (member.id,))
            row = await cursor.fetchone()
            if row is None:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return
            channel_id = row[0]
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.set_permissions(interaction.guild.default_role, connect=True)
                await interaction.response.send_message("Your voice channel has been unlocked.", ephemeral=True)
                logger.info(f"{member.display_name} unlocked their voice channel.")
            else:
                await interaction.response.send_message("Channel not found.", ephemeral=True)

    @app_commands.command(name="name", description="Change your voice channel's name")
    @app_commands.guild_only()
    @app_commands.describe(name="The new name for your voice channel")
    async def rename_voice(self, interaction: discord.Interaction, name: str):
        """
        Changes the user's voice channel name.
        """
        logger.debug(f"Received /voice name command from {interaction.user.display_name} in guild '{interaction.guild.name}' with new name '{name}'")
        member = interaction.user
        if len(name) > 100:
            await interaction.response.send_message("Channel name must be less than 100 characters.", ephemeral=True)
            return
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (member.id,))
            row = await cursor.fetchone()
            if row is None:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return
            channel_id = row[0]
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.edit(name=name)
                await interaction.response.send_message(f"Your voice channel name has been changed to '{name}'.", ephemeral=True)
                logger.info(f"{member.display_name} changed their voice channel name to '{name}'.")

                # Update user settings
                await db.execute("""
                    INSERT OR REPLACE INTO userSettings (userID, channelName, channelLimit)
                    VALUES (?, ?, COALESCE((SELECT channelLimit FROM userSettings WHERE userID = ?), 0))
                """, (member.id, name, member.id))
                await db.commit()
            else:
                await interaction.response.send_message("Channel not found.", ephemeral=True)

    @app_commands.command(name="limit", description="Set user limit for your voice channel")
    @app_commands.guild_only()
    @app_commands.describe(limit="The user limit for your voice channel (0 for unlimited)")
    async def set_limit_voice(self, interaction: discord.Interaction, limit: int):
        """
        Sets the user limit for the user's voice channel.
        """
        logger.debug(f"Received /voice limit command from {interaction.user.display_name} in guild '{interaction.guild.name}' with limit '{limit}'")
        member = interaction.user
        if limit < 0 or limit > 99:
            await interaction.response.send_message("User limit must be between 0 and 99.", ephemeral=True)
            return
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (member.id,))
            row = await cursor.fetchone()
            if row is None:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return
            channel_id = row[0]
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.edit(user_limit=limit)
                await interaction.response.send_message(f"Your voice channel user limit has been set to {limit}.", ephemeral=True)
                logger.info(f"{member.display_name} set their voice channel limit to {limit}.")

                # Update user settings
                await db.execute("""
                    INSERT OR REPLACE INTO userSettings (userID, channelName, channelLimit)
                    VALUES (?, COALESCE((SELECT channelName FROM userSettings WHERE userID = ?), ?), ?)
                """, (member.id, member.id, f"{member.display_name}'s Channel", limit))
                await db.commit()
            else:
                await interaction.response.send_message("Channel not found.", ephemeral=True)

    @app_commands.command(name="permit", description="Permit a user to join your locked voice channel")
    @app_commands.guild_only()
    @app_commands.describe(member="The member to permit")
    async def permit_user_voice(self, interaction: discord.Interaction, member: discord.Member):
        """
        Permits a user to join the user's locked voice channel.
        """
        logger.debug(f"Received /voice permit command from {interaction.user.display_name} in guild '{interaction.guild.name}' for member '{member.display_name}'")
        owner = interaction.user
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (owner.id,))
            row = await cursor.fetchone()
            if row is None:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return
            channel_id = row[0]
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.set_permissions(member, connect=True)
                await interaction.response.send_message(f"{member.display_name} has been permitted to join your channel.", ephemeral=True)
                logger.info(f"{owner.display_name} permitted {member.display_name} to join their voice channel.")
            else:
                await interaction.response.send_message("Channel not found.", ephemeral=True)

    @app_commands.command(name="reject", description="Reject a user from your voice channel")
    @app_commands.guild_only()
    @app_commands.describe(member="The member to reject")
    async def reject_user_voice(self, interaction: discord.Interaction, member: discord.Member):
        """
        Rejects a user from the user's voice channel.
        """
        logger.debug(f"Received /voice reject command from {interaction.user.display_name} in guild '{interaction.guild.name}' for member '{member.display_name}'")
        owner = interaction.user
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (owner.id,))
            row = await cursor.fetchone()
            if row is None:
                await interaction.response.send_message("You don't own a channel.", ephemeral=True)
                return
            channel_id = row[0]
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.set_permissions(member, connect=False)
                if member in channel.members:
                    try:
                        await member.move_to(None)
                    except Exception as e:
                        logger.exception(f"Error moving {member.display_name} out of the channel: {e}")
                await interaction.response.send_message(f"{member.display_name} has been rejected from your channel.", ephemeral=True)
                logger.info(f"{owner.display_name} rejected {member.display_name} from their voice channel.")
            else:
                await interaction.response.send_message("Channel not found.", ephemeral=True)

    @app_commands.command(name="claim", description="Claim ownership of a voice channel")
    @app_commands.guild_only()
    async def claim_voice(self, interaction: discord.Interaction):
        """
        Claims ownership of a voice channel if the original owner left.
        """
        logger.debug(f"Received /voice claim command from {interaction.user.display_name} in guild '{interaction.guild.name}'")
        member = interaction.user
        voice_state = member.voice
        if not voice_state or not voice_state.channel:
            await interaction.response.send_message("You're not in a voice channel.", ephemeral=True)
            return
        channel = voice_state.channel

        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("SELECT userID FROM voiceChannel WHERE voiceID = ?", (channel.id,))
            row = await cursor.fetchone()
            if row is None:
                await interaction.response.send_message("This channel cannot be claimed.", ephemeral=True)
                return
            owner_id = row[0]
            if owner_id == member.id:
                await interaction.response.send_message("You already own this channel.", ephemeral=True)
                return
            owner_in_channel = any(user.id == owner_id for user in channel.members)
            if owner_in_channel:
                await interaction.response.send_message("The owner is still in the channel.", ephemeral=True)
                return
            # Transfer ownership
            await db.execute("UPDATE voiceChannel SET userID = ? WHERE voiceID = ?", (member.id, channel.id))
            await db.commit()
            await interaction.response.send_message("You have claimed ownership of the channel.", ephemeral=True)
            logger.info(f"{member.display_name} claimed ownership of channel '{channel.name}'")

    @app_commands.command(name="unclaim", description="Unclaim your currently claimed voice channel")
    @app_commands.guild_only()
    async def unclaim_voice(self, interaction: discord.Interaction):
        """
        Unclaims any voice channels currently claimed by the user.
        """
        logger.debug(f"Received /voice unclaim command from {interaction.user.display_name} in guild '{interaction.guild.name}'")
        member = interaction.user
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (member.id,))
            rows = await cursor.fetchall()
            if not rows:
                await interaction.response.send_message("You don't have any claimed voice channels.", ephemeral=True)
                return

            for row in rows:
                channel_id = row[0]
                channel = self.bot.get_channel(channel_id)
                if channel:
                    if len(channel.members) == 0:
                        try:
                            await channel.delete()
                            await db.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (channel_id,))
                            await db.commit()
                            logger.info(f"Deleted unclaimed empty voice channel '{channel.name}' for {member.display_name}")
                        except Exception as e:
                            logger.exception(f"Error deleting voice channel '{channel.name}': {e}")
                    else:
                        await interaction.response.send_message(f"Cannot unclaim channel '{channel.name}' because it is not empty.", ephemeral=True)
                        logger.info(f"{member.display_name} attempted to unclaim non-empty channel '{channel.name}'")
                        return
                else:
                    await db.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (channel_id,))
                    await db.commit()
                    logger.warning(f"Channel with ID {channel_id} not found. Removed from database.")
            await interaction.response.send_message("All your claimed voice channels have been unclaimed and deleted if empty.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Voice(bot))
    logger.info("Voice cog loaded.")
