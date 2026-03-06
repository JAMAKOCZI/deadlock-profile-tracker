# Deadlock Profile Tracker

Automatically fetch and display profiles for all 12 players (6 v 6) in an active [Deadlock](https://store.steampowered.com/app/1422450/Deadlock/) match.

## Features

- **Active match lookup** — find a match by player `account_id` or `match_id`.
- **Fallback strategy** — if the player isn't in the top-200 watched matches, the most recent match from their history is used instead.
- **Parallel profile fetching** — enriches each player with data from the Deadlock API (and optionally Steam Web API) using `asyncio` + `httpx`.
- **Rich terminal UI** — displays two team tables with player name, hero, KDA, win rate, and country.

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Configure a Steam Web API key for richer profile data
cp .env.example .env
# Edit .env and set STEAM_API_KEY=<your key>

# 3. Run the tracker
# Look up a player's current/recent match:
python main.py --account-id 123456789

# Look up a specific active match:
python main.py --match-id 9876543210

# List top active matches:
python main.py --active
```

## Project structure

```
deadlock-profile-tracker/
├── main.py                     # CLI entry point
├── config.py                   # Configuration (.env, API URLs)
├── models/
│   ├── match.py                # Match dataclass
│   └── player.py               # Player dataclass
├── modules/
│   ├── steamid_converter.py    # SteamID3 ↔ SteamID64 conversion
│   ├── match_finder.py         # Find active/recent match
│   ├── player_extractor.py     # Extract players from match payload
│   ├── profile_fetcher.py      # Fetch profiles (Deadlock API + Steam)
│   └── display.py              # Rich terminal display
├── tests/                      # pytest test suite
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
