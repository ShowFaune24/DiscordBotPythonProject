import os
import sys
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Ensure UTF-8 console output on Windows terminals
if sys.platform == "win32":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

# 1. Load secret environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("EPIC_CHANNEL_ID")

if not TOKEN:
    print("❌ Fatal Error: DISCORD_TOKEN is missing in .env file.")
    sys.exit(1)

# 2. Configure bot intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 3. Events when bot connects
@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Epic Games Store | !freegames"
        )
    )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"❌ Command Error in '{ctx.command}': {error}")
    await ctx.send(f"⚠️ Error executing command: {error}")

# 4. Load Cogs and start the bot
async def main():
    async with bot:
        await bot.load_extension("cogs.epic_games")
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())