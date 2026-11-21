# 18instaautomater — AI glamour quote posts

Automated **static Instagram quote images** built around one consistent
fictional adult South Asian AI influencer. Each run claims one unused line from
the curated quote bank, builds a prompt from a locked master character identity
plus a curated visual variation, generates a real image through a swappable
provider adapter, composes the quote onto the image, validates the result,
records the full lifecycle in SQLite and publishes through a cached Instagram
session.

```
quote bank (110 approved lines, no LLM filler)
   → atomic claim (quote_usage table)
   → master character prompt + curated variation (outfit/pose/expression/...)
   → ImageProvider adapter (Perchance by default; NVIDIA optional)
   → real image downloaded + verified (placeholders refused)
   → Pillow quote composition (1080x1920, Anton typography, scrim)
   → final image validation (size, open, sidecar, placeholder guard)
   → session/cookie publish via instagrapi with duplicate protection
   → SQLite lifecycle + run report + webhook
```

## Quick start

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # fill in credentials
python -m pytest -q             # baseline must be green
python manage.py doctor
python pipeline.py --dry-run    # real generation, NO publishing
```

## Output mode

| Mode | Command | Result |
|---|---|---|
| **Reel (default)** | `python pipeline.py` | composed 1080×1920 quote image → short MP4 + trending catalog audio |
| Photo | `python pipeline.py --mode photo` | static quote image with trending catalog audio |
| Build only | `python pipeline.py --dry-run` | real image + composed output, no upload |
| Strict | `python pipeline.py --strict` | refuses placeholders and refusals |
| Legacy Reel | `python pipeline.py --mode legacy-reel` | original FFmpeg video/theme workflow |

Reel mode uses `generate_video.still_video()` to turn the composed JPEG into a
silent 9–18 s MP4 with a slow camera move; instagrapi then attaches the catalog
track with `clip_upload_with_music()`. Your quote bank and master character
prompt are used in every mode.

## Quote bank

`assets/quotes/approved.json` is the single source of approved lines. Currently
800 user-approved entries (`u001`–`u800`); add more with `quote_bank.add_lines()`
or by editing the JSON. The application **never** asks an LLM to invent
replacement quotes.

```powershell
python manage.py quotes                       # counts + fingerprint
python -c "import quote_bank; print(quote_bank.add_lines('assets/quotes/approved.json', [{'text':'Your new approved line here','mood':'flirty'}]))"
```

A line is claimed atomically in `quote_usage` before generation, so two
concurrent runs cannot pick the same line. When the bank runs low a warning is
emitted; when it is exhausted the run fails loudly instead of silently filling
with weak lines.

## Character identity (important limitation)

`character/profile.py::MASTER_PROFILE` is the fixed identity foundation: fictional
adult woman, 25, South Asian/Indian appearance, fair-to-medium luminous skin,
long wavy dark-chocolate hair, round full-cheeked soft oval face, large almond
dark-brown eyes, full lips, full-figured curvy hourglass build. It is always
prepended verbatim to every prompt by `character/variations.py::build_prompt`.

**A fixed seed and repeated wording do NOT guarantee the same face.** The
verified Perchance wrapper exposes only `prompt`, `negative_prompt`, `style`,
`aspect_ratio`, `guidance_scale`, `seed` and `num_images` — there is **no
reference-image field**. The adapter records `reference_images_supported=False`
rather than pretending otherwise. For true face locking, supply an
identity-capable provider behind `image_providers/base.py::ImageProvider`; the
character profile already carries `reference_images` and version metadata for
that purpose.

## Image providers

| Provider | Config | Credentials | Reference image |
|---|---|---|---|
| `perchance` (default) | `IMAGE_PROVIDER=perchance`, local wrapper at `PERCHANCE_URL` | none | **not supported** |
| `nvidia` | `IMAGE_PROVIDER=nvidia`, `NVIDIA_API_KEY` | NVIDIA NIM key | not supported |
| `placeholder` | `IMAGE_PROVIDER=placeholder`, `ALLOW_PLACEHOLDER=1` | none | dev/test only |

Run the Perchance wrapper locally:

```powershell
git clone https://github.com/afrozthalam/Perchance-API.git
pip install -r Perchance-API/requirements.txt
python Perchance-API/app.py
# wait until http://127.0.0.1:8000/v1/health reports "ready": true
```

The wrapper drives a background Chrome session against Perchance; review that
project's terms before production use. It has no API key and no documented rate
limit. The adapter applies health checks, timeouts, bounded retries, image-byte
validation and atomic saves. Failed generations are never marked successful.

## Composition & validation

`compose_image.py` resizes/crops the generated photo to 1080×1920, adds a
gaussian scrim, wraps the quote with the shared `generate_video.layout()` logic
(Anton font), and writes a sidecar JSON with the exact lines rendered.
`validate.py::validate_final_image` checks existence, openability, dimensions,
minimum bytes, non-flat pixels, a non-placeholder filename and the sidecar
quote match. Text presence is verified via metadata (no OCR), which is stated
explicitly rather than overclaimed.

## Music on photo posts (trending audio)

Static image posts cannot carry an audio stream by themselves, but the installed
`instagrapi` (>= 3.2) supports attaching an **Instagram catalog track** to a feed
photo via `photo_upload_with_music(..., track=...)`. The pipeline therefore:

1. discovers tracks with `music/top_trends` (falling back to `music/trending`,
   or `music/audio_global_search` when `MUSIC_SOURCE=search`),
2. prefers a track not used recently (LRU via `used_assets`),
3. publishes the composed JPEG with that catalog track,
4. records `prompt_metadata.music` (track id/title/artist) in the post row.

The first post had no music because the original spec produced static images and
the publisher used plain `photo_upload()` — there was no audio path. Set
`MUSIC_ENABLED=1` (default) to attach trending audio; `MUSIC_SOURCE=off` keeps
posts silent. Music discovery is fail-soft: if the catalog is unavailable the
post is still published, with a note in the run report. Instagram shows the
track attribution on the post automatically, so no manual caption credit is
needed.

## Instagram authentication

Session/cookie based via `instagrapi` only — no Graph API. Sessions are cached
at `sessions/<username>.json`, never committed. `ensure_session` validates the
session before upload; `upload_photo_post` uses `photo_upload` with a fail-fast
challenge path and a duplicate check after each failed attempt. Secrets live in
`.env` locally and GitHub Secrets in CI. `python manage.py session` shows only
cache metadata, never session contents.

## Multiple accounts / full automation

`run_all_accounts.py` runs one complete pipeline post **per configured account** in a
single scheduled invocation. GitHub Actions calls it instead of `pipeline.py`, so
each cron slot publishes once to `@xene_hotty` and once to `@panda_fcuk`. A failure
on one account never blocks the other; each sub-run keeps its own session,
cadence bucket (`DAILY_CAP_PER_ACCOUNT`) and run label.

To restrict locally:

```powershell
python run_all_accounts.py --dry-run          # build for both, publish nothing
python run_all_accounts.py --only account_2   # only @panda_fcuk
```

**One-time GitHub setup (no code changes needed afterward):**
- Secrets: `IG_USERNAME_1`/`IG_PASSWORD_1`/`IG_2FA_SECRET_1` (**xene_hotty**),
  `IG_USERNAME_2`/`IG_PASSWORD_2`/`IG_2FA_SECRET_2` (**panda_fcuk**).
  Both accounts share the same password — set `IG_PASSWORD_2` to the same
  value as `IG_PASSWORD_1` in GitHub Secrets (values are never committed).
- Variables: `IG_HANDLE_1=@xene_hotty`, `IG_HANDLE_2=@panda_fcuk`,
  `DAILY_CAP_PER_ACCOUNT=6`, `MIN_GAP_MINUTES=0`, `IMAGE_PROVIDER=perchance`,
  `MUSIC_ENABLED=1`, `MUSIC_SOURCE=trending`, `REEL_DURATION=12`,
  `CHARACTER_ID=meera-v1`, `QUOTE_LOW_WATERMARK=20`.
- Settings → Actions → General → Workflow permissions: **Read and write**.

Automation caveats: the first CI login from a datacenter IP may require an
Instagram challenge (complete it in-app once, clear the `ig-sessions-v2-*` cache,
re-run). The Perchance wrapper clones a third-party repo at runtime and is the
main reliability risk. Content moderation is not enforced — see the warning
about explicit quote text at the top of this README.

## Scheduling

`.github/workflows/post.yml` keeps the original six crons/day (`23 */4 * * *`)
with `concurrency.cancel-in-progress: false`, plus `checker.yml` which
re-dispatches after two hours of no success. The engine's own guards (daily cap,
minimum gap, duplicate caption, crash reconciliation) make redundant dispatches
harmless.

## Diagnostics

```powershell
python manage.py doctor     # ffmpeg, fonts, DB, accounts, provider, library
python manage.py status     # recent posts and counts
python manage.py quotes     # quote bank status
python manage.py preview    # prompt + composition from a local image, no network
python manage.py generate   # one real generated image through the adapter
python manage.py session    # session cache metadata only
python manage.py library
python manage.py insights
python manage.py cleanup
```

## Database

`data/engine.db` (SQLite/WAL) is preserved, never reset. `migrations/001_add_vertical.py`
additively adds lifecycle columns to `posts` and a `quote_usage` table. It is
idempotent and runs automatically on `db.connect()`. Legacy rows and generated
lines are untouched. Rollback: restore `data/engine.db` from your backup and
check out `master`.

## Warnings

1. Instagram automation can violate Instagram's Terms of Service and risk bans.
2. Keep content non-explicit. The master negative prompt blocks nudity and
   explicit material. The wrapper itself bypasses Perchance content-warning
   screens — review that decision before production use.
3. Placeholder images are refused in production (`--strict`, `ALLOW_PLACEHOLDER=0`).
4. No live Instagram post is performed during implementation; publishing
   requires explicit approval after the dry run.
