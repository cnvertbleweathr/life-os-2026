// Pixel-art title loops, built to the pixel-art-sprites skill:
//  · Integer scaling in DEVICE pixels (crisp at 1×, 1.25×, 1.5×, 2×, 3×), image-rendering: pixelated.
//  · 16×16 character frames (FW×FH), 4-frame run cycle: contact → passing → contact (mirror) → passing (mirror),
//    arms opposite legs, torso drops 1px on contact.
//  · Ground scrolls exactly one foot-travel per frame (STRIDE px), so feet plant instead of sliding.
//  · One consistent outline rule: every character gets a 1px outer outline, generated, never hand-drawn.
//    Scenery has no outline.
//  · Light from the top-left: shade sits on the right/bottom of every form. Closed palette: only --px-* colours.
// Motion rules for ONS daily screens: stops offscreen and in hidden tabs, click pauses (remembered),
// prefers-reduced-motion shows a still frame.
(function () {
  const H = 32, FW = 16, FH = 16, KEY = 'ons-px-paused';
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const rnd = i => (((i * 2654435761) >>> 0) % 1000) / 1000;

  // ---------- Sprite parts (16 wide). Legend:
  // h helmet · g helmet shade · m facemask · H hair · s skin · t skin shade · e eye
  // j shirt · k shirt shade · w number · b ball · p near leg · q far leg (shade) · x shoe · r shorts
  const HELMET = [
    '......hhhh......',
    '.....hhhhhhm....',
    '.....hhhhhsm....',
    '.....ghhhgsm....',
    '......ggts......',
  ];
  const HAIR = [
    '......HHHH......',
    '.....HHHHHH.....',
    '.....HHHHses....',
    '.....HHHssss....',
    '......tsss......',
  ];
  const TORSO = [
    '.....jjjjk......',
    '.....jjjwk......',
    '.....jjjjk......',
    '......jjkk......',
  ];
  // legs: hips on cols 6–9. Contact = 5 rows (torso low), passing = 6 rows (torso high).
  const LEGS = [
    [ // 0 contact: near leg forward
      '......qqpp......',
      '......qq.pp.....',
      '.....qq...pp....',
      '....qq.....pp...',
      '...xx.......xx..',
    ],
    [ // 1 passing: near leg supports, far leg bent behind
      '......qqpp......',
      '.....qq.pp......',
      '....qq..pp......',
      '...xx...pp......',
      '........pp......',
      '........xxx.....',
    ],
    [ // 2 contact: far leg forward (mirror)
      '......ppqq......',
      '......pp.qq.....',
      '.....pp...qq....',
      '....pp.....qq...',
      '...xx.......xx..',
    ],
    [ // 3 passing: far leg supports, near leg bent behind (mirror)
      '......ppqq......',
      '.....pp.qq......',
      '....pp..qq......',
      '...xx...qq......',
      '........qq......',
      '........xxx.....',
    ],
  ];
  // arm overlays per frame, [row, col, char] relative to the upper body (head 0–4, torso 5–8)
  const ARMS = {
    carrier: f => [[6, 10, 'b'], [6, 11, 'b'], [7, 10, 'b'], [7, 11, 'b'], [7, 9, 's'],   // ball tucked in the near arm
      ...(f === 2 ? [[6, 4, 't'], [7, 3, 't']] : f % 2 ? [[7, 4, 't']] : [])],          // far arm swings opposite the far leg
    tackler: f => [[6, 10, 'j'], [6, 11, 's'], [6, 12, 's'], [7, 10, 'k'], [7, 11, 't'], ...(f % 2 ? [] : [[5, 12, 's']])],
    jogger: f => f === 0 ? [[6, 4, 's'], [7, 3, 's']] : f === 2 ? [[7, 10, 's'], [6, 11, 's']] : [[7, 9, 's'], [8, 9, 's']],
  };

  function frame(head, arms, f, shorts) {
    const g = Array.from({ length: FH }, () => Array(FW).fill('.'));
    const legs = LEGS[f], upper = head.concat(TORSO), top = FH - legs.length - upper.length;
    upper.forEach((r, y) => [...r].forEach((c, x) => { if (c !== '.') g[top + y][x] = c; }));
    arms(f).forEach(([y, x, c]) => { g[top + y][x] = c; });
    legs.forEach((r, y) => [...r].forEach((c, x) => {
      if (c === '.') return;
      g[top + upper.length + y][x] = shorts && y === 0 ? 'r' : c;
    }));
    return g;
  }
  const SPRITES = {};
  ['carrier', 'tackler', 'jogger'].forEach(k => {
    SPRITES[k] = [0, 1, 2, 3].map(f => frame(k === 'jogger' ? HAIR : HELMET, ARMS[k], f, k === 'jogger'));
  });

  // Draw a grid with a generated 1px outer outline (4-neighbour), so every character shares one outline weight.
  function drawSprite(ctx, g, ox, oy, map, outline) {
    const filled = (x, y) => y >= 0 && y < FH && x >= 0 && x < FW && g[y][x] !== '.';
    ctx.fillStyle = outline;
    for (let y = -1; y <= FH; y++) for (let x = -1; x <= FW; x++) {
      if (filled(x, y)) continue;
      if (filled(x - 1, y) || filled(x + 1, y) || filled(x, y - 1) || filled(x, y + 1)) ctx.fillRect(ox + x, oy + y, 1, 1);
    }
    for (let y = 0; y < FH; y++) for (let x = 0; x < FW; x++) {
      const c = map[g[y][x]]; if (!c) continue; ctx.fillStyle = c; ctx.fillRect(ox + x, oy + y, 1, 1);
    }
  }
  function grid(ctx, rows, x, y, map) {
    for (let r = 0; r < rows.length; r++) for (let c = 0; c < rows[r].length; c++) {
      const col = map[rows[r][c]]; if (col) { ctx.fillStyle = col; ctx.fillRect(x + c, y + r, 1, 1); }
    }
  }
  const px = (ctx, col, x, y, w = 1, h = 1) => { ctx.fillStyle = col; ctx.fillRect(x, y, w, h); };

  const TREE = ['.TTT.', 'TTTTD', 'TTTDD', '.TDD.', '..R..', '..R..'];
  const CLOUD = ['..CC....', '.CCCC.C.', 'CCCCCCCC'];

  const KEYS = ['outline', 'skin', 'skin-d', 'team', 'team-d', 'foe', 'foe-d', 'white', 'white-d', 'mask', 'ball', 'hair', 'run', 'run-d', 'navy', 'navy-d',
    'stand', 'grass', 'grass2', 'grass-d', 'line', 'post', 'sky', 'cloud', 'sun', 'hill', 'hill2', 'tree', 'tree-d', 'trunk', 'ground', 'ground2', 'star'];
  function palette() {
    const cs = getComputedStyle(document.documentElement), P = { dark: document.documentElement.dataset.theme === 'dark' };
    KEYS.forEach(k => P[k] = cs.getPropertyValue('--px-' + k).trim());
    return P;
  }

  // ---------- Degenerates Corner: ball carrier breaking upfield, a defender on his heels
  const cfb = {
    ms: 125, stride: 4,       // run: 125 ms a frame (fast band), 4 px of foot travel a frame
    draw(ctx, W, n, P) {
      const d = n * this.stride, f = n % 4;
      px(ctx, P.stand, 0, 0, W, 10);
      const crowd = [P.team, P.foe, P.white, P['white-d']], off = Math.floor(d / 4), beat = Math.floor(n / 2);
      for (let x = 1; x < W; x += 2) for (let y = 2; y < 9; y += 2) {
        const i = (x + off) * 7 + y * 131, h = rnd(i); if (h < 0.3) continue;
        px(ctx, crowd[Math.floor(h * 97) % crowd.length], x, y - (rnd(i + beat * 17) < 0.1 ? 1 : 0));
      }
      if (P.dark) for (let x = 6; x < W; x += 28) px(ctx, P.star, x, 0, 4, 1);
      px(ctx, P.outline, 0, 9, W, 1);
      for (let x = 0; x < W; x++) {
        const wx = x + d;
        px(ctx, Math.floor(wx / 10) % 2 ? P.grass : P.grass2, x, 10, 1, H - 10);
        if (wx % 20 === 0) px(ctx, P.line, x, 11, 1, H - 11);
      }
      px(ctx, P.line, 0, 10, W, 1);
      const rx = Math.floor(W * 0.56) - 8;
      let scoring = false;
      for (let k = Math.floor(d / 260) - 1; k <= Math.floor(d / 260) + 1; k++) {
        const gx = k * 260 + 220 - d; if (gx > W + 30 || gx < -40) continue;
        px(ctx, P['team-d'], gx, 11, 20, H - 11); px(ctx, P.line, gx, 11, 1, H - 11);
        const p = gx + 20;
        px(ctx, P.post, p, 13, 1, 16); px(ctx, P.post, p - 4, 12, 9, 1); px(ctx, P.post, p - 4, 3, 1, 9); px(ctx, P.post, p + 4, 3, 1, 9);
        if (rx + 8 >= gx && rx + 8 <= gx + 20) scoring = true;
      }
      // defender trails by 15–21 px, drifting slowly; his cycle runs half a step behind
      const dx = rx - 18 + Math.round(3 * Math.sin(n / 9));
      px(ctx, P['grass-d'], dx + 3, 29, 9, 1); px(ctx, P['grass-d'], rx + 3, 29, 9, 1);
      const team = { h: P.team, g: P['team-d'], m: P.mask, s: P.skin, t: P['skin-d'], j: P.navy, k: P['navy-d'], w: P.team, b: P.ball, p: P.white, q: P['white-d'], x: P.outline };
      const foe = { h: P.foe, g: P['foe-d'], m: P.mask, s: P.skin, t: P['skin-d'], j: P.white, k: P['white-d'], w: P.foe, p: P.white, q: P['white-d'], x: P.outline };
      drawSprite(ctx, SPRITES.tackler[(f + 2) % 4], dx, 13, foe, P.outline);
      drawSprite(ctx, SPRITES.carrier[f], rx, 13, team, P.outline);
      if (scoring && n % 2) { px(ctx, P.post, rx + 4, 11); px(ctx, P.post, rx + 13, 11); px(ctx, P.post, rx + 2, 14); px(ctx, P.post, rx + 15, 14); }
    },
  };

  // ---------- This week: a jogger on the trail; sun by day, moon and stars at night
  const week = {
    ms: 160, stride: 4,       // jog: 160 ms a frame (normal band)
    draw(ctx, W, n, P) {
      const d = n * this.stride, f = n % 4;
      px(ctx, P.sky, 0, 0, W, H);
      if (P.dark) {
        for (let i = 0; i < W / 4; i++) { const x = Math.floor(rnd(i * 13) * W), y = Math.floor(rnd(i * 29) * 14); if (rnd(i + Math.floor(n / 3) * 31) > 0.15) px(ctx, P.star, x, y); }
        const mx = W - 16; px(ctx, P.sun, mx + 1, 3, 4, 1); px(ctx, P.sun, mx, 4, 5, 3); px(ctx, P.sun, mx + 1, 7, 4, 1); px(ctx, P.sky, mx + 3, 4, 2, 2);
      } else {
        const sx = W - 16; px(ctx, P.sun, sx + 1, 3, 4, 6); px(ctx, P.sun, sx, 4, 6, 4);
        if (Math.floor(n / 3) % 2) { px(ctx, P.sun, sx + 2, 1, 2, 1); px(ctx, P.sun, sx + 2, 10, 2, 1); px(ctx, P.sun, sx - 2, 5, 1, 2); px(ctx, P.sun, sx + 7, 5, 1, 2); }
      }
      for (let k = 0; k < 4; k++) {
        const span = W + 40, cx = ((k * 61 - Math.floor(d / 8)) % span + span) % span - 20;
        grid(ctx, CLOUD, cx, 3 + (k % 2) * 4, { C: P.cloud });
      }
      for (let x = 0; x < W; x++) {
        const o1 = x + Math.floor(d / 4), h1 = 6 + Math.round(2.5 * Math.sin(o1 / 11) + 1.5 * Math.sin(o1 / 5));
        px(ctx, P.hill2, x, 27 - h1, 1, h1);
        const o2 = x + Math.floor(d / 2), h2 = 3 + Math.round(2 * Math.sin(o2 / 7));
        px(ctx, P.hill, x, 27 - h2, 1, h2);
      }
      const tOff = Math.floor(d * 3 / 4);
      for (let k = Math.floor(tOff / 46) - 1; k <= Math.floor((tOff + W) / 46) + 1; k++) grid(ctx, TREE, k * 46 + 13 - tOff, 21, { T: P.tree, D: P['tree-d'], R: P.trunk });
      px(ctx, P.ground, 0, 27, W, H - 27);
      for (let x = 0; x < W; x++) { if ((x + d) % 9 === 0) px(ctx, P.ground2, x, 29); if ((x + d) % 13 === 4) px(ctx, P.ground2, x, 31); }
      const jx = Math.floor(W * 0.42) - 8;
      px(ctx, P.ground2, jx + 3, 29, 9, 1);
      drawSprite(ctx, SPRITES.jogger[f], jx, 13,
        { H: P.hair, s: P.skin, t: P['skin-d'], e: P.outline, j: P.run, k: P['run-d'], w: P.run, r: P.outline, p: P.skin, q: P['skin-d'], x: P.white }, P.outline);
    },
  };

  const SCENES = { cfb, week };

  function mount(el) {
    const canvas = el.querySelector('canvas'), ctx = canvas.getContext('2d'), scene = SCENES[el.dataset.scene];
    let W = 96, P = palette(), clock = 0, prev = 0, raf = 0, last = -1, visible = true, paused = false;
    try { paused = localStorage.getItem(KEY) === '1'; } catch (e) {}

    const draw = force => { const n = Math.floor(clock / scene.ms); if (!force && n === last) return; last = n; ctx.clearRect(0, 0, W, H); scene.draw(ctx, W, n, P); };
    const running = () => !paused && visible && !reduce.matches && !document.hidden;
    const loop = now => { clock += Math.max(0, Math.min(100, now - prev)); prev = now; draw(false); raf = running() ? requestAnimationFrame(loop) : 0; };
    const sync = () => {
      el.setAttribute('aria-pressed', paused || reduce.matches);
      el.disabled = reduce.matches;
      el.title = reduce.matches ? 'Animation off (reduced motion)' : paused ? 'Play animation' : 'Pause animation';
      if (running() && !raf) { prev = performance.now(); raf = requestAnimationFrame(loop); }
    };
    // Integer scale in device pixels: each art pixel is exactly s device pixels.
    const size = () => {
      const dpr = window.devicePixelRatio || 1;
      const s = Math.max(1, Math.floor(el.clientHeight * dpr / H)), css = s / dpr;
      W = Math.ceil(el.clientWidth / css);
      canvas.width = W; canvas.height = H;
      canvas.style.width = W * css + 'px'; canvas.style.height = H * css + 'px';
      canvas.style.marginTop = Math.floor((el.clientHeight - H * css) / 2 * dpr) / dpr + 'px';
      ctx.imageSmoothingEnabled = false;
      draw(true);
    };

    el.addEventListener('click', () => { paused = !paused; try { localStorage.setItem(KEY, paused ? '1' : '0'); } catch (e) {} sync(); });
    new ResizeObserver(size).observe(el);
    matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`).addEventListener('change', size);
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; sync(); }).observe(el);
    new MutationObserver(() => { P = palette(); draw(true); }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    document.addEventListener('visibilitychange', sync);
    reduce.addEventListener('change', () => { draw(true); sync(); });
    size(); sync();
  }

  addEventListener('DOMContentLoaded', () => document.querySelectorAll('.scene[data-scene]').forEach(mount));
})();
