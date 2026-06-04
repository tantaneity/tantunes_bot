# tantunes

inline telegram bot for searching and streaming music from spotify, soundcloud and youtube.

## usage

type `@tantunes_bot <query>` in any chat — select a track — audio appears in place.

whole albums go through a command. send `/album artist - album`, flip through the cover gallery
with `‹ ›`, hit download. tracks come back as grouped audio, each one cached so the next person
who searches it gets an instant result. needs spotify configured (for the album search) and
`UPLOAD_CHANNEL_ID` set (where the audio lives).

soundcloud albums work too, just by link. there's no text search for sets on soundcloud, so paste
the album url instead: `/album https://soundcloud.com/artist/sets/name`. same picker, same flow,
spotify not required.

## stack

- **aiogram 3** — telegram bot framework
- **yt-dlp** — audio download
- **spotipy** — spotify search (optional)
- **redis** — file_id cache + search result cache
- **sqlite + sqlalchemy** — stats persistence
- **dishka** — DI container

## setup

```env
BOT_TOKEN=
REDIS_URL=redis://redis:6379
UPLOAD_CHANNEL_ID=        # private channel for audio storage (recommended)
ADMIN_IDS=                # comma-separated telegram user ids
SPOTIFY_CLIENT_ID=        # optional, enables spotify as primary source
SPOTIFY_CLIENT_SECRET=
DB_PATH=tantunes.db
```

get spotify credentials at [developer.spotify.com](https://developer.spotify.com/dashboard).

for auto-download without button: **BotFather → /setinlinefeedback → enable**.

## run

```bash
docker compose up -d --build
```


## links

- channel — [t.me/instantaneity](https://t.me/instantaneity)
