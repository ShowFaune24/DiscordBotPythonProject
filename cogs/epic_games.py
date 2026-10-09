import os
import discord
from discord.ext import commands, tasks



class EpicGames(commands.Cog):
    def __init__(self, bot, channel_id):
        self.bot = bot
        self.channel_id = channel_id
        

    #bot command 1
    @commands.command(name="freegames")
    async def free_games(self, ctx):
        await ctx.send("Checking Epic Games Store for free deals...")

#Tells dc how to load the cog
async def setup(bot):
    await bot.add_cog(EpicGames(bot))