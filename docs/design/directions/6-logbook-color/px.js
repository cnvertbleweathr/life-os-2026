// Pixel-art title loops, built to the pixel-art-sprites skill (.claude/skills/pixel-art-sprites):
//  · Integer scaling in DEVICE pixels; image-rendering: pixelated.
//  · Characters on a 20×18 frame. 6-frame run cycle (patterns.md "run: 6"): contact → down → float, then
//    the same three mirrored. Legs have knees (hip → knee → foot), arms swing opposite the legs, the body
//    bobs 1px (low on "down", high on "float").
//  · Ground scrolls one foot-travel per frame (stride), so the support foot stays planted.
//  · One outline rule: every character gets a generated 1px outer outline; scenery gets none.
//  · Light from the top-left. Closed palette: only --px-* colours.
// ONS motion rules: stops offscreen / hidden tab, click pauses (remembered), reduced motion = still frame.
(function () {
  const H = 32, FW = 20, FH = 18, KEY = 'ons-px-paused';
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const rnd = i => (((i * 2654435761) >>> 0) % 1000) / 1000;

  // ---------------- Character frames ----------------
  // h helmet · g helmet shade · m facemask · H hair/cap · s skin · t skin shade · e eye
  // j shirt · k shirt shade · w trim/number · b ball · p near leg · q far leg · r shorts · x shoe
  const HELMET = ['........hhhh........', '.......hhhhhhm......', '.......hhhhhsm......', '.......ghhhgsm......', '........ggts........'];
  const HAIR = ['........HHHH........', '.......HHHHHH.......', '.......HHHHses......', '.......HHHssss......', '........tsss........'];
  const CAP = ['........HHHH........', '.......HHHHHHH......', '.......HHHsses......', '........tsss........', '........tss.........'];
  const TORSO = ['.......jjjjk........', '.......jjjwk........', '.......jjjjk........', '........jjkk........'];
  const STRIPES = ['.......jkjkj........', '.......jkjkj........', '.......jkjkj........', '........kjkj........'];

  // Leg poses relative to the hip: K = knee, P = foot (x forward, y down). bob: body offset.
  const POSES = [
    { bob: 0, near: { K: [2, 3], P: [4, 7] }, far: { K: [-1, 4], P: [-4, 2] } },   // contact: reach forward, heel kick behind
    { bob: 1, near: { K: [1, 3], P: [0, 6] }, far: { K: [2, 3], P: [-1, 4] } },    // down: support bent, knee passing
    { bob: -1, near: { K: [-2, 4], P: [-5, 7] }, far: { K: [3, 1], P: [3, 5] } },  // float: push off behind, knee drive
  ];
  const ARM = { fwd: { E: [2, 2], H: [4, 1] }, mid: { E: [0, 3], H: [1, 4] }, back: { E: [-2, 2], H: [-3, 4] } };
  const FAR_ARM = ['fwd', 'mid', 'back', 'back', 'mid', 'fwd'];
  const OPP = { fwd: 'back', mid: 'mid', back: 'fwd' };

  function line(x0, y0, x1, y1, cb) {
    const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
    let err = dx + dy, i = 0;
    for (;;) { cb(x0, y0, i++); if (x0 === x1 && y0 === y1) break; const e2 = 2 * err; if (e2 >= dy) { err += dy; x0 += sx; } if (e2 <= dx) { err += dx; y0 += sy; } }
  }
  function build(kind, f) {
    const g = Array.from({ length: FH }, () => Array(FW).fill('.'));
    const set = (x, y, c) => { if (y >= 0 && y < FH && x >= 0 && x < FW) g[y][x] = c; };
    const pose = POSES[f % 3], mirror = f >= 3;
    const L = mirror ? { near: pose.far, far: pose.near } : pose;
    const top = 1 + pose.bob, hipY = top + 9, sh = [9, top + 6];
    const jog = kind === 'jogger';
    const leg = (hx, p, c) => {
      const kx = hx + p.K[0], ky = hipY + p.K[1], fx = hx + p.P[0], fy = Math.min(FH - 1, hipY + p.P[1]);
      line(hx, hipY, kx, ky, (x, y, i) => { const cc = jog && i < 2 ? 'r' : c; set(x, y, cc); set(x + 1, y, cc); });
      line(kx, ky, fx, fy, (x, y) => { set(x, y, c); set(x + 1, y, c); });
      set(fx, fy, 'x'); set(fx + 1, fy, 'x'); set(fx + 2, fy, 'x');
    };
    const arm = (pos, upper, fore) => {
      const a = ARM[pos], ex = sh[0] + a.E[0], ey = sh[1] + a.E[1], hx = sh[0] + a.H[0], hy = sh[1] + a.H[1];
      line(sh[0], sh[1], ex, ey, (x, y) => set(x, y, upper));
      line(ex, ey, hx, hy, (x, y) => set(x, y, fore));
    };
    // behind the body: far arm, far leg
    arm(FAR_ARM[f], 'k', 't');
    leg(9, L.far, 'q');
    // body
    const head = jog ? HAIR : kind === 'ref' ? CAP : HELMET;
    head.concat(kind === 'ref' ? STRIPES : TORSO).forEach((r, y) => [...r].forEach((c, x) => { if (c !== '.') set(x, top + y, c); }));
    leg(10, L.near, 'p');
    // in front: the near arm, or what it holds
    if (kind === 'carrier') { [[12, 6], [13, 6], [12, 7], [13, 7], [14, 7]].forEach(([x, y]) => set(x, top + y, 'b')); set(11, top + 7, 's'); }
    else if (kind === 'tackler') { set(12, top + 6, 'j'); set(13, top + 6, 's'); set(14, top + 6, 's'); set(12, top + 7, 'k'); set(13, top + 7, 't'); set(14, top + 5 + (f % 2), 's'); }
    else arm(OPP[FAR_ARM[f]], 'j', 's');
    return g;
  }
  const SPR = {};
  ['carrier', 'tackler', 'ref', 'jogger'].forEach(k => SPR[k] = [0, 1, 2, 3, 4, 5].map(f => build(k, f)));

  // Dog (10×6), 2-frame gallop, and birds (3×2)
  const DOG = [
    ['........dd', 'd......dde', '.ddddddddd', '.DDDDDDDD.', 'd.d....d.d', '..........'],
    ['........dd', '.d.....dde', '.ddddddddd', '.DDDDDDDD.', '..dd..dd..', '..........'],
  ];
  const BIRD = [['b.b', '.b.'], ['...', 'bbb']];
  const TREE = ['..TTT..', '.TTTTD.', 'TTTTTDD', 'TTTTDDD', '.TTDDD.', '...R...', '...R...'];
  const CLOUD = ['..CC....', '.CCCC.C.', 'CCCCCCCC'];

  // 3×5 pixel font for numbers and a few letters
  const FONT = {
    0: ['111', '101', '101', '101', '111'], 1: ['010', '110', '010', '010', '111'], 2: ['111', '001', '111', '100', '111'],
    3: ['111', '001', '011', '001', '111'], 4: ['101', '101', '111', '001', '001'], 5: ['111', '100', '111', '001', '111'],
    6: ['111', '100', '111', '101', '111'], 7: ['111', '001', '010', '010', '010'], 8: ['111', '101', '111', '101', '111'],
    9: ['111', '101', '111', '001', '111'], '-': ['000', '000', '111', '000', '000'], T: ['111', '010', '010', '010', '010'],
    D: ['110', '101', '101', '101', '110'], '!': ['010', '010', '010', '000', '010'],
  };
  function text(ctx, str, x, y, col) {
    ctx.fillStyle = col;
    for (const ch of String(str)) { const gl = FONT[ch]; if (gl) gl.forEach((r, yy) => [...r].forEach((b, xx) => { if (b === '1') ctx.fillRect(x + xx, y + yy, 1, 1); })); x += 4; }
  }

  function drawSprite(ctx, g, ox, oy, map, outline) {
    const h = g.length, w = g[0].length, filled = (x, y) => y >= 0 && y < h && x >= 0 && x < w && g[y][x] !== '.';
    ctx.fillStyle = outline;
    for (let y = -1; y <= h; y++) for (let x = -1; x <= w; x++) {
      if (!filled(x, y) && (filled(x - 1, y) || filled(x + 1, y) || filled(x, y - 1) || filled(x, y + 1))) ctx.fillRect(ox + x, oy + y, 1, 1);
    }
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const c = map[g[y][x]]; if (c) { ctx.fillStyle = c; ctx.fillRect(ox + x, oy + y, 1, 1); } }
  }
  const toGrid = rows => rows.map(r => [...r]);
  function tiles(ctx, rows, x, y, map) {
    for (let r = 0; r < rows.length; r++) for (let c = 0; c < rows[r].length; c++) { const col = map[rows[r][c]]; if (col) { ctx.fillStyle = col; ctx.fillRect(x + c, y + r, 1, 1); } }
  }
  const px = (ctx, col, x, y, w = 1, h = 1) => { ctx.fillStyle = col; ctx.fillRect(x, y, w, h); };

  const KEYS = ['outline', 'skin', 'skin-d', 'team', 'team-d', 'foe', 'foe-d', 'white', 'white-d', 'mask', 'ball', 'hair', 'run', 'run-d', 'navy', 'navy-d',
    'stand', 'track', 'grass', 'grass2', 'grass-d', 'line', 'post', 'board', 'sky', 'cloud', 'sun', 'mtn', 'mtn-d', 'snow', 'hill', 'hill2', 'tree', 'tree-d', 'trunk',
    'ground', 'ground2', 'star', 'dog', 'dog-d', 'bloom1', 'bloom2'];
  function palette() {
    const cs = getComputedStyle(document.documentElement), P = { dark: document.documentElement.dataset.theme === 'dark' };
    KEYS.forEach(k => P[k] = cs.getPropertyValue('--px-' + k).trim());
    return P;
  }

  // ---------------- Degenerates Corner ----------------
  const YARDS = [10, 20, 30, 40, 50, 40, 30, 20, 10];
  const cfb = {
    ms: 100, stride: 4, still: 2,
    draw(ctx, W, n, P) {
      const d = n * this.stride, f = n % 6, beat = Math.floor(n / 2);
      // stands + crowd; light towers at night
      px(ctx, P.stand, 0, 0, W, 8);
      const crowd = [P.team, P.foe, P.white, P['white-d']], off = Math.floor(d / 4);
      for (let x = 1; x < W; x += 2) for (let y = 1; y < 8; y += 2) {
        const i = (x + off) * 7 + y * 131, h = rnd(i); if (h < 0.3) continue;
        px(ctx, crowd[Math.floor(h * 97) % crowd.length], x, y - (rnd(i + beat * 17) < 0.1 ? 1 : 0));
      }
      if (P.dark) for (let x = 36; x < W; x += 30) { px(ctx, P.star, x, 0, 5, 1); px(ctx, P['white-d'], x + 2, 1, 1, 6); }
      // scoreboard: this season's record
      px(ctx, P.outline, 3, 0, 25, 8); px(ctx, P.board, 4, 1, 23, 6); text(ctx, '17-11', 6, 2, P.post);
      // sideline: track and coaches in headsets
      px(ctx, P.track, 0, 8, W, 3);
      for (let k = Math.floor(d / 33) - 1; k <= Math.floor((d + W) / 33) + 1; k++) {
        if (rnd(k * 3 + 1) < 0.35) continue;
        const cx = k * 33 - d + Math.floor(rnd(k) * 12), c = rnd(k * 5) < 0.5 ? P.team : P.navy;
        px(ctx, P.skin, cx, 7); px(ctx, P.outline, cx - 1, 7); px(ctx, c, cx - 1, 8, 3, 2);
      }
      // field: stripes, yard lines, hash marks, yard numbers
      for (let x = 0; x < W; x++) {
        const wx = x + d;
        px(ctx, Math.floor(wx / 10) % 2 ? P.grass : P.grass2, x, 11, 1, H - 11);
        if (wx % 20 === 0) px(ctx, P.line, x, 12, 1, H - 12);
        if (wx % 4 === 0) { px(ctx, P.line, x, 15); px(ctx, P.line, x, 27); }
      }
      px(ctx, P.line, 0, 11, W, 1);
      for (let k = Math.floor(d / 40) - 1; k <= Math.floor((d + W) / 40) + 1; k++) text(ctx, YARDS[((k % 9) + 9) % 9], k * 40 - d - 3, 21, P['grass-d']);
      // end zone, pylons, goalpost every 300 px
      const rx = Math.floor(W * 0.62) - 10;
      let scoring = false;
      for (let k = Math.floor(d / 300) - 1; k <= Math.floor(d / 300) + 1; k++) {
        const gx = k * 300 + 260 - d; if (gx > W + 30 || gx < -40) continue;
        px(ctx, P['team-d'], gx, 12, 22, H - 12); px(ctx, P.line, gx, 12, 1, H - 12);
        px(ctx, P.team, gx, 12, 1, 2); px(ctx, P.team, gx, 29, 1, 2);
        const p = gx + 22;
        px(ctx, P.post, p, 12, 1, 17); px(ctx, P.post, p - 4, 11, 9, 1); px(ctx, P.post, p - 4, 1, 1, 10); px(ctx, P.post, p + 4, 1, 1, 10);
        if (rx + 10 >= gx && rx + 10 <= gx + 26) scoring = true;
      }
      // referee, defender, ball carrier; cycles offset so nobody steps in unison
      const dx = rx - 22 + Math.round(3 * Math.sin(n / 11)), fx = dx - 30 + Math.round(2 * Math.sin(n / 7));
      [fx, dx, rx].forEach(x => px(ctx, P['grass-d'], x + 4, 30, 11, 1));
      const base = { s: P.skin, t: P['skin-d'], m: P.mask, x: P.outline };
      drawSprite(ctx, SPR.ref[(f + 4) % 6], fx, 12, { ...base, H: P.outline, j: P.white, k: P.outline, p: P.navy, q: P['navy-d'] }, P.outline);
      drawSprite(ctx, SPR.tackler[(f + 3) % 6], dx, 12, { ...base, h: P.foe, g: P['foe-d'], j: P.white, k: P['white-d'], w: P.foe, p: P.white, q: P['white-d'] }, P.outline);
      drawSprite(ctx, SPR.carrier[f], rx, 12, { ...base, h: P.team, g: P['team-d'], j: P.navy, k: P['navy-d'], w: P.team, b: P.ball, p: P.white, q: P['white-d'] }, P.outline);
      if (scoring) {
        for (let i = 0; i < 14; i++) px(ctx, [P.team, P.foe, P.post, P.white][i % 4], rx + Math.floor(rnd(i * 7 + beat) * 30) - 6, 1 + Math.floor(rnd(i * 11 + beat) * 10));
        if (n % 4 < 3) text(ctx, 'TD!', rx + 6, 3, P.post);
      }
    },
  };

  // ---------------- This week ----------------
  const week = {
    ms: 140, stride: 3, still: 0,
    draw(ctx, W, n, P) {
      const d = n * this.stride, f = n % 6;
      px(ctx, P.sky, 0, 0, W, H);
      if (P.dark) {
        for (let i = 0; i < W / 4; i++) { const x = Math.floor(rnd(i * 13) * W), y = Math.floor(rnd(i * 29) * 12); if (rnd(i + Math.floor(n / 3) * 31) > 0.15) px(ctx, P.star, x, y); }
        const mx = W - 18; px(ctx, P.sun, mx + 1, 2, 4, 1); px(ctx, P.sun, mx, 3, 5, 3); px(ctx, P.sun, mx + 1, 6, 4, 1); px(ctx, P.sky, mx + 3, 3, 2, 2);
      } else {
        const sx = W - 18; px(ctx, P.sun, sx + 1, 2, 4, 6); px(ctx, P.sun, sx, 3, 6, 4);
        if (Math.floor(n / 3) % 2) { px(ctx, P.sun, sx + 2, 0, 2, 1); px(ctx, P.sun, sx + 2, 9, 2, 1); px(ctx, P.sun, sx - 2, 4, 1, 2); px(ctx, P.sun, sx + 7, 4, 1, 2); }
      }
      // the Rockies, far back, snow on the peaks (lit side left)
      const mo = Math.floor(d / 10);
      for (let x = 0; x < W; x++) {
        const wx = x + mo, k = Math.floor(wx / 34), u = wx - k * 34, peak = 9 + Math.floor(rnd(k + 5) * 6), hh = Math.max(0, peak - ((Math.abs(u - 17) * 0.8) | 0));
        if (hh > 0) { px(ctx, u < 17 ? P.mtn : P['mtn-d'], x, 25 - hh, 1, hh); if (hh > peak - 3) px(ctx, P.snow, x, 25 - hh, 1, Math.min(2, hh)); }
      }
      for (let k = 0; k < 4; k++) { const span = W + 40, cx = ((k * 67 - Math.floor(d / 8)) % span + span) % span - 20; tiles(ctx, CLOUD, cx, 3 + (k % 2) * 4, { C: P.cloud }); }
      for (let k = 0; k < 3; k++) { const span = W + 30, bx = ((k * 53 + Math.floor(n / 2) * (k + 1)) % span) - 10; tiles(ctx, BIRD[(n + k) % 2], bx, 6 + k * 3, { b: P.outline }); }
      for (let x = 0; x < W; x++) {
        const o1 = x + Math.floor(d / 4), h1 = 4 + Math.round(2 * Math.sin(o1 / 11) + 1.5 * Math.sin(o1 / 5));
        px(ctx, P.hill2, x, 27 - h1, 1, h1);
        const o2 = x + Math.floor(d / 2), h2 = 2 + Math.round(1.5 * Math.sin(o2 / 7));
        px(ctx, P.hill, x, 27 - h2, 1, h2);
      }
      const tOff = Math.floor(d * 3 / 4);
      for (let k = Math.floor(tOff / 41) - 1; k <= Math.floor((tOff + W) / 41) + 1; k++) if (rnd(k * 9 + 2) > 0.25) tiles(ctx, TREE, k * 41 + 9 - tOff, 20, { T: P.tree, D: P['tree-d'], R: P.trunk });
      // trail, wildflowers on the verge, mile markers
      px(ctx, P.ground, 0, 27, W, H - 27);
      for (let x = 0; x < W; x++) {
        const wx = x + d;
        if (wx % 9 === 0) px(ctx, P.ground2, x, 29);
        if (wx % 13 === 4) px(ctx, P.ground2, x, 31);
        const fl = rnd(wx * 3 + 1); if (fl > 0.86) px(ctx, fl > 0.93 ? P.bloom1 : P.bloom2, x, 26);
      }
      for (let k = Math.floor(d / 120); k <= Math.floor((d + W) / 120) + 1; k++) {
        const x = k * 120 - d + 30; if (x < -6 || x > W) continue;
        px(ctx, P.trunk, x + 2, 22, 1, 6); px(ctx, P.outline, x - 1, 15, 7, 8); px(ctx, P.white, x, 16, 5, 6); text(ctx, (k % 9) + 1, x + 1, 16, P.run);
      }
      // jogger and the dog
      const jx = Math.floor(W * 0.42) - 10, dogx = jx + 18 + Math.round(2 * Math.sin(n / 6));
      px(ctx, P.ground2, jx + 4, 29, 11, 1); px(ctx, P.ground2, dogx + 1, 29, 8, 1);
      drawSprite(ctx, SPR.jogger[f], jx, 12, { H: P.hair, s: P.skin, t: P['skin-d'], e: P.outline, j: P.run, k: P['run-d'], w: P.run, r: P.navy, p: P.skin, q: P['skin-d'], x: P.white }, P.outline);
      drawSprite(ctx, toGrid(DOG[n % 2]), dogx, 23, { d: P.dog, D: P['dog-d'], e: P.outline }, P.outline);
    },
  };

  const SCENES = { cfb, week };

  function mount(el) {
    const canvas = el.querySelector('canvas'), ctx = canvas.getContext('2d'), scene = SCENES[el.dataset.scene];
    let W = 96, P = palette(), clock = scene.still * scene.ms, prev = 0, raf = 0, last = -1, visible = true, paused = false;
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
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; sync(); }).observe(el);
    new MutationObserver(() => { P = palette(); draw(true); }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    document.addEventListener('visibilitychange', sync);
    reduce.addEventListener('change', () => { draw(true); sync(); });
    size(); sync();
  }
  addEventListener('DOMContentLoaded', () => document.querySelectorAll('.scene[data-scene]').forEach(mount));
})();
