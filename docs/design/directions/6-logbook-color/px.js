// Pixel-art title loops. One small canvas per page (<button class="scene" data-scene="…">), drawn at
// 32 logical rows and scaled up with nearest-neighbour. Colours come from the theme's CSS variables,
// so every scene redraws itself for light and dark.
// Motion rules (ONS daily screens): 12 fps, stops offscreen and in hidden tabs, click pauses
// (remembered), prefers-reduced-motion shows a still frame. Nothing else on the page animates.
(function () {
  const H = 32, FPS = 12, KEY = 'ons-px-paused';
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const rnd = i => (((i * 2654435761) >>> 0) % 1000) / 1000;

  // ---- Sprites: 8×12, facing right. H head/helmet · S skin · J jersey/shirt · W stripe · B ball or hand · P pants · K shoes
  const RUN = [
    ['..HHH...', '.HHHHH..', '.HHSSS..', '..SSS...', '..JJJ...', '.JJJBB..', '.JJWBBB.', '..JJJ...', '..PPP...', '.PP.PP..', 'PP...PP.', 'K.....K.'],
    ['..HHH...', '.HHHHH..', '.HHSSS..', '..SSS...', '..JJJ...', '.JJJBB..', '.JJWBBB.', '..JJJ...', '..PPP...', '..PPP...', '..P.PP..', '..K..K..'],
  ];
  const JOG = [
    ['..HHH...', '.HHHHS..', '.HSSSS..', '..SSS...', '..JJJ...', '.JJJJS..', 'SJJJJ...', '..JJJ...', '..PPP...', '.PP.PP..', 'PP...PP.', 'K.....K.'],
    ['..HHH...', '.HHHHS..', '.HSSSS..', '..SSS...', '..JJJ...', '.SJJJ...', '..JJJS..', '..JJJ...', '..PPP...', '..PPP...', '..P.PP..', '..K..K..'],
  ];
  const TREE = ['.TTT.', 'TTTTT', 'TTTTT', 'TTTTT', '.TTT.', '..R..', '..R..'];
  const CLOUD = ['..CC....', '.CCCC.C.', 'CCCCCCCC'];

  function spr(ctx, rows, x, y, map) {
    for (let r = 0; r < rows.length; r++) for (let c = 0; c < rows[r].length; c++) {
      const col = map[rows[r][c]]; if (!col) continue;
      ctx.fillStyle = col; ctx.fillRect(x + c, y + r, 1, 1);
    }
  }
  function px(ctx, col, x, y, w = 1, h = 1) { ctx.fillStyle = col; ctx.fillRect(x, y, w, h); }

  function palette() {
    const cs = getComputedStyle(document.documentElement), g = n => cs.getPropertyValue(n).trim();
    const P = { dark: document.documentElement.dataset.theme === 'dark' };
    ['sky', 'grass', 'grass2', 'line', 'stand', 'zone', 'post', 'ball', 'ground', 'ground2', 'hill', 'hill2', 'tree', 'trunk',
      'sun', 'cloud', 'skin', 'ink', 'hair', 'away', 'star', 'shadow'].forEach(k => P[k] = g('--px-' + k));
    ['run', 'edge', 'check', 'plan', 'habit', 'read'].forEach(k => P[k] = g('--' + k + '-mark'));
    return P;
  }

  // ---- Degenerates Corner: a ball carrier breaking upfield with a defender on his heels
  function cfb(ctx, W, t, P) {
    const d = Math.floor(t * 24);
    // stands and crowd (slow parallax), stadium lights at night
    px(ctx, P.stand, 0, 0, W, 10);
    const crowd = [P.edge, P.check, P.run, P.line, P.plan], beat = Math.floor(t * 4), off = Math.floor(d * 0.25);
    for (let x = 1; x < W; x += 2) for (let y = 2; y < 9; y += 2) {
      const i = (x + off) * 7 + y * 131, h = rnd(i); if (h < 0.3) continue;
      px(ctx, crowd[Math.floor(h * 97) % crowd.length], x, y - (rnd(i + beat * 17) < 0.1 ? 1 : 0));
    }
    if (P.dark) for (let x = 6; x < W; x += 28) px(ctx, P.star, x, 0, 4, 1);
    px(ctx, P.ink, 0, 9, W, 1);
    // field: mown stripes, yard lines every 20, sideline
    for (let x = 0; x < W; x++) {
      const wx = x + d;
      px(ctx, Math.floor(wx / 10) % 2 ? P.grass : P.grass2, x, 10, 1, H - 10);
      if (wx % 20 === 0) px(ctx, P.line, x, 11, 1, H - 11);
    }
    px(ctx, P.line, 0, 10, W, 1);
    // end zone + goalpost every 260 px of field
    let scoring = false;
    const rx = Math.floor(W * 0.56);
    for (let k = Math.floor(d / 260) - 1; k <= Math.floor(d / 260) + 1; k++) {
      const gx = k * 260 + 220 - d;
      if (gx > W + 30 || gx < -40) continue;
      px(ctx, P.zone, gx, 11, 20, H - 11);
      px(ctx, P.line, gx, 11, 1, H - 11);
      const pxl = gx + 20;
      px(ctx, P.post, pxl, 13, 1, 16); px(ctx, P.post, pxl - 4, 12, 9, 1); px(ctx, P.post, pxl - 4, 3, 1, 9); px(ctx, P.post, pxl + 4, 3, 1, 9);
      if (rx + 4 >= gx && rx + 4 <= gx + 20) scoring = true;
    }
    // players
    const f = Math.floor(t * 10) % 2;
    const dx = rx - 15 - Math.round(3 * Math.sin(t * 1.3));
    px(ctx, P.shadow, dx + 1, 29, 6, 1); px(ctx, P.shadow, rx + 1, 29, 6, 1);
    spr(ctx, RUN[1 - f], dx, 17 - (f ? 0 : 1), { H: P.check, S: P.skin, J: P.away, W: P.check, B: P.skin, P: P.away, K: P.ink });
    spr(ctx, RUN[f], rx, 17 - f, { H: P.edge, S: P.skin, J: P.ink, W: P.edge, B: P.ball, P: P.line, K: P.ink });
    if (scoring && Math.floor(t * 6) % 2) { px(ctx, P.post, rx + 2, 13); px(ctx, P.post, rx + 6, 12); px(ctx, P.post, rx - 1, 14); px(ctx, P.post, rx + 9, 14); }
  }

  // ---- This week: a jogger on the trail, hills and trees going by; sun by day, moon and stars at night
  function week(ctx, W, t, P) {
    const d = Math.floor(t * 14);
    px(ctx, P.sky, 0, 0, W, H);
    if (P.dark) {
      for (let i = 0; i < W / 4; i++) { const x = Math.floor(rnd(i * 13) * W), y = Math.floor(rnd(i * 29) * 16); if (rnd(i + Math.floor(t * 2) * 31) > 0.15) px(ctx, P.star, x, y); }
      const mx = W - 16; px(ctx, P.sun, mx + 1, 3, 4, 1); px(ctx, P.sun, mx, 4, 5, 3); px(ctx, P.sun, mx + 1, 7, 4, 1); px(ctx, P.sky, mx + 3, 4, 2, 2);
    } else {
      const sx = W - 16; px(ctx, P.sun, sx + 1, 3, 4, 6); px(ctx, P.sun, sx, 4, 6, 4);
      if (Math.floor(t * 2) % 2) { px(ctx, P.sun, sx + 2, 1, 2, 1); px(ctx, P.sun, sx + 2, 10, 2, 1); px(ctx, P.sun, sx - 2, 5, 1, 2); px(ctx, P.sun, sx + 7, 5, 1, 2); }
    }
    for (let k = 0; k < 4; k++) {
      const span = W + 40, cx = ((k * 61 - Math.floor(d * 0.2)) % span + span) % span - 20;
      spr(ctx, CLOUD, cx, 3 + (k % 2) * 4, { C: P.cloud });
    }
    for (let x = 0; x < W; x++) {
      const o1 = x + d * 0.3, h1 = 6 + Math.round(2.5 * Math.sin(o1 / 11) + 1.5 * Math.sin(o1 / 5));
      px(ctx, P.hill2, x, 27 - h1, 1, h1);
      const o2 = x + d * 0.55, h2 = 3 + Math.round(2 * Math.sin(o2 / 7));
      px(ctx, P.hill, x, 27 - h2, 1, h2);
    }
    for (let k = Math.floor(d * 0.8 / 46) - 1; k <= Math.floor((d * 0.8 + W) / 46) + 1; k++) {
      spr(ctx, TREE, k * 46 + 13 - Math.floor(d * 0.8), 20, { T: P.tree, R: P.trunk });
    }
    px(ctx, P.ground, 0, 27, W, H - 27);
    for (let x = 0; x < W; x++) { if ((x + d) % 9 === 0) px(ctx, P.ground2, x, 29); if ((x + d) % 13 === 4) px(ctx, P.ground2, x, 31); }
    const f = Math.floor(t * 8) % 2, jx = Math.floor(W * 0.42);
    px(ctx, P.shadow, jx + 1, 28, 6, 1);
    spr(ctx, JOG[f], jx, 16 - f, { H: P.hair, S: P.skin, J: P.run, P: P.ink, K: P.line });
  }

  const SCENES = { cfb, week };

  function mount(el) {
    const canvas = el.querySelector('canvas'), ctx = canvas.getContext('2d'), scene = SCENES[el.dataset.scene];
    let W = 96, P = palette(), t = 2.4, prev = 0, raf = 0, last = -1, visible = true, paused = false;
    try { paused = localStorage.getItem(KEY) === '1'; } catch (e) {}

    const draw = force => { const fi = Math.floor(t * FPS); if (!force && fi === last) return; last = fi; scene(ctx, W, fi / FPS, P); };
    const running = () => !paused && visible && !reduce.matches && !document.hidden;
    const loop = now => { t += Math.min(0.1, (now - prev) / 1000); prev = now; draw(false); raf = running() ? requestAnimationFrame(loop) : 0; };
    const sync = () => {
      el.setAttribute('aria-pressed', paused || reduce.matches);
      el.disabled = reduce.matches;
      el.title = reduce.matches ? 'Animation off (reduced motion)' : paused ? 'Play animation' : 'Pause animation';
      if (running() && !raf) { prev = performance.now(); raf = requestAnimationFrame(loop); }
    };
    const size = () => {
      const s = Math.max(1, Math.round(el.clientHeight / H));
      W = Math.ceil(el.clientWidth / s);
      canvas.width = W; canvas.height = H;
      canvas.style.width = W * s + 'px'; canvas.style.height = H * s + 'px';
      draw(true);
    };

    el.addEventListener('click', () => { paused = !paused; try { localStorage.setItem(KEY, paused ? '1' : '0'); } catch (e) {} sync(); });
    new ResizeObserver(size).observe(el);
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; sync(); }).observe(el);
    new MutationObserver(() => { P = palette(); draw(true); }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    document.addEventListener('visibilitychange', sync);
    reduce.addEventListener('change', () => { draw(true); sync(); });
    size(); sync();
  }

  addEventListener('DOMContentLoaded', () => document.querySelectorAll('.scene[data-scene]').forEach(mount));
})();
