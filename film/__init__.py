"""ONS film GIF renderer (Phase 3 of docs/film/ONS_FILM_SECTION_PLAN.md).

  palette.py   the --px-* tokens from web/app/globals.css, light and dark
  canvas.py    role-indexed frames → the two GIFs (web = light, matrix = dark)
  font.py      the 3×5 pixel font
  motifs.py    original mood loops (render_mode "motif")
  sprites/     hand-built public-domain scenes (render_mode "sprite")
  clip.py      your own Plex copy, pixelated (render_mode "plex_clip")

Format: 64×32 art pixels, 40 frames × 125 ms = a 5-second loop.
scripts/film_gif_render.py drives it.
"""

W, H, FRAMES, FRAME_MS = 64, 32, 40, 125
