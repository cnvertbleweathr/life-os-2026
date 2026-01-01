# Spotify exports (drop files here)

Download your Spotify account data export (Streaming History / Extended Streaming History),
unzip it, and drop the JSON files into this folder.

Expected inputs:
- StreamingHistory*.json OR ExtendedStreamingHistory*.json

Naming:
- keep Spotify’s filenames as-is

Run:
1) python3 scripts/import_spotify_streaming_history.py
2) python3 scripts/spotify_metrics.py --year 2026

Notes:
- Minutes listened are computed from msPlayed.
