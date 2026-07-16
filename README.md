# Deadlock Profile Tracker

Fetch and display profiles for all players in a [Deadlock](https://store.steampowered.com/app/1422450/Deadlock/) match — live or recently finished.

Data comes from the public community **[Deadlock API](https://api.deadlock-api.com)** (`deadlock-api.com`). Valve does not ship a stable first-party public match API for third-party tools.

## Download

Download the latest `deadlock-tracker.exe` from the [Releases](../../releases/latest) page — no Python installation required.

Run the `.exe` and the app will **auto-detect** your Steam account, then wait for a match via:

1. Steam HTTP cache (replay URL — no special launch flags)
2. Deadlock `console.log` (if the game was started with `-condebug`)
3. Active matches API (top-200 watched lobbies) filtered by your account

## Features

- **Auto-detect Steam user** from local `loginusers.vdf`
- **Local match detection** — Steam cache + optional `-condebug` console log
- **Active / finished lookup** by `account_id` or `match_id`
- **Parallel profile enrichment** — Deadlock Steam profiles (+ optional Steam Web API key)
- **Win-rate estimate** from recent match history
- **Rich terminal UI** — two team tables (name, hero, KDA, win rate, country)

## Quick start

### Option A — Download the exe (recommended)

1. Go to [Releases](../../releases/latest) and download `deadlock-tracker.exe`.
2. (Optional) Place a `.env` file **next to the exe** with `STEAM_API_KEY=<your key>`.
3. Double-click `deadlock-tracker.exe`.

### Option B — Run from source

```bash
pip install -r requirements.txt

# Optional Steam Web API key for extra profile enrichment
cp .env.example .env

# Auto-detect (default)
python main.py

# Look up by SteamID3 (account_id)
python main.py --account-id 123456789

# Look up a match id (active list or metadata)
python main.py --match-id 9876543210

# List top watched active matches
python main.py --active
```

## How match lookup works

| Source | When it works |
|--------|----------------|
| `GET /v1/matches/active` | Live matches in the in-game **top-200 watch** list (full roster) |
| Local Steam HTTP cache | When you enter a match (replay URL cached by Steam) |
| `console.log` (`-condebug`) | When Deadlock is launched with `-condebug` |
| `GET /v1/matches/{id}/metadata` | Finished / indexed matches (salts available) |
| `GET /v1/players/{id}/match-history` | Fallback to resolve latest `match_id`, then hydrate via metadata/active |

**Limits to know:**

- Active endpoint is **not** every match worldwide — only the watched top-200.
- Live matches often **404 on metadata** until after the game ends and is ingested.
- Server-side `?account_id=` on `/active` is unreliable; this tool filters client-side.

## Project structure

```
deadlock-profile-tracker/
├── main.py                      # CLI entry point
├── config.py                    # .env, API URL, retry policy
├── models/
│   ├── match.py
│   └── player.py
├── modules/
│   ├── steam_detector.py        # loginusers.vdf
│   ├── steam_cache_detector.py  # Steam appcache/httpcache replay URLs
│   ├── console_log_detector.py  # -condebug console.log
│   ├── steamid_converter.py
│   ├── match_finder.py          # Deadlock API match resolution
│   ├── player_extractor.py
│   ├── profile_fetcher.py       # /v1/players/steam + optional Steam Web API
│   ├── hero_resolver.py         # /v1/assets/heroes name map
│   └── display.py
├── scripts/
│   └── smoke_live_api.py        # Live API smoke test
├── tests/
├── .github/workflows/release.yml
├── requirements.txt
└── .env.example
```

## Running tests

```bash
pip install -r requirements.txt pytest pytest-asyncio
python -m pytest tests/ -v
```

Live smoke (needs network):

```bash
python scripts/smoke_live_api.py
```

## Data sources

| Source | Auth | Description |
|--------|------|-------------|
| [Deadlock API](https://api.deadlock-api.com/docs) | None | Active matches, metadata, match history, Steam profiles |
| [Steam Web API](https://developer.valvesoftware.com/wiki/Steam_Web_API) | Optional key | Extra profile enrichment |

### SteamID conversion

Deadlock API uses **SteamID3** (`account_id`); Steam Web API uses **SteamID64**:

```
SteamID64 = account_id + 76561197960265728
```

## License

See [LICENSE](LICENSE).

This project is not affiliated with Valve. Deadlock API is a community project.
