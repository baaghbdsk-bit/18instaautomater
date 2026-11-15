# 18instaautomater

Fully autonomous Instagram Reel engine for **@xene.ai**: picks a content
theme weighted by past engagement, writes a fresh flirty line (Gemini, with
a built-in seed bank fallback), generates an AI photo (Perchance), renders a
1080×1920 Reel with FFmpeg (Anton typography, scrim, camera motion, licensed
music), validates the MP4, publishes through instagrapi, and commits its
state back to the repository.

GitHub Actions wakes it 6 times a day; an hourly checker re-dispatches a
missed slot. No laptop needed after setup.

```
GitHub Actions (6 crons + hourly checker)
   │
   ├─ kill switch → auth → crash reconciliation → cap/gap guards
   ├─ theme picked by measured engagement (likes+comments)
   ├─ line written by Gemini (3-level dedupe) or seed bank
   ├─ photo: Perchance theme prompts (prompt-level dedupe)
   ├─ music: CC BY 4.0 pool, LRU picks, random offset per post
   ├─ render 1080×1920, 9–15 s, ASS text, scrim, 5 camera moves
   ├─ validate (codec/size/duration/faststart) — broken renders never post
   ├─ duplicate-caption check vs last 12 posts → upload with safe retry
   ├─ record in SQLite (committed back by CI)
   └─ artifact + step summary + optional webhook
```

## ⚠️ Warnings

1. **Instagram automation violates Instagram's Terms of Service.** Accounts
   can be blocked or disabled. Volume is deliberately capped (6/day, 120-min
   gap) — raise it at your own risk. You accept this by running it.
2. **Keep content suggestive, not explicit.** Nudity gets pages disabled
   fast, which defeats the point of reviving them. The Perchance negative
   prompt blocks explicit material on purpose; edit lines in `lines.py`
   accordingly.
3. **FFmpeg edits media, it doesn't create photos.** Images come from the
   Perchance wrapper; captions/lines from `lines.py` (+ Gemini).

## Architecture (vs the original script collection)

| Concern | Where | Notes |
|---|---|---|
| State | `data/engine.db` (SQLite, committed) | posts, lines, asset usage, insights, runs |
| Orchestration | `pipeline.py` | kill switch → auth → reconcile → guards → build → publish |
| Content | `themes.py` + `lines.py` | 12 themes × 3 prompts, 90 seed lines, LLM + dedupe |
| Rendering | `generate_video.py` | ASS/libass, layout auto-fit, scrim, motion, loudnorm |
| Validation | `validate.py` | ffprobe + MP4 faststart atom walker |
| Publishing | `post_instagram.py` | instagrapi, session cache, 2FA, safe-retry uploads |
| Diagnostics | `manage.py` | `doctor` / `status` / `library` / `insights` / `cleanup` |
| Reliability | `net.py`, `notify.py` | jittered backoff, GH annotations, webhook |

**Double-post protection (layered):**
1. a `publishing` row is written *before* the upload starts;
2. uploads retry only after confirming the caption's first line is not live;
3. every run reconciles stale rows against the profile before anything else;
4. daily cap + minimum gap + last-12-posts caption dedupe.

## Install (local, optional — CI does everything)

```powershell
cd d:\18instaautomater
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # fill in credentials
```

## Run locally

```powershell
python pipeline.py                  # full cycle (generate -> render -> post)
python pipeline.py --dry-run        # build only, never posts
python pipeline.py --skip-generate  # reuse newest image in assets/images
python pipeline.py --theme fitness  # force a theme
python manage.py doctor             # is everything wired up?
python manage.py status             # recent posts + today's count
python -m pytest -q                 # test suite (no network)
```

## GitHub Actions setup

1. Push this folder to a **private** GitHub repo (default branch `main`).
2. Settings → Secrets and variables → **Actions**:

   | Secret | Required | Value |
   |---|---|---|
   | `IG_USERNAME_1` / `IG_PASSWORD_1` / `IG_2FA_SECRET_1` | yes | instagrapi login for @xene.ai |
   | `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | yes | Gemini (OpenAI-compatible) |
   | `NOTIFY_WEBHOOK_URL` | no | Discord/Slack failure alerts |
   | `IG_USERNAME_2` … | no | second account for rotation |

   Variables (Settings → Variables): `IG_HANDLE_1` (watermark, default
   `@xene.ai`), `DAILY_CAP_PER_ACCOUNT` (6), `MIN_GAP_MINUTES` (120).

3. Settings → Actions → General → **Workflow permissions** → *Read and write*
   (the workflow commits `data/engine.db` back).
4. Actions → **Scheduled reel post** → *Run workflow* with `dry_run` ticked →
   inspect the artifact. Then run it unticked for the first real post.
5. Let the schedule take over (6×/day at :23 past every 4th hour).

`checker.yml` runs hourly and re-dispatches the post workflow whenever no
successful run exists in the last 2 hours — the engine's own guards make the
extra dispatch harmless.

### First-login note

The first CI run performs a fresh login from a GitHub datacenter IP;
Instagram may raise a challenge. If that happens: log in from your phone,
complete any verification, delete `sessions/` cache (Actions → Caches), and
re-run. Afterwards the cached session avoids most logins.

## Configuration

- `config.py` — cadence, video, fonts, Perchance, LLM, switches
- `themes.py` — themes: Perchance prompts + line mood + music pool
- `lines.py` — seed lines (3 moods × 30), CTAs, hashtags, cliché list
- `.env` — credentials and secrets only

## Music

15 tracks by Kevin MacLeod (incompetech.com), CC BY 4.0 — attribution is
appended to every caption automatically (`MUSIC_CREDIT` in `config.py`).

## Troubleshooting

- **`python manage.py doctor`** first — it checks ffmpeg/libass, fonts, DB,
  accounts, LLM, Perchance, library and the last render.
- **ffmpeg not found**: set `FFMPEG_BIN` / `FFPROBE_BIN` in `.env`.
- **Challenge required**: complete it in the app, delete
  `sessions/<username>.json`, re-run.
- **Perchance down**: CI fails the run by design (`--strict`); the hourly
  checker retries automatically.
- **Silent reels**: no files in `assets/music/` — the pools ship with the
  repo, make sure they were committed.
- **Pause everything**: set `KILL_SWITCH=1` (repo variable) — runs skip
  cleanly without failing.

## Disclaimer

Unofficial automation framework. You are solely responsible for the content
you post and for complying with Instagram's Community Guidelines and Terms
of Service. The author is not responsible for account bans or data loss.
