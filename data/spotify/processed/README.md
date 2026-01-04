# Spotify – Processed Data

This directory contains derived data from Spotify sources.

## Files

- tewnidge_artists.csv  
  Artists extracted from the "Tewnidge" playlist.  
  Used as the source of truth for downstream integrations (e.g. Bandsintown).

## How to regenerate
Run:
  python3 scripts/spotify_extract_artists.py
