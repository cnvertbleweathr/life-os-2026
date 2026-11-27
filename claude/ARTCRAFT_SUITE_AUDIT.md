# ArtCraft Suite Audit — Mac mini

_2026-11-26 · discovery only (no projects, recordings or settings changed; MCPs added with approval)_

## Headline findings

1. **12 of 17 apps are installed.** AniCraft, FigCraft, TextureCraft, MaterialCraft and Craft Anything are not on disk (checked /Applications, ~/Applications, ~/Craft, Spotlight, pkgutil, Homebrew, ~/Downloads). The ArtCraft Launcher app is **not installed**: only its support folder exists (`~/Library/Application Support/ArtCraft Launcher/self-update.txt` = `v0.4.1`). There's an older `artcraft-launcher-0.2.0-macos-universal.dmg` in ~/Downloads.
2. **The "five working MCPs" were in Claude Desktop, not Claude Code.** Before this audit Claude Code had only `vectorcraft` (the Daily 10 cover entry, left untouched). PhotoCraft/PdfCraft/EffectCraft/LightCraft lived in `~/Library/Application Support/Claude/claude_desktop_config.json`.
3. **Every installed CLI runs a headless MCP server.** Each answered `initialize` + `tools/list` with **no Craft app running**. The app only has to be open for the UI tools (screenshot/click/drag/menu) and, for SoundCraft, actual audio recording.
4. **Now connected in Claude Code (user scope): all 12**, after approval. The 7 new ones (Sound/Film/Design/Deck/Word/Grid/CAD) have **no folder-restriction flag** in their CLIs, so they can open and save anywhere you can.

MCP commands added (`claude mcp list` → all `✔ Connected`):

```
soundcraft   /Users/kg/.local/bin/soundcraft-cli mcp
filmcraft    /Users/kg/.local/bin/filmcraft-cli mcp
designcraft  /Users/kg/.local/bin/designcraft-cli mcp
deckcraft    /Users/kg/.local/bin/deckcraft-cli mcp
wordcraft    /Users/kg/.local/bin/wordcraft-cli mcp
gridcraft    /Users/kg/.local/bin/gridcraft-cli mcp
cadcraft     /Users/kg/.local/bin/cadcraft-cli mcp
photocraft   /usr/local/bin/photocraft-cli mcp --automation-read-root ~/life-os-2026/data/spotify/covers --automation-write-root (same)   # mirrored from Desktop
effectcraft  /Users/kg/.local/bin/effectcraft-cli mcp --automation-read-root /Users/kg/Craft --automation-write-root /Users/kg/Craft  # mirrored
lightcraft   /Users/kg/.local/bin/lightcraft-cli mcp /Users/kg/Craft/photos                                                       # mirrored
pdfcraft     /Users/kg/.local/bin/pdfcraft-cli mcp --root /Users/kg/Craft --compact                                                # mirrored
vectorcraft  (unchanged) …vectorcraft-cli mcp --automation-read-root ~/life-os-2026/assets/templates --automation-write-root ~/life-os-2026/data/spotify/covers
```

Live-app bridging (for UI tools) is per app: `--connect PORT` (Sound/Design/Deck/Grid/Word/CAD) or `--bridge` (FilmCraft). SoundCraft's desktop app has to be started with `soundcraft --control 0`; its default control port is 7979.

---

## 1. Inventory table

Command counts come from each CLI's `commands` listing (PdfCraft: `tools`). "MCP tools" is the `tools/list` count from a headless handshake. Groups are command-id prefixes (CADCraft uses AutoCAD-style ids, so its groups are menus).

| App | Installed | App ver | CLI ver | Path (app · CLI) | Claude Code MCP | App open needed? | Commands | MCP tools | Top command groups |
|---|---|---|---|---|---|---|---:|---:|---|
| PhotoCraft | ✅ | 0.23.1 | 0.7.0 | /Applications · /usr/local/bin (also in bundle) | ✔ added (mirrored) | No (UI tools only) | 858 | 21 | layer 206, filter 124, edit 77, image 64, type 59, file 51 |
| VectorCraft | ✅ | 0.24.1 | 0.9.0 | /Applications · ~/.local/bin | ✔ pre-existing | No | 732 | 32 | object 132, select 47, path 32, file 27, text 27, document 26 |
| FilmCraft | ✅ | 0.20.1 | 0.6.0 | /Applications · ~/.local/bin | ✔ added | No (`--bridge` for live) | 693 | 17 | graphics 82, clip 57, file 56, timeline 56, sequence 45, project 40, multicam 35 |
| LightCraft | ✅ | 0.21.1 | 0.6.0 | /Applications · ~/.local/bin | ✔ added (mirrored) | No | 301 | 318 | library 40, photo 38, develop 29, faces 19, mask 18, keyword 18 |
| PdfCraft | ✅ | 0.22.0 | 0.6.0 | /Applications · ~/.local/bin | ✔ added (mirrored) | No | 143 | 17 (compact) | doc 36, page 14, form 13, comment 9, measure 8, bookmark 7 |
| EffectCraft | ✅ | 0.25.1 | 0.8.0 | /Applications · ~/.local/bin | ✔ added (mirrored) | No | 669 | 27 | layer 107, view 61, file 59, keys 34, edit 26, comp 25 |
| AniCraft | ❌ | — | — | not found | — | — | — | — | — |
| DesignCraft | ✅ | 0.21.1 | 0.6.0 | /Applications · ~/.local/bin (also in bundle) | ✔ added | No | 446 | 25 | object 54, table 35, file 29, type 25, style 21, layout 19 |
| FigCraft | ❌ | — | — | not found | — | — | — | — | — |
| TextureCraft | ❌ | — | — | not found | — | — | — | — | — |
| MaterialCraft | ❌ | — | — | not found | — | — | — | — | — |
| SoundCraft | ✅ | 0.20.1 | 0.5.0 | /Applications · ~/.local/bin | ✔ added | No for editing/mixing/bounce; **Yes to record** | 464 | 17 | view 94, edit 89, track 61, event 35, options 35, clip 30, mix 26 |
| WordCraft | ✅ | 0.19.1 | 0.5.0 | /Applications · ~/.local/bin | ✔ added | No | 460 | 16 | para 45, table 40, format 35, review 35, insert 33, references 23 |
| DeckCraft | ✅ | 0.19.1 | 0.5.0 | /Applications · ~/.local/bin | ✔ added | No | 226 | 25 | format 39, shape 23, slide 17, file 16, table 16, arrange 15, animation 11 |
| CADCraft | ✅ | 0.20.1 | 0.5.0 | /Applications · ~/.local/bin | ✔ added | No | 305 | 11 | menus: Draw 52, Tools 43, Modify 36, Format 25, Dimension 22, View 21 |
| GridCraft | ✅ | 0.19.1 | 0.5.0 | /Applications · ~/.local/bin | ✔ added | No | 315 | 21 | home 63, data 32, formulas 27, edit 26, view 22, pivot 19 |
| Craft Anything | ❌ | — | — | not found | — | — | — | — | — |

Bundle ids are all `ai.storyteller.<app>`. CLIs were installed 2026-10-10 by `~/Downloads/install_craft_clis.sh`.

---

## 2. SoundCraft deep dive

Evidence: `soundcraft-cli describe <id>`, `plugins`, `parity`, and test runs against the **in-memory `--demo` session (never saved)**. Every command reachable by `execute`/`batch` over MCP works headless unless noted.

**Precondition right now:** no audio interface is connected. macOS lists only output devices (FireTV, Mac mini Speakers), and headless SoundCraft reports `"device": null`.

### Session setup
| Item | Verdict | How |
|---|---|---|
| New session from template | **Partial / MCP** | `session.new` only takes `template: blank\|demo`. Workaround: keep a `SongTemplate.scraft`, `session.open` it, then `session.save_as`. (`session.save_template {path}` exists.) |
| Name tracks | MCP | `track.new {name, format: mono\|stereo, kind}`, `track.rename` |
| Tempo / meter | MCP | `event.tempo {bpm, at}`, `event.meter {numerator, denominator, at}` |
| Click track | MCP | `track.create_click`, `options.click`, `setup.click_countoff {volume_db, accent_note…}` |
| Count-in | MCP | `options.countoff`, `setup.click_countoff {countoff_bars: 1..16, only_during_record}` |
| Section markers | MCP | `markers.add {name, at, kind, ruler: 1..5}` (demo has Intro/Verse/Chorus/Outro) |

### Recording
| Item | Verdict | How |
|---|---|---|
| See input devices / channels | **Partial, unverified** | `setup.hardware {device?, buffer_size}` sets a device **by name**. `setup.io {action:list}` lists only busses and outputs, and no command enumerates interface inputs. `track.input {input: hardware name}`. Needs re-testing with the interface plugged in and the app bridged. |
| Arm | MCP | `mix.record_arm {tracks, value}` |
| Monitoring | MCP | `mix.input_monitor`, `options.low_latency_monitoring` |
| Punch-in | MCP | `options.quickpunch`, `options.trackpunch`, `options.destructive_punch`, `options.pre_post_roll` / `pre_roll` / `post_roll` |
| Loop recording | MCP | `options.loop_record`, `options.loop_playback` |
| Multiple takes (playlists) | MCP | `track.playlist_new / duplicate / select / promote`, `edit.copy_to_new_playlist` |
| **Actually capturing audio** | **App must be open + bridged** | Headless test: `transport.record` → `{}`, but `transport.status` → `"recording": false`. The headless engine has no device. Recording needs `soundcraft --control 0` + MCP `--connect PORT` (or you press Record in the GUI). |

### Plugins
| Item | Verdict | How |
|---|---|---|
| AU | **Not supported** | Only `engine.vst3_plugins` and `engine.clap_plugins` exist. Both currently return `[]` (no third-party plugins installed). |
| VST3 / CLAP | MCP | `mix.insert {plugin: "vst3:<id>"}`, `mix.insert_params`, `mix.insert_state` |
| Built-in amp sim | **Missing** | The 26 built-ins have no amp sim. Parity lists "SansAmp PSA-1" and "Eleven Lite" as not implemented. Closest: `saturator`, `lofi`. |
| EQ / compression / reverb | MCP | `eq_1band`, `eq_7band`, `channel_strip`, `compressor`, `expander_gate`, `maximizer`, `room_reverb`, `plate_reverb`, also `mod_delay`, `chorus`, `pitch_shifter` |

### Editing
| Item | Verdict | How |
|---|---|---|
| Comping takes | MCP (visual lanes GUI) | `track.playlist_promote {track, playlist, start, end}` copies a range from an alt take. `edit.copy_to_target_playlist`, `track.designate_target_playlist` |
| Cuts | MCP | `edit.separate`, `separate_at_transients`, `trim_*`, `heal`, `strip_silence` |
| Fades | MCP | `edit.fades_create {shape: linear\|equal power\|s-curve\|exponential\|logarithmic}` |
| Time-stretch | MCP | `track.elastic {algorithm}`, `clip.elastic_properties {ratio}`, `clip.conform_to_tempo` |
| Tempo maps | MCP | `event.tempo {at}`, `tempo_linear / parabolic / s_curve / stretch`, `event.beat_detective`, `event.identify_beat` |

### Mixing
| Item | Verdict | How |
|---|---|---|
| Buses | MCP | `mix.new_bus`, `setup.io {action: create_bus}` |
| Sends | MCP | `mix.send {bus, level_db, pre_fader}`, `mix.send_level` |
| Automation | MCP | `automation.write_range`, `automation.set_point`, `mix.automation_mode`, `automation.thin` |
| AudioSuite | MCP | `audiosuite.process {process: normalize\|reverse\|gain\|time_stretch\|pitch_shift\|varispeed\|<plugin id>}`. Tested headless: normalize and reverse returned `processed: 1`. (Parity's "0/28" counts the menu entries, not this command.) |

### Export
| Item | Verdict | How |
|---|---|---|
| WAV | MCP | `file.bounce_mix {path, format: wav\|aiff\|flac, bit_depth, start, end, normalize, dither}` |
| MP3 | **Missing** | Not a bounce format. Workaround: ffmpeg (installed at /usr/local/bin/ffmpeg). |
| Stems | MCP | `file.bounce_stems {dir, format}`, `file.export_clips {dir, clips}` |
| Loudness normalisation | **Missing** | `normalize` is a boolean with no LUFS target. Workaround: ffmpeg `loudnorm`. |

### Read-back (can Claude review takes?)
| Item | Verdict | Evidence |
|---|---|---|
| Clip lengths / positions / gains / fades | **Yes, MCP** | `session.inspect {detail: full}` → per-clip `start`, `length`, `gain_db`, `fade_in/out`, `start_time`. `soundcraft-cli info file.wav` → `frames`, `seconds`, `sample_rate`. |
| Tempo / meter / markers | **Yes, MCP** | `inspect` returns `tempo[]`, `meter[]`, `markers[]` |
| Peak / loudness / clipping | **No** | `session.audio_health` says outright: "Does not check files on disk, signal levels, plugins or routing." No peak/RMS/LUFS fields anywhere in inspect output. |
| Waveform data | **No** (image only when bridged) | The only `waveform` keys are view settings (`"view":"waveform"`). The `screenshot` tool is APP_ONLY. |
| **Workaround (verified)** | ffmpeg | `export_clips` / `bounce_mix` → `ffmpeg -af ebur128=peak=true,astats`. On a test tone it reported `I: -19.6 LUFS, True peak: -6.2 dBFS`. That covers integrated loudness, true peak, RMS, clipped-sample count and DC offset per take. |

### FilmCraft sync
**File-based only.** SoundCraft has no AAF/OMF export (parity: "Export Selected Tracks as New AAF/OMF…" not implemented), though FilmCraft has `file.importAaf`. What works:
- SoundCraft `file.bounce_mix` WAV → FilmCraft `file.import {paths}` → place on the timeline → `export --preset "YouTube 1080p Full HD"` (38 presets).
- The other way: FilmCraft exports a reference cut → SoundCraft `file.import_video` (H.264/ProRes/MJPEG) + `video.offset` to score or sync to picture.

### Breakdown summary
- **Works over MCP:** almost all of session setup, arming/monitoring/punch/loop/playlists, built-in EQ/comp/reverb, VST3/CLAP insertion, all editing (comp via playlists, cuts, fades, elastic, tempo maps), buses/sends/automation, AudioSuite, WAV/AIFF/FLAC mix and stem bounce, structural read-back.
- **GUI or app-open only:** actually recording audio; screenshots/visual comp lanes; probably device enumeration (unverified).
- **Missing:** custom templates in `session.new`, AU, built-in amp sim, MP3 export, LUFS normalisation, signal-level read-back, AAF to FilmCraft.

### The 3 biggest gaps for your use
1. **No signal read-back.** Claude can't hear or meter a take inside SoundCraft. Fix: every take review goes `export_clips` → ffmpeg analysis (loudness, true peak, clipping count, length) and comes back as a table. This works today and is the key enabler.
2. **No amp sim and no AU.** Bass and guitar DI tracks need a VST3/CLAP amp sim installed first (none are installed). Until then, record DI clean and use `saturator` + EQ for monitoring. The microtonal guitar records fine as audio; just avoid `event.beat_detective`/pitch tools on it.
3. **Recording needs the live app, and the interface isn't connected now.** Headless MCP can prep and mix but can't capture. Each session: plug in the interface, launch `soundcraft --control 0`, and bridge (a second MCP entry, e.g. `soundcraft-live … mcp --connect <port>`, can be added later). Device and input enumeration has to be re-tested then.

---

## 3. Proposed song-a-month workflow

| Week | Step | Who | Tooling |
|---|---|---|---|
| 1 | **Prep**: pick title, tempo, meter, key, form | You + Claude | Claude drafts a song sheet (form, bar counts, section lengths at that tempo, using `session.format_time`) |
| 1 | **Session build**: open `SongTemplate.scraft` → save as `~/Music/SongMonth/2026-12_<title>/<title>.scraft`; set tempo/meter; markers per section; click + 2-bar count-off; tracks `Bass DI`, `Gtr DI`, `Gtr Micro DI`, `Scratch`; bus `Verb` | Claude (headless MCP) | `session.open/save_as`, `event.tempo/meter`, `markers.add`, `setup.click_countoff`, `track.new`, `mix.new_bus`, `mix.send` |
| 2–3 | **Record**: you play; one playlist per pass; loop-record hard sections | You (app open) | Claude can arm/punch over a bridged MCP, or you drive the GUI |
| 2–3 | **Take review**: after each sitting, Claude exports the clips and reports per take: length, LUFS-I, true peak, clipped samples, alignment to markers. It flags clipped or very quiet takes and suggests which playlist ranges to promote | Claude | `session.inspect`, `file.export_clips` → ffmpeg `ebur128` + `astats`, then `track.playlist_promote` once you choose |
| 4 | **Edit and mix notes**: Claude comps the chosen ranges, adds crossfades, sets starting EQ/comp on each track, rough levels; you listen and give notes; Claude applies them and logs each pass | Both | `edit.fades_create`, `mix.insert(_params)`, `mix.volume/pan`, `automation.write_range` |
| 4 | **Export**: 24-bit WAV master + stems; ffmpeg → MP3 and a −14 LUFS streaming copy; optional FilmCraft video | Claude | `file.bounce_mix`, `file.bounce_stems`, ffmpeg `loudnorm`, FilmCraft `file.import` + preset export |
| 4 | **Log in ONS** | Claude | see below |

**ONS log (proposed, not built).** ONS has no music-recording table today (`data/music/` only has `artist_of_day/` and `onthisday/`). Proposal: an append-only `data/music/recordings/songs.jsonl` loaded into DuckDB as `music.songs_recorded`. One row per finished song:

```json
{"month":"2026-12","title":"…","tempo_bpm":92,"meter":"4/4","key":"E minor (or tuning/EDO for the microtonal piece)",
 "length_seconds":214.6,"instruments":["electric bass","electric guitar","microtonal electric guitar"],
 "session_path":"~/Music/SongMonth/2026-12_…/….scraft","master_path":"…/master.wav","mp3_path":"…/….mp3",
 "lufs_integrated":-14.1,"true_peak_dbfs":-1.0,"takes_recorded":11,"finished_on":"2026-12-28"}
```

Tempo, meter and length come from `session.inspect` (`tempo[]`, `meter[]`, `length_samples / sample_rate`). Loudness comes from ffmpeg. Key and instruments come from you, since SoundCraft has `event.add_key_change` but I didn't verify that inspect returns it. The Daily paper or home page could then show "Song of the month" with a VectorCraft-made cover.

---

## Part 3: capability check on the others

**FilmCraft** (693 cmds). Builds projects and sequences, imports media, does timeline, trim, multicam, Lumetri/LUT and masks, titles (`graphics.newText/newShape/newFromFile`), local transcription (`transcript.generate`, `removeFillers/removePauses`, `createCaptions`) and TTS (`tts.create/render`). Exports H.264/HEVC/ProRes/DNxHR/GIF/PNG/WAV via 38 presets (YouTube, Vimeo, Social Vertical), plus EDL/FCP7 XML/FCPXML/AAF/OMF. `render_frame` gives stills headless. **ONS use:** monthly song video: SoundCraft master + a VectorCraft cover/stills → captioned 1080p or vertical cut, auto-built from the songs log.

**AniCraft**: not installed. No capability check possible.

**DesignCraft** (446 cmds). InDesign-class layout: frames, stories, styles, tables, master pages, books (`book.*`, `book.exportPdf`), TOC/index/footnotes, data merge (`data` group), place images. Exports PDF (incl. booklets), IDML, EPUB (reflow and fixed), HTML, text. **ONS use:** a printable monthly or yearly "ONS Almanac" or zine: habits, fitness and music recaps flowed into a template via data merge, exported as a PDF for the Artisan 720.

**FigCraft**: not installed. No capability check possible.

**GridCraft** (315 cmds, 21 MCP tools incl. `read_range/write_range/evaluate_formula/insert_chart/create_table`). Excel-class workbook: formulas (`functions` catalog), pivots, tables, charts, sorting and filters, sample workbooks. Reads xlsx/xlsm/xlsb/ods/csv/json. Saves xlsx, exports CSV/HTML. **ONS use:** a weekly self-recalculating xlsx export of the DuckDB marts (SugarWOD, running, betting ROI) with pivots and charts, for when you want to poke at numbers outside the web app.

**DeckCraft** (226 cmds, 25 MCP tools). Slides, layouts and masters, shapes, text, tables, native charts (`insert.chart` with categories/series), media, transitions/animations. Exports PNG/JPEG/PPTX/PDF/outline. **ONS use:** an auto-generated monthly review deck (goals progress, charts from DuckDB, song-of-the-month slide), exported to PDF or PPTX.

**WordCraft** (460 cmds). Word-class documents: styles, tables, tracked changes and comments (`--author`), TOC/citations/bibliography (plus a Zotero bridge), equations, mail merge. Converts docx/odt/rtf/html/md/tex/txt/pdf/png. **ONS use:** turn the morning brief or weekly secretary notes into a nicely set docx/PDF. Mail merge could produce printed habit or check-in sheets.

**CADCraft** (305 cmds, 11 MCP tools incl. `command_line`, `query_entities`). AutoCAD-style 2D drafting: draw/modify, dimensions, layers, blocks, hatches, layouts, constraints. Reads and writes DXF/DWG, exports SVG/PNG/PDF (`sample floorplan`). **ONS use:** a dimensioned home-gym or studio floor plan (rack, rower, amp/interface desk), exported to SVG for an ONS page or PDF for planning.

TextureCraft/MaterialCraft: not installed, so nothing to report.

---

## 4. Top 3 other ONS ideas

1. **FilmCraft song video pipeline.** It closes the song-a-month loop: master WAV + cover → captioned YouTube or vertical video, triggered from the songs log. Highest payoff, all headless.
2. **DeckCraft monthly review deck.** DuckDB → native charts → PDF. Pairs with the existing morning-paper print habit and needs no new data.
3. **DesignCraft printable almanac.** Data-merged monthly or yearly print edition of ONS (habits, fitness, shows, songs) for the Epson. A bigger build, but it reuses the print schedule.

## 5. Recording hardware

### Live-app re-test (2026-11-27): why hardware comes first
SoundCraft was relaunched with `soundcraft --control 0` (control port 50902) and queried with `soundcraft-cli app`:
- **The Mac mini has no audio input.** macOS lists only FireTV and Mac mini Speakers (both output-only). USB shows only the Seagate drive and keyboard, and all four Thunderbolt ports read "No device connected".
- **The app's only device is FireTV**: `setup.hardware` → `"device": "FireTV"`. `setup.io` lists one output (`Out 1-2`) and no inputs. There is no command that lists hardware inputs.
- **Record fails silently.** A mono `BassDI` track armed fine (`record_arm: true`), but `transport.record` returned `{}` while `transport.status` stayed `recording: false`, with no clip and no log line. Claude must check `transport.status` and the clip count after each take, not trust the record call.
- **Unknown input names fail silently too.** `track.input {"input":"Input 1"}` created a bus named "Input 1" instead of returning an error.
- **`session.new` isn't available over the app channel** (`unknown method`). The test used the open, unsaved "Untitled" session; nothing was written to disk.

### Choice: Focusrite Scarlett 2i2 (4th Gen)
The use case is one player recording one instrument at a time (several guitars including the microtonal one, plus bass), with a mic planned. Two combo inputs cover instrument + mic at once. The number of instruments doesn't matter, since you swap the cable.

Specs, from focusrite.com (fetched 2026-11-27):

| | **2i2 4th Gen** | 4i4 4th Gen |
|---|---|---|
| Mic preamps / Hi-Z inputs | 2 / 2 (front combo) | 2 / 2 (same front pair) |
| Extra inputs | — | 2 rear line inputs (+ loopback) |
| Gain range | 69 dB mic, 62 dB instrument | same |
| Auto Gain + Clip Safe | yes | yes |
| Air (Presence / Harmonic Drive) | yes | yes |
| MIDI in/out | no | yes |
| Line outputs / headphone outs | 2 / 1 | 4 / 1 |
| Power | USB-C bus power (900 mA) | USB-C bus power (1.5 A), PSU included |
| Cable in box | USB-C → USB-A, 1 m | USB-C → USB-C, 1 m |
| Mac support | Apple Silicon and Intel | same |
| Price shown | $239.99 ("Black Friday Sale"; stock unclear) | $339.99 |

**Why the 2i2 4th Gen:** the 4i4 doesn't add any instrument or mic inputs. Its extras (line inputs, MIDI, more outputs) only pay off with a keyboard, synth, stereo modeler or studio monitors plus a separate headphone mix. **Clip Safe** suits this workflow especially well: it turns the gain down when a take is about to clip, which protects takes Claude can only review afterwards. Upgrade to the 4i4 if MIDI or extra line inputs come into the plan.

Not confirmed from the pages (check on arrival): whether macOS needs Focusrite Control 2 or a driver to see it, and where the direct-monitoring control is.

### Shopping list
- [ ] Focusrite Scarlett 2i2 (4th Gen)
- [ ] 1/4" TS instrument cable (one, or one per instrument to save swapping)
- [ ] Closed-back headphones (don't monitor through the FireTV; it adds delay)
- [ ] Mic: dynamic first (e.g. Shure SM57/SM58: no phantom power needed, forgiving in an untreated room). A condenser is fine later; the Scarlett supplies 48V.
- [ ] XLR cable, mic stand, pop filter (for vocals)
- [ ] One VST3 or CLAP amp sim that runs on **Intel macOS** (SoundCraft has no built-in amp sim and loads no AU). Alternatively, a USB amp modeler (Line 6 HX Stomp / POD Go, Boss Katana, Quad Cortex, FM3) that is also an interface.

### Setup steps once it arrives
1. Plug it into a Thunderbolt/USB-C port (or USB-A with the included cable). Confirm it appears in **System Settings → Sound → Input**; install Focusrite Control 2 if it doesn't.
2. Instrument into input 1 with **INST** on. Run Auto Gain, or set peaks around −12 to −6 dBFS. Enable Clip Safe.
3. Headphones into the Scarlett; turn on direct monitoring.
4. Claude relaunches SoundCraft with `--control 0`, sets `setup.hardware {"device":"<Scarlett name>", "buffer_size":128}`, confirms the inputs appear, and repeats the short unsaved test take. It verifies with `transport.status`, `track.inspect` (clip count) and an ffmpeg level check.
5. Then add the bridged MCP entry (`soundcraft-cli mcp --connect <port>`, after approval), with a fixed port or a launch script, since `--control 0` picks a new port each time.

## Open items / caveats
- Re-test SoundCraft device/input listing and recording once the Scarlett is connected (see §5 setup steps).
- Install a VST3/CLAP amp sim before the first session. Re-run `engine.vst3_plugins {rescan:true}` afterwards.
- The 7 new MCPs are unrestricted (no root flag). If that's a concern, scope them to a project instead of user scope.
- The ArtCraft Launcher app isn't installed. AniCraft/FigCraft/TextureCraft/MaterialCraft/Craft Anything would have to come from there or from GitHub (`storytold/<app>` releases, as `install_craft_clis.sh` does).
