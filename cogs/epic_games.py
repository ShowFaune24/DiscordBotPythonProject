import os
import json
import logging
from datetime import datetime, timezone
import aiohttp
import discord
from discord.ext import commands, tasks

logger = logging.getLogger("epic_games")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "posted_promotions.json")


class GameLinkView(discord.ui.View):
    """Interactive Discord UI View with a direct link button to the store page."""

    def __init__(self, url: str):
        super().__init__(timeout=None)
        if url:
            self.add_item(
                discord.ui.Button(
                    label="Claim on Epic Games Store",
                    url=url,
                    style=discord.ButtonStyle.link,
                    emoji="🛒",
                )
            )


class EpicGames(commands.Cog):
    """Cog for querying and notifying about Epic Games Store free promotions."""

    def __init__(self, bot):
        self.bot = bot

        channel_env = os.getenv("EPIC_CHANNEL_ID")
        self.channel_id = int(channel_env) if channel_env and channel_env.isdigit() else None
        if not self.channel_id:
            print("⚠️ Warning: EPIC_CHANNEL_ID is not configured properly in .env.")

        # Official backend CDN endpoint (resolves via Akamai edge to Epic Games)
        self.api_url = (
            "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
            "?locale=en-US&country=US&allowCountries=US"
        )
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

        self.posted_promotions = self._load_cache()

    async def cog_load(self):
        self.check_games.start()

    async def cog_unload(self):
        self.check_games.cancel()

    # ---------------------------------------------------------
    # Cache Persistence (Prevents Hourly Loop Spam)
    # ---------------------------------------------------------
    def _load_cache(self) -> dict:
        """Loads previously posted promotions from disk."""
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Could not load cache: {e}")
        return {}

    def _save_cache(self):
        """Saves current promotions cache to disk."""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.posted_promotions, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save cache: {e}")

    def _prune_cache(self, now: datetime):
        """Removes expired promotions from the cache."""
        expired = []
        for key, end_iso in self.posted_promotions.items():
            if end_iso:
                try:
                    end_dt = datetime.fromisoformat(end_iso)
                    if end_dt <= now:
                        expired.append(key)
                except Exception:
                    pass
        for key in expired:
            del self.posted_promotions[key]

    # ---------------------------------------------------------
    # API Data Fetching & Parsing
    # ---------------------------------------------------------
    async def fetch_games_data(self):
        """Fetches both active and upcoming free games from Epic Games API."""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(self.api_url) as response:
                    if response.status != 200:
                        print(f"❌ API HTTP Error: Status {response.status}")
                        return [], []

                    data = await response.json()
                    elements = (
                        data.get("data", {})
                        .get("Catalog", {})
                        .get("searchStore", {})
                        .get("elements", [])
                    )

                    now = datetime.now(timezone.utc)
                    active_games = []
                    upcoming_games = []

                    for game in elements:
                        title = game.get("title", "Unknown Title")
                        promotions = game.get("promotions")
                        if not promotions:
                            continue

                        price_data = game.get("price", {}).get("totalPrice", {})
                        fmt_price = price_data.get("fmtPrice", {}).get("originalPrice")
                        if not fmt_price and price_data.get("originalPrice"):
                            fmt_price = f"${price_data.get('originalPrice') / 100:.2f}"
                        if not fmt_price or fmt_price == "0":
                            fmt_price = "Free"

                        discount_price = price_data.get("discountPrice", 0)

                        # Determine image
                        banner = None
                        thumbnail = None
                        for img in game.get("keyImages", []):
                            img_type = img.get("type")
                            img_url = img.get("url")
                            if not img_url:
                                continue
                            if img_type in ("OfferImageWide", "DieselStoreFrontWide"):
                                banner = img_url
                            elif img_type in ("Thumbnail", "OfferImageTall", "VaultClosed"):
                                thumbnail = img_url
                        display_image = banner or thumbnail

                        # Determine store URL
                        slug = game.get("productSlug")
                        if not slug and game.get("offerMappings"):
                            for m in game.get("offerMappings", []):
                                if m.get("pageSlug"):
                                    slug = m.get("pageSlug")
                                    break
                        if not slug and game.get("catalogNs", {}).get("mappings"):
                            for m in game.get("catalogNs", {}).get("mappings", []):
                                if m.get("pageSlug"):
                                    slug = m.get("pageSlug")
                                    break
                        if not slug:
                            slug = game.get("urlSlug")

                        store_url = (
                            f"https://store.epicgames.com/p/{slug}"
                            if slug
                            else "https://store.epicgames.com"
                        )

                        description = game.get("description", "No description available.")
                        if len(description) > 1000:
                            description = description[:997] + "..."

                        # 1. Check Active Promotions
                        promotional_offers = promotions.get("promotionalOffers", [])
                        is_active = False
                        for group in promotional_offers:
                            for offer in group.get("promotionalOffers", []):
                                discount = offer.get("discountSetting", {})
                                if discount_price == 0 or discount.get("discountPercentage") == 0:
                                    start_str = offer.get("startDate")
                                    end_str = offer.get("endDate")
                                    start_dt = (
                                        datetime.fromisoformat(start_str) if start_str else None
                                    )
                                    end_dt = datetime.fromisoformat(end_str) if end_str else None

                                    if (not start_dt or start_dt <= now) and (
                                        not end_dt or end_dt > now
                                    ):
                                        active_games.append(
                                            {
                                                "id": game.get("id"),
                                                "title": title,
                                                "description": description,
                                                "original_price": fmt_price,
                                                "url": store_url,
                                                "image": display_image,
                                                "end_date_iso": end_str,
                                                "end_timestamp": int(end_dt.timestamp())
                                                if end_dt
                                                else None,
                                            }
                                        )
                                        is_active = True
                                        break
                            if is_active:
                                break

                        # 2. Check Upcoming Promotions
                        if not is_active:
                            upcoming_offers = promotions.get("upcomingPromotionalOffers", [])
                            for group in upcoming_offers:
                                for offer in group.get("promotionalOffers", []):
                                    discount = offer.get("discountSetting", {})
                                    if discount.get("discountPercentage") == 0:
                                        start_str = offer.get("startDate")
                                        end_str = offer.get("endDate")
                                        start_dt = (
                                            datetime.fromisoformat(start_str) if start_str else None
                                        )
                                        end_dt = (
                                            datetime.fromisoformat(end_str) if end_str else None
                                        )

                                        if start_dt and start_dt > now:
                                            upcoming_games.append(
                                                {
                                                    "id": game.get("id"),
                                                    "title": title,
                                                    "description": description,
                                                    "original_price": fmt_price,
                                                    "url": store_url,
                                                    "image": display_image,
                                                    "start_date_iso": start_str,
                                                    "start_timestamp": int(start_dt.timestamp())
                                                    if start_dt
                                                    else None,
                                                    "end_timestamp": int(end_dt.timestamp())
                                                    if end_dt
                                                    else None,
                                                }
                                            )
                                            break

                    print(
                        f"🤖 Debug: Successfully parsed {len(active_games)} active, "
                        f"{len(upcoming_games)} upcoming free game(s)."
                    )
                    return active_games, upcoming_games
            except Exception as e:
                print(f"❌ Error fetching games: {e}")
                return [], []

    # ---------------------------------------------------------
    # Embed Builders
    # ---------------------------------------------------------
    def create_active_embed(self, game: dict) -> discord.Embed:
        """Constructs a Discord embed for an active 100% free game."""
        embed = discord.Embed(
            title=f"🎁 FREE NOW: {game['title']}",
            description=game["description"],
            url=game["url"],
            color=discord.Color.from_rgb(0, 120, 242),  # Epic Games blue
        )

        orig_price = game.get("original_price", "N/A")
        price_display = f"~~{orig_price}~~ ➔ **FREE**" if orig_price != "Free" else "**FREE**"
        embed.add_field(name="💰 Price", value=price_display, inline=True)

        if game.get("end_timestamp"):
            end_ts = game["end_timestamp"]
            embed.add_field(
                name="⏰ Free Until",
                value=f"<t:{end_ts}:F>\n(<t:{end_ts}:R>)",
                inline=True,
            )

        if game.get("image"):
            embed.set_image(url=game["image"])

        embed.set_footer(text="Epic Games Store • 100% Free Limited Time Promotion")
        return embed

    def create_upcoming_embed(self, game: dict) -> discord.Embed:
        """Constructs a Discord embed for an upcoming free game."""
        embed = discord.Embed(
            title=f"⏳ COMING SOON: {game['title']}",
            description=game["description"],
            url=game["url"],
            color=discord.Color.gold(),
        )

        orig_price = game.get("original_price", "N/A")
        embed.add_field(name="💰 Regular Price", value=orig_price, inline=True)

        if game.get("start_timestamp"):
            start_ts = game["start_timestamp"]
            embed.add_field(
                name="📅 Free Starting",
                value=f"<t:{start_ts}:F>\n(<t:{start_ts}:R>)",
                inline=True,
            )

        if game.get("image"):
            embed.set_image(url=game["image"])

        embed.set_footer(text="Epic Games Store • Upcoming Free Game Promotion")
        return embed

    # ---------------------------------------------------------
    # Discord Commands
    # ---------------------------------------------------------
    @commands.command(name="freegames", aliases=["free", "games"])
    async def free_games(self, ctx):
        """Displays all currently active free games on Epic Games Store."""
        await ctx.send("🔍 Checking Epic Games Store for active free games...")
        active_games, _ = await self.fetch_games_data()

        if active_games:
            for game in active_games:
                embed = self.create_active_embed(game)
                view = GameLinkView(game["url"])
                await ctx.send(embed=embed, view=view)
        else:
            await ctx.send("No 100% free games currently found on Epic Games Store.")

    @commands.command(name="upcoming", aliases=["nextfree"])
    async def upcoming_games(self, ctx):
        """Displays upcoming free games scheduled for next week."""
        await ctx.send("🔍 Checking Epic Games Store for upcoming free games...")
        _, upcoming_games = await self.fetch_games_data()

        if upcoming_games:
            for game in upcoming_games:
                embed = self.create_upcoming_embed(game)
                view = GameLinkView(game["url"])
                await ctx.send(embed=embed, view=view)
        else:
            await ctx.send("No upcoming free games announced right now on Epic Games Store.")

    # ---------------------------------------------------------
    # Background Hourly Task Loop (Deduplicated)
    # ---------------------------------------------------------
    @tasks.loop(hours=1)
    async def check_games(self):
        """Checks for new free games every hour and posts only unannounced promotions."""
        if not self.channel_id:
            return

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(self.channel_id)
            except Exception as e:
                print(f"❌ Failed to fetch channel {self.channel_id}: {e}")
                return

        now = datetime.now(timezone.utc)
        self._prune_cache(now)

        active_games, _ = await self.fetch_games_data()
        new_posted = 0

        for game in active_games:
            promo_key = f"{game['id']}_{game.get('end_date_iso', '')}"

            if promo_key not in self.posted_promotions:
                embed = self.create_active_embed(game)
                view = GameLinkView(game["url"])
                await channel.send(
                    content="🎉 **New Free Game Alert on Epic Games Store!**",
                    embed=embed,
                    view=view,
                )
                self.posted_promotions[promo_key] = game.get("end_date_iso")
                new_posted += 1

        if new_posted > 0:
            self._save_cache()
            print(f"✅ Hourly Check: Announced {new_posted} new free game promotion(s).")
        else:
            print("ℹ️ Hourly Check: No new free promotions to announce.")

    @check_games.before_loop
    async def before_check_games(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(EpicGames(bot))