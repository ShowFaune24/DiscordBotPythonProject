# Project Status Briefing: Epic Games Discord Bot (`Shower#2487`)

## 1. Executive Summary

This document outlines the current state, architecture, and ongoing troubleshooting efforts for a Python-based Discord bot (`Shower#2487`). The bot is designed to query the Epic Games Store API and notify users about active 100% free game promotions both on-demand via a prefix command (`!freegames`) and automatically via an hourly background task loop.

## 2. Technical Stack & Environment

* **Language & Runtime**: Python 3.14 (64-bit) on Windows 10/11

* **Core Libraries**:

  * `discord.py` (v2.x) – Bot lifecycle, commands, embeds, and task loops.

  * `aiohttp` – Asynchronous HTTP client for API polling.

  * `python-dotenv` – Environment variable management (`.env`).

* **Bot Architecture**:

  * `bot.py` – Entry point, initializes `commands.Bot` with `Message Content` intents, loads cogs.

  * `cogs/epic_games.py` – Implements `EpicGames(commands.Cog)` handling API fetching, JSON parsing, Discord embed construction, and `@tasks.loop(hours=1)`.

## 3. Current Implementation State

### ✅ Resolved Components

1. **Discord Portal & Bot Authentication**:

   * Application created in Discord Developer Portal.

   * `Message Content Intent` and standard gateway permissions enabled.

   * Connection to Discord WS gateway successful.

2. **Cog & Event Loop Lifecycle**:

   * Cog dynamic loading via `bot.load_extension("cogs.epic_games")` corrected.

   * `before_loop` logic attached to `@tasks.loop` using `await self.bot.wait_until_ready()` to avoid posting before gateway handshake completes.

3. **Response Embed Formatting**:

   * Standardized `discord.Embed` layout displaying game title, store link, promotional description, and hero banner image (`keyImages`).

## 4. Current Blocking Issues & Technical Analysis

### Issue A: Cloudflare Anti-Scraping / Bot Detection (HTTP 403 Forbidden)

* **Symptom**: `aiohttp` requests returned `Status 403`.

* **Root Cause**: Akamai and Cloudflare edge servers block automated Python user-agents (`Python/3.x aiohttp/3.x`).

* **Fix Applied**: Configured browser-identical request headers:

  ```
  self.headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "en-US,en;q=0.9",
  }
  
  ```

### Issue B: Host URL Routing (HTTP 404 Not Found)

* **Symptom**: Requests to `https://store.epicgames.com/freeGamesPromotions` returned `Status 404`.

* **Root Cause**: The API path `/freeGamesPromotions` is not exposed on Epic's main web domain, but rather hosted on Akamai's static backend CDN domain.

* **Fix Applied**: Standardized API target back to official backend:
  `https://store-site-backend-static-ipv4.akamaized.net/freeGamesPromotions?locale=en-US&country=US&allowCountries=US`

### Issue C: DNS Resolution Failure (`getaddrinfo failed`) — ✅ *RESOLVED*

* **Symptom**:
  ```
  Cannot connect to host store-site-backend-static-ipv4.akamaized.net:443
  ssl:default [getaddrinfo failed]
  ```

* **Root Cause**: The domain `store-site-backend-static-ipv4.akamaized.net` does not exist on DNS (`NXDOMAIN`). The correct, functional Epic Games Store CDN endpoint is `store-site-backend-static.ak.epicgames.com` (or `store-site-backend-static-ipv4.ak.epicgames.com`).
  * Manual DoH attempts had failed previously due to TLS SNI certificate mismatch (Akamai edge certs cover `*.epicgames.com`, not `*.akamaized.net`).

* **Fix Applied**: Target the actual Epic Games CDN domain:
  `https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US`
  Verified: Resolves across all DNS servers and returns HTTP 200 with catalog data.

### Issue D: Windows Console Unicode Encoding Crash — ✅ *RESOLVED*

* **Symptom**: `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f916'`
* **Root Cause**: Default Windows console code page (`cp1252`) fails on emoji logging (`🤖`, `❌`, `🎁`).
* **Fix Applied**: Reconfigure `sys.stdout` and `sys.stderr` to UTF-8 on Windows.

## 5. Next Steps & Implementation Options

See [TECHNICAL_INVESTIGATION_REPORT.md](file:///d:/Prog/PythonProjects/DiscrodBot/DiscordBotPythonProject/TECHNICAL_INVESTIGATION_REPORT.md) for full diagnostic logs, architecture analysis, and implementation options (deduplication of hourly announcements, enriched Discord embeds with end timestamps, and optional upcoming games command).