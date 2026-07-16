# Deadlock Profile Tracker

CLI that shows **all players in your Deadlock match** — nicknames, heroes, KDA, win rate, country — in a Rich terminal UI.

Works for **live** and **recently finished** matches. Data comes from the public community [Deadlock API](https://api.deadlock-api.com) ([docs](https://api.deadlock-api.com/docs)). Valve does not provide a stable first-party public match API for third-party tools.

> Not affiliated with Valve. Deadlock API is a community project.

## Download

Get the latest Windows build from **[Releases](https://github.com/JAMAKOCZI/deadlock-profile-tracker/releases/latest)**:

- Asset: `deadlock-tracker.exe`
- No Python install required

```text
1. Download deadlock-tracker.exe
2. (Optional) Put a .env file next to the exe (see Configuration)
3. Double-click the exe — it auto-detects your Steam account and waits for a match
```

## Features

| Feature | Details |
|---------|---------|
| Auto Steam login | Reads local `loginusers.vdf` (MostRecent user) |
| Match detection | Steam HTTP cache (no flags) · `console.log` (`-condebug`) · active API |
| Lookups | `--account-id` · `--match-id` · `--active` |
| Profiles | Batch `GET /v1/players/steam` (+ optional Steam Web API key) |
| Heroes | Names from `GET /v1/assets/heroes` |
| Win rate | Estimate from recent match history |
| UI | Two team tables (name, hero, KDA, win rate, country) |

## Quick start (source)

```bash
git clone https://github.com/JAMAKOCZI/deadlock-profile-tracker.git
cd deadlock-profile-tracker
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt

# Optional: Steam Web API key for extra profile enrichment
cp .env.example .env

python main.py                 # auto-detect (default)
python main.py --account-id 123456789
python main.py --match-id 9876543210
python main.py --active        # list top watched live matches
```

## CLI

| Command | Description |
|---------|-------------|
| `python main.py` | Detect local Steam user, wait for a match (cache / console / API) |
| `python main.py --account-id <SteamID3>` | Find that player's active or recent match |
| `python main.py --match-id <id>` | Load a specific match (active list or metadata) |
| `python main.py --active` | Print top watched live matches |
| `python main.py -h` | Help |

SteamID3 is the 32-bit `account_id` used by the Deadlock API (not SteamID64).

## How match detection works

Auto-detect (no args) tries, in parallel while waiting:

1. **Steam HTTP cache** — replay URL in `appcache/httpcache` (no special launch flags)
2. **`console.log`** — if Deadlock was started with `-condebug`
3. **Active matches API** — `GET /v1/matches/active`, client-side filter by your `account_id`

Then the match is hydrated and profiles are fetched.

### API resolution order

| Source | When it works |
|--------|----------------|
| `GET /v1/matches/active` | Live lobbies in the in-game **top-200 watch** list (full roster) |
| Steam HTTP cache | After you enter a match (Valve replay host in Steam cache) |
| `console.log` (`-condebug`) | When the game was launched with `-condebug` |
| `GET /v1/matches/{id}/metadata` | Finished / indexed matches (match salts available) |
| `GET /v1/players/{id}/match-history` | Latest `match_id`, then hydrate via metadata or active list |
| `GET /v1/players/steam` | Persona name, avatar, profile URL, country |
| `GET /v1/assets/heroes` | Hero display names |

### Limits (API / game, not app bugs)

- **Active list ≠ all matches worldwide** — only the watched top-200.
- **Live metadata often 404s** until the match ends and is ingested (`Failed to fetch match salts`).
- **Live KDA** may show `—` — the active payload usually has no combat stats; KDA appears after metadata is available.
- Server-side `?account_id=` on `/active` is unreliable; this tool **filters client-side**.

## Configuration

Copy `.env.example` → `.env` (next to the exe when using the build, or in the project root from source).

| Variable | Default | Description |
|----------|---------|-------------|
| `STEAM_API_KEY` | _(empty)_ | Optional [Steam Web API](https://steamcommunity.com/dev/apikey) key |
| `DEADLOCK_PATH` | auto | Override Deadlock install path |
| `DEADLOCK_API_BASE_URL` | `https://api.deadlock-api.com` | API base URL |
| `REQUEST_TIMEOUT` | `15` | HTTP timeout (seconds) |
| `MAX_ACCOUNT_ATTEMPTS` | `20` | Retries for `--account-id` |
| `ACCOUNT_RETRY_DELAY_S` | `15` | Delay between account retries |
| `MAX_MATCH_LOOKUP_ATTEMPTS` | `8` | Retries for `--match-id` |
| `MATCH_LOOKUP_RETRY_DELAY_S` | `5` | Delay between match-id retries |

Placeholder values like `your_steam_api_key_here` are ignored.

For the **exe**, place `.env` in the **same folder as `deadlock-tracker.exe`** (CWD alone is not enough under PyInstaller).

### SteamID conversion

```text
SteamID64 = account_id + 76561197960265728
account_id (SteamID3) = SteamID64 - 76561197960265728
```

## Project structure

```text
deadlock-profile-tracker/
├── main.py                         # CLI entry point
├── config.py                       # env, API URL, retry policy
├── models/
│   ├── match.py
│   └── player.py
├── modules/
│   ├── steam_detector.py           # loginusers.vdf
│   ├── steam_cache_detector.py     # Steam appcache/httpcache
│   ├── console_log_detector.py     # -condebug console.log
│   ├── steamid_converter.py
│   ├── match_finder.py             # active / history / metadata
│   ├── player_extractor.py
│   ├── profile_fetcher.py          # steam profiles + win rate
│   ├── hero_resolver.py            # hero id → name
│   └── display.py                  # Rich tables
├── scripts/
│   └── smoke_live_api.py           # live API smoke test
├── tests/                          # pytest suite
├── .github/workflows/release.yml   # test + Windows exe + GitHub Release
├── requirements.txt
└── .env.example
```

## Development

```bash
pip install -r requirements.txt pytest pytest-asyncio
python -m pytest tests/ -v
```

Live smoke (needs network):

```bash
python scripts/smoke_live_api.py
```

### Release

Pushing a tag `v*` (e.g. `v1.0.0`) runs CI tests, builds `deadlock-tracker.exe` on Windows, and publishes a GitHub Release.

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| “Could not detect Steam account” | Log into the Steam client; or use `--account-id` / `--match-id` |
| Match never found in auto mode | Enter a match; ensure Steam is installed; try relaunching Deadlock with `-condebug` |
| “Match not found” for a live id | Wait for top-200 watch listing, or try again after the match ends (metadata) |
| Names stay `Player_<id>` | Network/API issue, or profiles not yet in Deadlock steam cache; optional `STEAM_API_KEY` helps |
| `.env` ignored by exe | Put `.env` next to `deadlock-tracker.exe`, not only in CWD |

## License

See [LICENSE](LICENSE).
