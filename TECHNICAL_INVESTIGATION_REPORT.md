# Epic Games Discord Bot: Technical Investigation & Status Report

**Date**: 2026-10-10  
**Bot Identity**: `Shower#2487` (Application ID: `1558207822531919872`)  
**Target Channel**: `1558247985132085390` (`#epicgames🤖`)  

---

## 1. Executive Summary

We conducted a root-cause diagnosis of the active blocker documented in `project_status_technical_briefing.md` and verified all components of the Discord bot. 

### Key Findings:
1. **The DNS resolution blocker (Issue C) was caused by an incorrect domain name**:
   - The code had targeted `store-site-backend-static-ipv4.akamaized.net`.
   - Direct DNS queries to ISP DNS, Google DNS (`8.8.8.8`), and Cloudflare (`1.1.1.1`) all confirmed that this domain does **not exist** (`NXDOMAIN`).
   - The correct and operational Epic Games Store CDN endpoint is:  
     `https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US`
   - This endpoint resolves immediately, passes TLS verification, and returns HTTP 200 with active promotion data.
2. **A secondary blocker was identified on Windows**:
   - Console logs containing Unicode emojis (`🤖`, `❌`, `🎁`) crashed the Python runtime with `UnicodeEncodeError: 'charmap' codec can't encode character` under the default Windows console code page (`cp1252`).
3. **Bot Gateway Authentication is 100% verified**:
   - Using the token in `.env`, the bot successfully handshakes with Discord Gateway, authenticates as `Shower#2487`, and resolves channel `#epicgames🤖`.
4. **Architectural issues in the background loop were identified**:
   - The hourly `@tasks.loop(hours=1)` currently sends messages unconditionally every hour. Because free games run for 7 days, the channel would receive identical duplicate alerts 168 times a week without a deduplication cache.

---

## 2. Detailed Technical Breakdown of What Was Tested

### Test 1: DNS Resolution Verification (Issue C)
* **Hypothesis in Briefing**: Local ISP DNS was failing to resolve Akamai subdomains.
* **Test Performed**:
  ```powershell
  nslookup store-site-backend-static-ipv4.akamaized.net 8.8.8.8
  nslookup store-site-backend-static-ipv4.akamaized.net 1.1.1.1
  ```
* **Result**:
  ```
  *** dns.google can't find store-site-backend-static-ipv4.akamaized.net: Non-existent domain
  ```
* **Diagnosis**: The domain itself does not exist. The earlier DoH (DNS-over-HTTPS) mitigation attempt had failed with TLS SNI mismatches because Akamai's edge servers present certificates for `*.epicgames.com`, not `*.akamaized.net`.
* **Verification of the Correct Domain**:
  ```powershell
  nslookup store-site-backend-static.ak.epicgames.com
  # Resolves to: e15203.dscb.akamaiedge.net (104.96.151.101)
  ```
  Testing the API endpoint via Python:
  ```
  Status: 200 OK | Search elements returned: 13
  ```

---

### Test 2: Runtime Execution on Windows (Unicode Error Discovery)
* **Test Performed**: Invoked `fetch_free_games()` within Python 3.14 on Windows.
* **Result**:
  ```
  UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f916' in position 0
  ...
  During handling of the above exception, another exception occurred:
  UnicodeEncodeError: 'charmap' codec can't encode character '\u274c'
  ```
* **Root Cause**: Windows terminals use localized encodings (e.g. `cp1252`) where emojis used in `print()` statements cause fatal exceptions.
* **Remediation**:
  Adding safe stdout reconfiguration on Windows:
  ```python
  import sys
  if sys.platform == "win32":
      if sys.stdout and hasattr(sys.stdout, "reconfigure"):
          sys.stdout.reconfigure(encoding="utf-8")
      if sys.stderr and hasattr(sys.stderr, "reconfigure"):
          sys.stderr.reconfigure(encoding="utf-8")
  ```
  With UTF-8 enabled, `fetch_free_games()` parsed 2 active free games cleanly without errors.

---

### Test 3: Discord Gateway & Channel Validation
* **Test Performed**: Authenticated against Discord gateway with `.env` credentials.
* **Result**:
  - Connected as: `Shower#2487 (ID: 1558207822531919872)`
  - Target channel ID `1558247985132085390` resolved to: `#epicgames🤖`
  - Gateway handshake and intents (`message_content=True`) are functioning properly.

---

### Test 4: Epic Games API Payload & Parsing Analysis
Inspection of the actual JSON payload from Epic Games revealed the following structures:

1. **Active Free Games** (currently active):
   - **Out of Sight**: `discountPrice: 0`, Original Price: `$14.99`, Active: `2026-10-08` to `2026-10-15`
   - **TerraScape**: `discountPrice: 0`, Original Price: `$16.99`, Active: `2026-10-08` to `2026-10-15`
2. **Upcoming Free Games** (under `upcomingPromotionalOffers`):
   - **Bad Cheese**: Free starting `2026-10-15`
   - **Agent A: A puzzle in disguise**: Free starting `2026-10-15`
3. **URL Slug Handling**:
   - `productSlug` is often `None` in the API.
   - The slug is located in `offerMappings[0]['pageSlug']`, `catalogNs['mappings'][0]['pageSlug']`, or `urlSlug`.
   - Current fallback in `cogs/epic_games.py` only checked `offerMappings[0]`.

---

## 3. Issues to Address to Finish the Bot

| Component | Current State | Required Fix |
| :--- | :--- | :--- |
| **API URL** | Points to invalid `akamaized.net` domain | Change to `store-site-backend-static.ak.epicgames.com` |
| **Windows stdout** | Crashes on emoji prints (`cp1252`) | Set UTF-8 reconfigure in `bot.py` |
| **Loop Duplicate Alerts** | Posts every hour unconditionally (168x/week spam) | Track posted promotion IDs in memory or small JSON cache file |
| **Discord Embeds** | Basic title + URL | Add end date timestamp (`<t:timestamp:R>`), original price, and banner |
| **Channel Resolution** | `get_channel()` cache only | Fallback to `fetch_channel()` if not in cache |
| **Error Handling** | Crashes on missing `EPIC_CHANNEL_ID` | Safe parsing of channel ID with clear log warnings |

---

## 4. Architectural Alternatives & Recommendations

### Alternative A: Minimal Direct Fix (Fastest)
* Fix the API URL in `cogs/epic_games.py`.
* Add Windows UTF-8 stdout configuration in `bot.py`.
* Add a simple in-memory set `self.posted_game_ids` to stop the loop from spamming every hour.
* **Pros**: Minimal code changes, addresses the briefing directly.
* **Cons**: In-memory cache resets if the bot restarts (posts once on restart).

### Alternative B: Production-Ready Implementation (Recommended)
* Apply all fixes from Alternative A.
* **Persistent Cache**: Store announced game IDs with promotion expiration timestamps in `data/posted_promotions.json`. On restart, it remembers already announced games and automatically cleans up expired entries.
* **Enriched Discord Embeds**: Display original price, banner image, and dynamic Discord timestamps (`Free until <t:end_time:F> (<t:end_time:R>)`).
* **Upcoming Games Support**: Add `!upcoming` command to let users see next week's free games.
* **Pros**: Robust, zero spam, user-friendly, high quality.
* **Cons**: Slightly more lines of code.

### Alternative C: Discord Slash Commands (Modern Discord UI)
* Use Discord Application Commands (`/freegames`, `/upcoming`) with Discord interactive buttons (e.g. "Claim on Epic Games Store" URL buttons).
* **Pros**: Modern Discord UX, autocomplete, works without message content permissions.
* **Cons**: Requires registering slash commands on Discord guild/global level.

---

## 5. Next Steps
1. Approve **Alternative A** or **Alternative B** (or specify custom preferences).
2. Apply the chosen changes to `cogs/epic_games.py` and `bot.py`.
3. Launch `bot.py` and verify in the `#epicgames🤖` channel.

