# ONS Film — Section, GIF Library & Pixel Display Plan

*Drafted Nov 7, 2026. Build target: Claude Code on the Mac mini, one branch + PR per phase.*

## Goal
A **Film** page in ONS that knows what you've watched (Letterboxd + Plex), and a growing **library of 5-second pixel GIFs** — one per film, each a loop of its signature scene — stored in ONS, referenceable everywhere, and later streamed to a **pixel display** that also rotates your teams' live scores.

## The pipeline (four stages)

```
 1. WATCHED            2. SCENE PICKED          3. GIF RENDERED            4. SHOWN
 Letterboxd RSS ─┐     film.scene_catalog       scripts/film_gif_render    /film page (PixelScene slot + library)
 Plex history  ──┼──▶  (Claude suggests,   ──▶  64×32 master, 5s loop ──▶  /api/display/playlist ──▶ LED panel
                 │      you approve)            web + matrix palettes        (film GIFs ⇄ live scores)
 mart_film_watches
```

### 1 · Watched — `mart_film_watches`
- **Letterboxd:** `pipelines/letterboxd_pipeline.py` already exists (dry-run confirmed, not yet in `daily_sync`). It carries the TMDB id from the RSS `tmdb:` namespace → that's the join key.
- **Plex:** new `pipelines/plex_pipeline.py` (DLT). Poll the server's watch history (`/status/sessions/history/all`, `X-Plex-Token`); resolve each item's `tmdb://` GUID. Polling only, no webhooks (Plex Pass question stays decoupled, as planned).
- **dbt:** `stg_letterboxd__diary`, `stg_plex__history` → `mart_film_watches` (one row per film per watch date; `source` = letterboxd / plex / both; rating from Letterboxd when present).
- **TMDB** (planned source) fills poster, runtime, genres, director — used for the page and for scene suggestion context.

### 2 · Scene picked — `film.scene_catalog`
One row per film. This is the "reference library" record.

| column | notes |
|---|---|
| `tmdb_id`, `title`, `year` | key + display |
| `scene_label` | e.g. "The shadow on the stairs" |
| `scene_note` | one line of what moves in the loop |
| `render_mode` | `sprite` · `plex_clip` · `motif` (see below) |
| `clip_start`, `clip_end` | `plex_clip` only, seconds into your file |
| `status` | `suggested` → `approved` → `rendered` (or `rejected`) |
| `gif_web`, `gif_matrix` | paths under `data/film/gifs/` |
| `suggested_by`, `approved_at`, `rendered_at` | audit |

- **Suggestion step:** for each new watch with no catalog row, one cheap Claude API call (title, year, TMDB overview) → proposes the most iconic scene + an approximate timestamp + a suggested `render_mode`. Log to `data/ai/generations.jsonl` like the other AI calls.
- **Approval:** you approve/edit in ONS (a small queue on the Film page, same pattern as Capture). Nothing renders without approval.

### 3 · GIF rendered — `scripts/film_gif_render.py`
**Format (matches the existing pixel scenes in DESIGN.md → Pixel Scenes):**
- **Master is 64×32 art pixels.** The title scenes are already 32px tall, so this maps 1:1 onto a 64×32 LED panel and integer-scales cleanly on the web.
- **5 seconds = 40 frames × 125 ms**, infinite loop, built so the last frame flows into the first (e.g. subject enters one side and exits the other).
- **Closed palette, two outputs:** `gif_web` uses the light-theme `--px-*` tokens; `gif_matrix` uses the dark-theme tokens. On an LED panel black is "off", so dark grounds look right and use far less power.
- Same rules as the scenes: integer scaling, `image-rendering: pixelated`, light from the top-left, characters get a 1px outline, scenery doesn't.

**Three render modes:**
- **`sprite`: hand-built pixel scene.** For public-domain films (in the US: films released through 1930, plus a few later ones that lost copyright, such as *Night of the Living Dead*, 1968). The scene can be recreated faithfully. Sample: Nosferatu shadow-on-the-stairs (`nosferatu_64x32.gif`, script `nosferatu.py`). Claude can draw these.
- **`plex_clip`: pixelate your own copy.** For films still under copyright (e.g. *Evil Dead*), Claude won't hand-draw the actual scene or character. Instead the renderer runs on the Mac mini: `ffmpeg` cuts `clip_start → clip_end` from your Plex file, crops to 2:1, scales to 64×32, then quantizes with ordered dither to the ONS film palette. The result is a personal-use derivative, so: keep `data/film/gifs/` gitignored and serve these only behind ONS auth / Tailscale, not on a public page.
- **`motif`: original mood loop.** The fallback when there's no file and no PD scene: an original pixel loop in the film's colours (rain on a window, a flickering projector, a VHS tracking wobble) with the title in the 3×5 pixel font.

`daily_sync.py` gets one step after dbt: render every `approved` row that has no GIF yet.

### 4a · Shown on ONS — `/film` page
- **Title scene:** a new `PixelScene scene="film"` that plays the most recently watched film's GIF (same click-to-pause, offscreen-stop and reduced-motion rules).
- **Blocks:** recent watches (Letterboxd + Plex, with source marks), the **GIF library** grid ("Screening Room": every rendered film, filter by year/genre/rating), the approval queue, year stats (films watched, avg rating, by decade).
- **Area colour:** Film needs its own tint / ink / mark trio in `globals.css` + DESIGN.md (none of the current eight fit).
- **API:** `api/routers/film.py` → `/api/film/watches`, `/api/film/library`, `/api/film/queue` (POST approve/edit), static GIFs served from the router.

### 4b · Shown on the pixel display (later)
- **Hardware:** a 64×32 HUB75 RGB panel on a Raspberry Pi with an RGB matrix HAT, driven by `rpi-rgb-led-matrix`. Ties into `ONS_PI_MIGRATION_PLAN`.
- **One endpoint does the curation:** `/api/display/playlist` returns an ordered list of items (`{type, url|frames, seconds}`), interleaving film GIFs (`gif_matrix`) with **score frames** for your teams. Use the ESPN source you already picked for live sports, with team logos from the existing logo sets, rendered server-side at 64×32 with the same 3×5 font as the scenes.
- **The Pi is dumb:** it fetches the playlist every minute and plays it. All logic stays in ONS. Live games can pre-empt the film rotation.

## Build order (each a branch + PR)
1. **Watches.** Letterboxd into `daily_sync`; `plex_pipeline.py`; staging + `mart_film_watches`.
2. **Catalog.** `film.scene_catalog`, suggestion step, approve/edit endpoint.
3. **Renderer.** `film_gif_render.py` with the three modes; `.gitignore` for clip output; `daily_sync` step.
4. **Page.** `/film` page, `PixelScene` `film` scene, Film area colour, DESIGN.md entry.
5. **Display.** `/api/display/playlist`, score-frame renderer, Pi player script + launchd/systemd unit.

## Open decisions
- Film area colour trio.
- Whether rewatches get their own GIF or reuse the film's.
- Panel size: 64×32 (matches scenes 1:1, recommended) vs 64×64 (room for a score bar under the film).
- Seed the library first with a public-domain starter set (Nosferatu, Metropolis, Caligari, A Trip to the Moon, Night of the Living Dead) so the renderer and page are proven before Plex lands.
