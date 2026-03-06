# Deadlock Profile Tracker

Automatically fetch and display profiles for all 12 players (6 v 6) in an active [Deadlock](https://store.steampowered.com/app/1422450/Deadlock/) match.

## Download

Download the latest `deadlock-tracker.exe` from the [Releases](../../releases/latest) page — no Python installation required.

Simply run the `.exe` and the app will **automatically detect** your Steam account and look up your current or most recent match.

## Features

- **Auto-detect Steam user** — reads your locally logged-in Steam account so you don't need to type anything.
- **Active match lookup** — find a match by player `account_id` or `match_id`.
- **Fallback strategy** — if the player isn't in the top-200 watched matches, the most recent match from their history is used instead.
- **Parallel profile fetching** — enriches each player with data from the Deadlock API (and optionally Steam Web API) using `asyncio` + `httpx`.
- **Rich terminal UI** — displays two team tables with player name, hero, KDA, win rate, and country.

## Quick start

### Option A — Download the exe (recommended)

1. Go to [Releases](../../releases/latest) and download `deadlock-tracker.exe`.
2. (Optional) Place a `.env` file next to the exe with `STEAM_API_KEY=<your key>` for richer profile data.
3. Double-click `deadlock-tracker.exe` — it auto-detects your Steam account.

### Option B — Run from source

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Configure a Steam Web API key for richer profile data
cp .env.example .env
# Edit .env and set STEAM_API_KEY=<your key>

# 3. Run the tracker (auto-detect mode)
python main.py

# Or specify a player manually:
python main.py --account-id 123456789

# Look up a specific active match:
python main.py --match-id 9876543210

# List top active matches:
python main.py --active
```

## Project structure

```
deadlock-profile-tracker/
├── main.py                     # CLI entry point (auto-detect or manual)
├── config.py                   # Configuration (.env, API URLs)
├── models/
│   ├── match.py                # Match dataclass
│   └── player.py               # Player dataclass
├── modules/
│   ├── steam_detector.py       # Auto-detect logged-in Steam user
│   ├── steamid_converter.py    # SteamID3 ↔ SteamID64 conversion
│   ├── match_finder.py         # Find active/recent match
│   ├── player_extractor.py     # Extract players from match payload
│   ├── profile_fetcher.py      # Fetch profiles (Deadlock API + Steam)
│   └── display.py              # Rich terminal display
├── tests/                      # pytest test suite
├── .github/workflows/
│   └── release.yml             # Build exe & publish GitHub Release
├── requirements.txt
├── .env.example
└── README.md
```

## Running tests

```bash
pip install pytest pytest-asyncio
python -m pytest tests/ -v
```

## Data sources

| Source | Auth | Description |
|--------|------|-------------|
| [Deadlock API](https://api.deadlock-api.com/docs) | None | Active matches, player profiles, match history |
| [Steam Web API](https://developer.valvesoftware.com/wiki/Steam_Web_API) | API key | Enriched Steam profile (avatar, country) |

## SteamID conversion

Deadlock API uses **SteamID3** (`account_id`), while Steam Web API uses **SteamID64**.

```
SteamID64 = account_id + 76561197960265728
```

## License

See [LICENSE](LICENSE).
