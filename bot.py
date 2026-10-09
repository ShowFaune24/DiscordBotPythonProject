import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# 1. Load secret environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = os.getenv('EPIC_CHANNEL_ID')

# 2. Configure bot intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 3. Event when bot comes online
@bot.event
async def on_ready():
    print(f'🤖 Logged in as {bot.user} (ID: {bot.user.id})')

# 4. Load Cogs and start the bot
async def main():
    async with bot:
        await bot.load_extension('cogs.epic_games')
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())