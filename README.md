# Resonate 🎵

A YouTube Music bot for Discord. Search for songs, stream them into a voice
channel, and build personal playlists that follow you across servers.

## Features

- **Search** — `/search` looks up songs on YouTube Music and lets you pick one
  from a dropdown to queue.
- **Play** — `/play` shows the top 10 YouTube Music matches for your query and
  streams the one you pick into your voice channel (URLs skip the picker and
  play directly), with a full queue system (skip, pause, resume, shuffle,
  remove, volume, now-playing).
- **Playlists** — `/playlist` commands let every user create up to 25 personal
  playlists (100 tracks each), stored in SQLite, playable in any server the
  bot is in.

## Commands

| Command | Description |
| --- | --- |
| `/play <query>` | Show the top 10 matches and pick one to play (URLs play directly) |
| `/search <query>` | Search YouTube Music and pick a result to queue |
| `/queue` | Show what's playing and what's up next |
| `/nowplaying` | Show the current song |
| `/skip` | Skip the current song |
| `/pause` / `/resume` | Pause or resume playback |
| `/stop` | Stop playback and clear the queue |
| `/shuffle` | Shuffle the queue |
| `/remove <position>` | Remove a track from the queue |
| `/volume <percent>` | Set volume (1–200%) |
| `/leave` | Disconnect the bot from voice |
| `/playlist create <name>` | Create a playlist |
| `/playlist add <name> <query>` | Add a song to a playlist |
| `/playlist show <name>` | List the songs in a playlist |
| `/playlist play <name> [shuffle]` | Queue an entire playlist |
| `/playlist remove <name> <position>` | Remove a song from a playlist |
| `/playlist list` | List your playlists |
| `/playlist delete <name>` | Delete a playlist |

The bot leaves the voice channel automatically after 5 minutes of inactivity
(configurable via `IDLE_TIMEOUT`).

## Setup

### 1. Create the Discord application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
   and create a **New Application**, then open the **Bot** tab.
2. Copy the **bot token** — you'll put it in `.env`.
3. No privileged intents are required.
4. Invite the bot with the following URL (replace `CLIENT_ID` with your
   application's client ID):

   ```
   https://discord.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot%20applications.commands&permissions=36768768
   ```

   That permission set covers: Send Messages, Embed Links, Connect, Speak.

### 2. Install and run

Requirements: **Python 3.10+**, **FFmpeg**, and **libopus** on your PATH
(`apt install ffmpeg libopus0` on Debian/Ubuntu, `brew install ffmpeg opus`
on macOS).

```bash
git clone https://github.com/Code-Liberation-Front/Resonate.git
cd Resonate
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then paste your bot token into .env
python -m resonate
```

While developing, set `GUILD_ID` in `.env` to your test server's ID so slash
commands appear instantly (global sync can take up to an hour).

### Docker

```bash
docker build -t resonate .
docker run -e DISCORD_TOKEN=your-token -v resonate-data:/data resonate
```

## How it works

- [`ytmusicapi`](https://github.com/sigma67/ytmusicapi) powers `/search` and
  free-text `/play` queries against YouTube Music (no YouTube account needed).
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) resolves a fresh audio stream
  URL right before each track plays (stream URLs expire, so they're never
  cached), and FFmpeg decodes it for Discord voice.
- Playlists are stored in SQLite via `aiosqlite`, keyed to your Discord user
  ID, so they work in every server you share with the bot.
- Each guild gets an independent player and queue, so playback in one server
  never affects another.

## Notes & limitations

- `/play` queues a single track per call; playlist URLs aren't expanded (yet).
- Playback depends on YouTube's public endpoints via yt-dlp — if streams stop
  resolving, update yt-dlp (`pip install -U yt-dlp`).

## Development

```bash
pip install -r requirements-dev.txt
pytest
```
