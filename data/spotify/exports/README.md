# Spotify exports (drop files here)

Download your Spotify account data (Streaming / Extended Streaming History) from your Spotify account privacy/data page.
Place the extracted streaming history files in this folder.

Expected inputs (varies by export type):
- StreamingHistory*.json OR ExtendedStreamingHistory*.json
- "Read Me First - Extended Streaming History" (reference)

This repo uses msPlayed to compute total minutes listened.

Run:
1) python3 scripts/import_spotify_streaming_history.py
2) python3 scripts/spotify_metrics.py --year 2026
3) python3 scripts/spotify_daily_playlist.py --tewnidge-playlist-id <ID>

