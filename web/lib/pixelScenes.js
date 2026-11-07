// Pixel-art title scenes for ONS (DESIGN.md → Pixel Scenes), ported from the reference build
// docs/design/directions/6-logbook-color/px.js. Usage: components/ui/PixelScene.tsx.
// Data comes from the element's dataset: data-scene ("cfb" | "week" | "fitness" | "reading"), data-record (CFB
// scoreboard), data-wx ("sun"|"partly"|"cloudy"|"wind"|"rain"|"snow") and data-temp (This week), data-classes /
// data-miles / data-squat (Fitness), data-shelf / data-goal (Reading).
// Pixel-art title loops, built to the pixel-art-sprites skill (.claude/skills/pixel-art-sprites):
//  · Integer scaling in DEVICE pixels; image-rendering: pixelated.
//  · Characters on a 20×18 frame. 6-frame run cycle (patterns.md "run: 6"): contact → down → float, then
//    the same three mirrored. Legs have knees (hip → knee → foot), arms swing opposite the legs, the body
//    bobs 1px (low on "down", high on "float").
//  · Ground scrolls one foot-travel per frame (stride), so the support foot stays planted.
//  · One outline rule: every character gets a generated 1px outer outline; scenery gets none.
//  · Light from the top-left. Closed palette: only --px-* colours.
// ONS motion rules: stops offscreen / hidden tab, click pauses (remembered), reduced motion = still frame.
const H = 32, FW = 20, FH = 18, KEY = 'ons-px-paused';
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

// Birds (3×2)
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
  'ground', 'ground2', 'star', 'bloom1', 'bloom2', 'sky-o', 'cloud-o', 'rain', 'leaf',
  'blackdog', 'collar', 'tan', 'tan-d', 'muzzle', 'tabby', 'tabby-s', 'gray-c', 'gray-s', 'eye',
  'gym', 'mat', 'mat2', 'plate', 'plate-d', 'lift', 'lift-d', 'wall', 'wall-d', 'wood', 'wood-d', 'read', 'read-d', 'lamp', 'glow', 'rug'];
function palette() {
  const cs = getComputedStyle(document.documentElement), P = { dark: document.documentElement.dataset.theme === 'dark' };
  KEYS.forEach(k => P[k] = cs.getPropertyValue('--px-' + k).trim());
  return P;
}

// ---------------- Degenerates Corner ----------------
const YARDS = [10, 20, 30, 40, 50, 40, 30, 20, 10];
const cfb = {
  ms: 100, stride: 4, still: 2,
  draw(ctx, W, n, P, data) {
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
    const rec = String((data && data.record) || '').replace(/[^0-9-]/g, '').slice(0, 6);
    if (rec) { const bw = rec.length * 4 + 5; px(ctx, P.outline, 3, 0, bw + 2, 8); px(ctx, P.board, 4, 1, bw, 6); text(ctx, rec, 6, 2, P.post); }
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
// The pack: black dog, chihuahua-beagle, puggle run with the jogger; a brown tabby and a gray striped cat trot behind.
// 2-frame gaits (patterns.md: fewer frames, readable silhouettes). Facing right.
const PETS = {
  blackdog: [ // 12×6, red collar
    ['........KKK.', 'K......cKKKK', '.KKKKKKKKKn.', '.KKKKKKKKK..', '.K.K....K.K.', 'K...K..K...K'],
    ['........KKK.', '.K.....cKKKK', '.KKKKKKKKKn.', '.KKKKKKKKK..', '..KK....KK..', '..K.K..K.K..'],
  ],
  chibeagle: [ // 9×5, tri-colour, tall chihuahua ears, tiny
    ['......T.T', 'T.....TTT', '.BBBBBTTW', '.WWWWWW..', '.T.T..T.T'],
    ['......T.T', '.T....TTT', '.BBBBBTTW', '.WWWWWW..', '..TT.TT..'],
  ],
  puggle: [ // 10×6, stocky, dark pug muzzle, curly tail
    ['.......TTT', 'TT....TEMM', 'T.TTTTTTMM', '.TTTTTTTW.', '.T.T..T.T.', '..........'],
    ['.......TTT', '.TT...TEMM', '.TTTTTTTMM', '.TTTTTTTW.', '..TT..TT..', '..........'],
  ],
  cat: [ // 10×6, tail up, pointed ears, striped back
    ['.......C.C', 'C......CCC', '.C.....CCe', '..CSCSCSC.', '..CCCCCCC.', '..C.C..C.C'],
    ['.......C.C', '.C.....CCC', '..C....CCe', '..CSCSCSC.', '..CCCCCCC.', '...CC..CC.'],
  ],
};
const WEATHER = {
  sun: { sky: 'sky', clouds: 2, sun: true },
  partly: { sky: 'sky', clouds: 5, sun: true },
  cloudy: { sky: 'sky-o', clouds: 8, sun: false, overcast: true },
  wind: { sky: 'sky', clouds: 4, sun: true, wind: true },
  rain: { sky: 'sky-o', clouds: 8, sun: false, overcast: true, rain: true },
  snow: { sky: 'sky-o', clouds: 8, sun: false, overcast: true, snow: true },
};
const week = {
  ms: 140, stride: 3, still: 0,
  draw(ctx, W, n, P, data) {
    const wx = WEATHER[data.wx] || WEATHER.sun, d = n * this.stride, f = n % 6;
    const cloudSpeed = wx.wind ? 2 : 8;
    px(ctx, P[wx.sky], 0, 0, W, H);
    // sky body: sun or moon, stars only when the sky is clear-ish at night
    if (P.dark) {
      if (!wx.overcast) for (let i = 0; i < W / 4; i++) { const x = Math.floor(rnd(i * 13) * W), y = Math.floor(rnd(i * 29) * 12); if (rnd(i + Math.floor(n / 3) * 31) > 0.15) px(ctx, P.star, x, y); }
      if (wx.sun) { const mx = W - 18; px(ctx, P.sun, mx + 1, 2, 4, 1); px(ctx, P.sun, mx, 3, 5, 3); px(ctx, P.sun, mx + 1, 6, 4, 1); px(ctx, P[wx.sky], mx + 3, 3, 2, 2); }
    } else if (wx.sun) {
      const sx = W - 18; px(ctx, P.sun, sx + 1, 2, 4, 6); px(ctx, P.sun, sx, 3, 6, 4);
      if (Math.floor(n / 3) % 2) { px(ctx, P.sun, sx + 2, 0, 2, 1); px(ctx, P.sun, sx + 2, 9, 2, 1); px(ctx, P.sun, sx - 2, 4, 1, 2); px(ctx, P.sun, sx + 7, 4, 1, 2); }
    }
    // the Rockies (snowier when it's snowing)
    const mo = Math.floor(d / 10);
    for (let x = 0; x < W; x++) {
      const wxp = x + mo, k = Math.floor(wxp / 34), u = wxp - k * 34, peak = 9 + Math.floor(rnd(k + 5) * 6), hh = Math.max(0, peak - ((Math.abs(u - 17) * 0.8) | 0));
      if (hh > 0) { px(ctx, u < 17 ? P.mtn : P['mtn-d'], x, 25 - hh, 1, hh); const cap = wx.snow ? 5 : 3; if (hh > peak - cap) px(ctx, P.snow, x, 25 - hh, 1, Math.min(cap - 1, hh)); }
    }
    // clouds: count and speed follow the weather; overcast adds a low ceiling
    if (wx.overcast) px(ctx, P['cloud-o'], 0, 0, W, 3);
    for (let k = 0; k < wx.clouds; k++) {
      const span = W + 40, cx = ((k * 41 + Math.floor(rnd(k) * 30) - Math.floor(d / cloudSpeed)) % span + span) % span - 20;
      tiles(ctx, CLOUD, cx, 2 + (k % 3) * 3, { C: wx.overcast ? P['cloud-o'] : P.cloud });
    }
    if (!wx.rain && !wx.snow) for (let k = 0; k < 3; k++) { const span = W + 30, bx = ((k * 53 + Math.floor(n / 2) * (k + 1)) % span) - 10; tiles(ctx, BIRD[(n + k) % 2], bx, 7 + k * 3, { b: P.outline }); }
    for (let x = 0; x < W; x++) {
      const o1 = x + Math.floor(d / 4), h1 = 4 + Math.round(2 * Math.sin(o1 / 11) + 1.5 * Math.sin(o1 / 5));
      px(ctx, P.hill2, x, 27 - h1, 1, h1); if (wx.snow) px(ctx, P.snow, x, 27 - h1, 1, 1);
      const o2 = x + Math.floor(d / 2), h2 = 2 + Math.round(1.5 * Math.sin(o2 / 7));
      px(ctx, P.hill, x, 27 - h2, 1, h2); if (wx.snow) px(ctx, P.snow, x, 27 - h2, 1, 1);
    }
    const tOff = Math.floor(d * 3 / 4), lean = wx.wind && n % 4 < 2 ? 1 : 0;
    for (let k = Math.floor(tOff / 41) - 1; k <= Math.floor((tOff + W) / 41) + 1; k++) if (rnd(k * 9 + 2) > 0.25) {
      const tx = k * 41 + 9 - tOff;
      tiles(ctx, TREE.slice(0, 5), tx + lean, 20, { T: P.tree, D: P['tree-d'] }); tiles(ctx, TREE.slice(5), tx, 25, { R: P.trunk });
      if (wx.snow) px(ctx, P.snow, tx + 2 + lean, 20, 3, 1), px(ctx, P.snow, tx + 1 + lean, 21, 1, 1);
    }
    // trail: snow cover, puddles, wildflowers (not under snow), mile markers
    px(ctx, P.ground, 0, 27, W, H - 27);
    for (let x = 0; x < W; x++) {
      const wxp = x + d;
      if (wxp % 9 === 0) px(ctx, P.ground2, x, 29);
      if (wxp % 13 === 4) px(ctx, P.ground2, x, 31);
      if (wx.snow) { px(ctx, P.snow, x, 27); if (rnd(wxp) > 0.55) px(ctx, P.snow, x, 28); if (rnd(wxp * 5) > 0.8) px(ctx, P.snow, x, 30); }
      else { const fl = rnd(wxp * 3 + 1); if (fl > 0.86) px(ctx, fl > 0.93 ? P.bloom1 : P.bloom2, x, 26); }
      if (wx.rain && (wxp % 47) < 6) px(ctx, P.rain, x, 30);
    }
    for (let k = Math.floor(d / 120); k <= Math.floor((d + W) / 120) + 1; k++) {
      const x = k * 120 - d + 30; if (x < -6 || x > W) continue;
      px(ctx, P.trunk, x + 2, 22, 1, 6); px(ctx, P.outline, x - 1, 15, 7, 8); px(ctx, P.white, x, 16, 5, 6); text(ctx, (k % 9) + 1, x + 1, 16, P.run);
      if (wx.snow) px(ctx, P.snow, x - 1, 14, 7, 1);
    }
    // the pack. Jogger at 40% of the width; dogs around, cats trailing.
    const jx = Math.round(W * 0.46) - 10, gap = Math.round(W * 0.1), wob = k => Math.round(2 * Math.sin(n / 6 + k));
    const pets = [
      ['cat', jx - 3 * gap + wob(4), 23, { C: P['gray-c'], S: P['gray-s'], e: P.eye }],
      ['cat', jx - 2 * gap - 1 + wob(3), 23, { C: P.tabby, S: P['tabby-s'], e: P.eye }],
      ['chibeagle', jx - gap + 2 + wob(2), 24, { T: P.tan, B: P.blackdog, W: P.white }],
      ['blackdog', jx + 18 + wob(0), 23, { K: P.blackdog, c: P.collar, n: P.outline }],
      ['puggle', jx + 34 + wob(1), 23, { T: P.tan, E: P['tan-d'], M: P.muzzle, W: P.white }],
    ];
    pets.forEach(([k, x, y], i) => px(ctx, P.ground2, x + 1, 29, PETS[k][0][0].length - 1, 1));
    px(ctx, P.ground2, jx + 4, 29, 11, 1);
    pets.slice(0, 3).forEach(([k, x, y, m], i) => drawSprite(ctx, toGrid(PETS[k][(n + i) % 2]), x, y, m, P.outline));
    drawSprite(ctx, SPR.jogger[f], jx, 12, { H: P.hair, s: P.skin, t: P['skin-d'], e: P.outline, j: P.run, k: P['run-d'], w: P.run, r: P.navy, p: P.skin, q: P['skin-d'], x: P.white }, P.outline);
    pets.slice(3).forEach(([k, x, y, m], i) => drawSprite(ctx, toGrid(PETS[k][(n + i) % 2]), x, y, m, P.outline));
    // precipitation and wind on top of everything
    if (wx.snow) for (let i = 0; i < W * 0.35; i++) { const x = Math.floor(rnd(i * 3) * W + n * (0.5 + rnd(i) * 0.6) + Math.sin(n / 4 + i) * 1.5) % W, y = Math.floor(rnd(i * 7) * H + n * (0.6 + rnd(i * 5) * 0.5)) % H; px(ctx, P.snow, x, y); }
    if (wx.rain) for (let i = 0; i < W * 0.3; i++) { const x = Math.floor(rnd(i * 3) * W - n * 1) % W, y = Math.floor(rnd(i * 7) * H + n * 3) % H; px(ctx, P.rain, (x + W) % W, y, 1, 2); }
    if (wx.wind) for (let i = 0; i < 7; i++) { const x = Math.floor(rnd(i * 3) * W + n * (4 + i % 3)) % (W + 10) - 5, y = 8 + Math.floor(rnd(i * 7) * 18) + (n + i) % 3 - 1; px(ctx, i % 2 ? P.leaf : P['tree-d'], W - x, y); px(ctx, P[wx.sky] === P.sky ? P.cloud : P['cloud-o'], W - x + 2 + (i % 3), y - 4, 4, 1); }
    // temperature, top left, straight on the sky
    const t = String(data.temp || '');
    if (t) { const c = P.dark ? P.white : P.outline; text(ctx, t, 3, 3, c); const gx = 3 + t.length * 4; px(ctx, c, gx, 3, 3, 1); px(ctx, c, gx, 4); px(ctx, c, gx + 2, 4); px(ctx, c, gx, 5, 3, 1); }
  },
};


// ---------------- Fitness ----------------
// A gym: the WOD whiteboard shows this year's class count; a lifter squats the heaviest back squat logged this
// year (plates per side add up to it); the jogger runs on a treadmill whose console shows the year's miles.
// The lifter is a front view, 30×18 because the bar runs past the 20-px body. Feet stay planted; the body drops
// through the squat and the knees track out. The squat is an action, not a cycle (patterns.md "attack"): a long
// hold at lockout, a controlled descent, a short hold at the bottom, a faster drive up, then chalk off the hands.
const LIFT_POSES = [
  { d: 0, knee: [[12, 14], [16, 14]] }, // lockout
  { d: 2, knee: [[10, 15], [18, 15]] }, // half
  { d: 3, knee: [[9, 15], [19, 15]] },  // bottom, knees out
];
const SQUAT_TICKS = [0, 0, 0, 0, 0, 0, 1, 1, 2, 2, 2, 1, 0, 0, 0, 0]; // 120 ms ticks; chalk on ticks 12–13
const PLATE_H = { 45: 4, 35: 4, 25: 3, 10: 2, 5: 1 };                 // half-heights in art pixels
function platesFor(load) {
  let side = Math.max(0, (Number(load) || 135) - 45) / 2; const out = [];
  for (const p of [45, 35, 25, 10, 5]) while (side >= p && out.length < 4) { out.push(p); side -= p; }
  return out.length ? out : [45];
}
function buildLifter(p, plates) {
  const W2 = 30, g = Array.from({ length: FH }, () => Array(W2).fill('.'));
  const set = (x, y, c) => { if (y >= 0 && y < FH && x >= 0 && x < W2) g[y][x] = c; };
  const top = 1 + p.d, barY = top + 4, hip = 12 + p.d;
  // bar, collars and plates sit behind the body
  for (let x = 1; x <= 28; x++) set(x, barY, 'b');
  set(8, barY, 'c'); set(21, barY, 'c');
  let xl = 7, xr = 22;
  plates.forEach(w => {
    const h = PLATE_H[w];
    for (let y = barY - h; y <= barY + h; y++) { set(xl - 1, y, 'P'); set(xl, y, 'Q'); set(xr, y, 'P'); set(xr + 1, y, 'Q'); }
    xl -= 2; xr += 2;
  });
  // head (front view) and neck
  ['HHHH', 'eSSe', 'SSSS', 'tSSt'].forEach((r, y) => [...r].forEach((c, x) => set(13 + x, top + y, c)));
  set(14, barY, 's'); set(15, barY, 's');
  // shoulders, torso (shade on the right: light from the top-left), shorts
  for (let x = 11; x <= 18; x++) set(x, barY + 1, x === 18 ? 'k' : 'j');
  for (let y = barY + 2; y <= hip - 3; y++) for (let x = 12; x <= 17; x++) set(x, y, x === 17 ? 'k' : 'j');
  for (let y = hip - 2; y <= hip; y++) for (let x = 12; x <= 17; x++) set(x, y, 'r');
  // arms: hands on the bar outside the shoulders, elbows under it
  [10, 19].forEach(x => { set(x, barY, 's'); set(x, barY + 1, 's'); set(x, barY + 2, 'k'); });
  // legs: hip → knee → planted ankle, 2 px wide; shoes don't move
  const leg = (hx, K, ax) => {
    line(hx, hip, K[0], K[1], (x, y) => { set(x, y, 'p'); set(x + 1, y, 'p'); });
    line(K[0], K[1], ax, 16, (x, y) => { set(x, y, 'p'); set(x + 1, y, 'p'); });
  };
  leg(12, p.knee[0], 12); leg(16, p.knee[1], 16);
  [11, 12, 13, 16, 17, 18].forEach(x => set(x, 17, 'x'));
  return g;
}
const fitness = {
  ms: 120, stride: 3, still: 0,
  draw(ctx, W, n, P, data) {
    // wall with a CrossFit-amber band, baseboard, rubber floor with tile seams
    px(ctx, P.gym, 0, 0, W, 28);
    px(ctx, P.lift, 0, 19, W, 2);
    px(ctx, P.mat2, 0, 27, W, 1);
    px(ctx, P.mat, 0, 28, W, H - 28);
    for (let x = 7; x < W; x += 16) px(ctx, P.mat2, x, 28, 1, H - 28);
    // whiteboard: the year's class count and two lines of marker
    const bx = 4, classes = String(data.classes || '').replace(/\D/g, '').slice(0, 3);
    px(ctx, P['white-d'], bx, 3, 26, 15); px(ctx, P.white, bx + 1, 4, 24, 13); px(ctx, P['white-d'], bx + 2, 17, 22, 1);
    if (classes) text(ctx, classes, bx + 3, 6, P.navy);
    px(ctx, P.navy, bx + 3, 13, 9, 1); px(ctx, P.collar, bx + 14, 13, 6, 1); px(ctx, P.run, bx + 3, 15, 13, 1);
    // kettlebells by the wall
    [[bx + 2, P['navy-d']], [bx + 8, P['plate-d']], [bx + 13, P['navy-d']]].forEach(([x, c]) => { px(ctx, c, x, 25, 4, 3); px(ctx, c, x + 1, 23, 2, 1); px(ctx, c, x, 24); px(ctx, c, x + 3, 24); });
    // squat rack and platform, lifter in front
    const lx = Math.max(bx + 30, Math.round(W * 0.43) - 15), ly = 11;
    px(ctx, P.wood, lx - 2, 28, 34, 2); px(ctx, P['wood-d'], lx - 2, 30, 34, 1);
    [lx - 1, lx + 30].forEach(x => { px(ctx, P['white-d'], x, 4, 1, 24); px(ctx, P.mask, x, 4, 1, 1); });
    px(ctx, P.mask, lx - 1, 14, 2, 1); px(ctx, P.mask, lx + 29, 14, 2, 1); // J-hooks
    const t = n % SQUAT_TICKS.length, pose = LIFT_POSES[SQUAT_TICKS[t]];
    drawSprite(ctx, buildLifter(pose, platesFor(data.squat)), lx, ly, { H: P.hair, S: P.skin, s: P.skin, t: P['skin-d'], e: P.outline, j: P.lift, k: P['lift-d'], r: P.navy, p: P.skin, x: P.white, b: P['white-d'], c: P.mask, P: P.plate, Q: P['plate-d'] }, P.outline);
    if (t === 12 || t === 13) { const up = t - 12; [[lx + 9, 13], [lx + 11, 12], [lx + 20, 13], [lx + 18, 12], [lx + 10, 11], [lx + 19, 11]].forEach(([x, y], i) => { if (i < 4 || up) px(ctx, P.white, x, y - up); }); }
    // treadmill: the belt moves one foot-travel per frame, so the support foot stays planted on it
    const tx = Math.max(lx + 36, Math.min(W - 50, Math.round(W * 0.72) - 16)), d = n * this.stride, DL = 34;
    px(ctx, P.outline, tx, 27, DL, 1); px(ctx, P.mat2, tx, 28, DL, 2); px(ctx, P.outline, tx + 1, 30, 2, 1); px(ctx, P.outline, tx + DL - 3, 30, 2, 1);
    for (let x = 0; x < DL; x++) if ((x + d) % 8 === 0) px(ctx, P['white-d'], tx + x, 27);
    // upright at the front of the deck, handrail at hand height, console out in front of the runner
    const miles = String(data.miles || '').replace(/\D/g, '').slice(0, 4), cw = Math.max(3, miles.length) * 4 + 3, ux = tx + DL - 2;
    px(ctx, P['white-d'], ux, 14, 1, 13); px(ctx, P['white-d'], tx + 20, 16, ux - tx - 20, 1);
    px(ctx, P.outline, ux - 2, 6, cw + 2, 8); px(ctx, P.board, ux - 1, 7, cw, 6);
    if (miles) text(ctx, miles, ux + 1, 8, P.post);
    drawSprite(ctx, SPR.jogger[n % 6], tx + 6, 9, { H: P.hair, s: P.skin, t: P['skin-d'], e: P.outline, j: P.run, k: P['run-d'], w: P.run, r: P.navy, p: P.skin, q: P['skin-d'], x: P.white }, P.outline);
  },
};

// ---------------- Reading ----------------
// A reading room. The top shelf holds one slot per book in the year's goal, filled with the books finished so
// far (fiction teal, nonfiction navy, unclassified grey). The reader turns a page every few seconds; the brown
// tabby lies on the chair back flicking its tail; the gray cat sleeps on the rug. 2-frame loops for the props.
const READER = [
  '....................',
  '.......HHHH.........',
  '......HHHHHs........',
  '......HHHHse........',
  '......HHHsss........',
  '.......Htss.........',
  '......jjjjj.........',
  '.....jjjjjjjss......',
  '.....jjjjk...sBWWB..',
  '.....jjjjk....BBBB..',
  '.....jjjjk..........',
  '.....rrrrrrrrrr.....',
  '.....rrrrrrrrrrr....',
  '..............pp....',
  '..............pp....',
  '..............pp....',
  '..............xxxx..',
  '....................',
];
const LOAF = [ // brown tabby lying on the chair back, 10×6; frame 2 flicks the tail up
  ['.......C.C', '.......CCC', '..SCSCSCCe', '.CCCCCCCC.', 'T.........', 'T.........'],
  ['.......C.C', '.......CCC', '..SCSCSCCe', 'TCCCCCCCC.', '.T........', '..........'],
];
const CURL = [ // gray cat asleep, 8×4; breathing
  ['...C.C..', '..CCCCS.', '.SCSCCCC', 'CCCCCCCC'],
  ['........', '..CCCCS.', '.SCSCCCC', 'CCCCCCCC'],
];
const reading = {
  ms: 160, stride: 0, still: 0,
  draw(ctx, W, n, P, data) {
    const t = n % 48;
    px(ctx, P.wall, 0, 0, W, 24);
    px(ctx, P['wall-d'], 0, 19, W, 5);
    // lamp glow on the wall, behind everything else
    const ox = Math.round(W * 0.46) - 6, tx = ox + 24, lampX = Math.max(tx + 14, Math.round(W * 0.84));
    // a soft halo around the shade: solid inside, checker-dithered at the rim (no smoothing, no new colour)
    for (let y = 0; y < 19; y++) for (let x = lampX - 12; x <= lampX + 12; x++) {
      const r = ((x - lampX) / 12) ** 2 + ((y - 5) / 9) ** 2;
      if (r < 0.55 || (r < 1 && (x + y) % 2 === 0)) px(ctx, P.glow, x, y);
    }
    // floor: planks and a rug
    px(ctx, P.wood, 0, 24, W, H - 24);
    for (const y of [27, 30]) px(ctx, P['wood-d'], 0, y, W, 1);
    for (let x = 0; x < W; x += 9) { px(ctx, P['wood-d'], x, 25 + (x % 2 ? 0 : 3), 1, 2); }
    px(ctx, P.rug, ox - 18, 25, 48, 4); px(ctx, P['plate-d'], ox - 18, 28, 48, 1);
    // bookshelf; the top shelf is this year's goal
    const sx = 4, shelf = String(data.shelf || ''), goal = Math.min(11, Math.max(shelf.length, Number(data.goal) || 0));
    px(ctx, P['wall-d'], sx, 2, 26, 22); px(ctx, P['wood-d'], sx, 2, 1, 22); px(ctx, P['wood-d'], sx + 25, 2, 1, 22);
    for (const y of [2, 9, 16, 23]) px(ctx, P.wood, sx, y, 26, 1);
    const SPINE = { f: [P.read, P['read-d']], n: [P.navy, P['navy-d']], u: [P['white-d'], P.mask] };
    for (let i = 0; i < goal; i++) {
      const x = sx + 2 + i * 2;
      if (i < shelf.length) { const [a, b] = SPINE[shelf[i]] || SPINE.u, h = 4 + Math.floor(rnd(i + 3) * 3); px(ctx, a, x, 9 - h, 1, h); px(ctx, b, x + 1, 9 - h, 1, h); }
      else px(ctx, P.wood, x, 8, 2, 1); // an empty slot: a mark on the shelf where the book goes
    }
    const DECOR = [P['team-d'], P.navy, P.tree, P.plate, P['lift-d'], P.hair, P['white-d'], P['read-d']];
    for (const y of [16, 23]) for (let x = sx + 2, k = y; x < sx + 24; k++) {
      const w = rnd(k * 7) > 0.7 ? 2 : 1, h = 4 + Math.floor(rnd(k * 3) * 3);
      if (rnd(k * 11) > 0.9) { x++; continue; }
      px(ctx, DECOR[Math.floor(rnd(k * 5) * DECOR.length)], x, y - h, Math.min(w, sx + 24 - x), h); x += w;
    }
    // window between the shelf and the chair: sky by day, stars at night
    const wx = Math.round((sx + 26 + ox - 6) / 2) - 10;
    if (ox - (sx + 26) > 30) {
      px(ctx, P.wood, wx - 1, 3, 22, 15); px(ctx, P.sky, wx, 4, 20, 12);
      if (P.dark) for (let i = 0; i < 6; i++) { if (rnd(i + Math.floor(n / 4) * 7) > 0.2) px(ctx, P.star, wx + 1 + Math.floor(rnd(i * 13) * 18), 5 + Math.floor(rnd(i * 29) * 9)); }
      else tiles(ctx, CLOUD, wx + 2 + (Math.floor(n / 12) % 12), 6, { C: P.cloud });
      px(ctx, P.wood, wx + 10, 4, 1, 12); px(ctx, P.wood, wx, 10, 20, 1); px(ctx, P['wood-d'], wx - 2, 17, 24, 1);
    }
    // the gray cat asleep on the rug
    drawSprite(ctx, toGrid(CURL[Math.floor(n / 6) % 2]), ox - 14, 23, { C: P['gray-c'], S: P['gray-s'] }, P.outline);
    // armchair back and seat, then the reader, then the near armrest
    const oy = 7;
    px(ctx, P.read, ox, oy + 3, 6, 14); px(ctx, P.read, ox + 1, oy + 2, 4, 1); px(ctx, P['read-d'], ox + 5, oy + 3, 1, 14);
    px(ctx, P.read, ox + 4, oy + 13, 13, 2); px(ctx, P['read-d'], ox + 4, oy + 15, 13, 1);
    px(ctx, P['wood-d'], ox + 1, oy + 16, 1, 2); px(ctx, P['wood-d'], ox + 15, oy + 16, 1, 2);
    const g = toGrid(READER);
    if (t === 44) { g[7][16] = 'W'; g[6][16] = 'W'; }          // a page lifts
    if (t === 45) { g[7][15] = 'W'; g[6][14] = 'W'; g[5][14] = 'W'; } // and turns toward the reader
    if (t === 30) g[3][10] = 's';                               // a blink
    drawSprite(ctx, g, ox, oy, { H: P.hair, s: P.skin, t: P['skin-d'], e: P.outline, j: P['team-d'], k: P['team-d'], r: P.navy, p: P.navy, x: P['white-d'], B: P['lift-d'], W: P.white }, P.outline);
    // the near armrest, in front of the reader's lap
    px(ctx, P.read, ox + 3, oy + 9, 11, 3); px(ctx, P['read-d'], ox + 3, oy + 12, 11, 1); px(ctx, P['read-d'], ox + 13, oy + 9, 1, 3);
    // the brown tabby on the chair back
    drawSprite(ctx, toGrid(LOAF[Math.floor(n / 5) % 3 === 2 ? 1 : 0]), ox - 1, oy - 2, { C: P.tabby, S: P['tabby-s'], e: P.eye, T: P.tabby }, P.outline);
    // side table with a mug; steam alternates
    px(ctx, P.wood, tx, 16, 9, 1); px(ctx, P['wood-d'], tx, 17, 9, 1); px(ctx, P['wood-d'], tx + 1, 18, 1, 6); px(ctx, P['wood-d'], tx + 7, 18, 1, 6);
    px(ctx, P.lift, tx + 3, 13, 3, 3); px(ctx, P['lift-d'], tx + 6, 14, 1, 1);
    const st = Math.floor(n / 3) % 2;
    px(ctx, P['white-d'], tx + 3 + st, 11); px(ctx, P['white-d'], tx + 4 - st, 10); px(ctx, P['white-d'], tx + 4 + st, 9);
    // floor lamp
    px(ctx, P['wood-d'], lampX, 7, 1, 17); px(ctx, P['wood-d'], lampX - 2, 23, 5, 1);
    px(ctx, P.lamp, lampX - 2, 3, 5, 1); px(ctx, P.lamp, lampX - 3, 4, 7, 3);
  },
};

// ---------------- Music ----------------
// A listening room. The poster on the wall carries the date of your artists' next Denver show; the amp's display
// shows the year's listening hours. The listener nods on the beat (2 frames); the record's highlight turns and
// the woofers pump (2-frame props); a note drifts up now and then.
const LISTENER = [
  '.......OOOO.........',
  '......OHHHHO........',
  '......HHHHHs........',
  '.....PHHHHse........',
  '.....PHHHsss........',
  '.......Htss.........',
  '......jjjjj.........',
  '.....jjjjjjj........',
  '.....jjjjkjjss......',
  '.....jjjjk..........',
  '.....jjjjk..........',
  '.....rrrrrrrrrr.....',
  '.....rrrrrrrrrrr....',
  '..............pp....',
  '..............pp....',
  '..............pp....',
  '..............xxxx..',
  '....................',
];
const NOTE = ['.11', '.1.', '11.', '11.'];
const music = {
  ms: 150, stride: 0, still: 0,
  draw(ctx, W, n, P, data) {
    px(ctx, P.wall, 0, 0, W, 26);
    px(ctx, P['wall-d'], 0, 22, W, 4);
    px(ctx, P.wood, 0, 26, W, H - 26); px(ctx, P['wood-d'], 0, 29, W, 1);
    // record shelf: sleeves standing in two cubbies
    const sx = 4;
    px(ctx, P['wood-d'], sx, 10, 26, 16); px(ctx, P['wall-d'], sx + 1, 11, 24, 6); px(ctx, P['wall-d'], sx + 1, 18, 24, 7);
    const SLEEVE = [P.plate, P.navy, P.lift, P.read, P['team-d'], P.white, P.foe, P['tree']];
    for (const [y0, h] of [[11, 6], [18, 7]]) for (let x = sx + 2, k = y0; x < sx + 24; x += 2, k++) {
      if (rnd(k * 13) > 0.85) continue;
      px(ctx, SLEEVE[Math.floor(rnd(k * 7) * SLEEVE.length)], x, y0 + (h - 5), 1, 5); px(ctx, P['wood-d'], x + 1, y0 + (h - 5), 1, 5);
    }
    // gig poster: the next show by one of your artists
    const pxp = sx + 32, poster = String(data.poster || '').replace(/[^0-9-]/g, '').slice(0, 5);
    px(ctx, P.foe, pxp, 3, 20, 15); px(ctx, P['foe-d'], pxp, 15, 20, 3);
    if (poster) text(ctx, poster, pxp + 2 + Math.floor((16 - poster.length * 4) / 2), 6, P.white);
    for (let x = 0; x < 16; x++) px(ctx, P.post, pxp + 2 + x, 12 + (x % 4 < 2 ? 0 : 1));
    // the listener in a chair, facing the turntable
    const cx = Math.max(pxp + 22, Math.round(W * 0.42) - 12), cy = 8;
    px(ctx, P.navy, cx, cy + 3, 6, 15); px(ctx, P.navy, cx + 1, cy + 2, 4, 1); px(ctx, P['navy-d'], cx + 5, cy + 3, 1, 15);
    px(ctx, P.navy, cx + 4, cy + 13, 13, 3); px(ctx, P['navy-d'], cx + 4, cy + 16, 13, 1);
    const nod = n % 4 < 2 ? 0 : 1;
    const g = toGrid(LISTENER);
    if (nod) { for (let y = 6; y > 0; y--) g[y] = g[y - 1].slice(); g[0] = [...'....................']; }
    drawSprite(ctx, g, cx, cy, { O: P.mask, P: P.plate, H: P.hair, s: P.skin, t: P['skin-d'], e: P.outline, j: P.lift, k: P['lift-d'], r: P['run-d'], p: P['run-d'], x: P.white }, P.outline);
    px(ctx, P.navy, cx + 3, cy + 10, 11, 3); px(ctx, P['navy-d'], cx + 13, cy + 10, 1, 3); // near armrest
    // speakers, cabinet with the amp display, turntable on top
    const tx = Math.max(cx + 30, Math.round(W * 0.7) - 15), pump = n % 2;
    [tx - 9, tx + 32].forEach(x => {
      px(ctx, P.mat, x, 12, 7, 14); px(ctx, P.mat2, x + 1, 13, 5, 3);
      px(ctx, P.mat2, x + 1 - pump, 18 - pump, 5 + pump * 2, 5 + pump * 2); px(ctx, P.mat, x + 3, 20, 1, 1);
    });
    px(ctx, P.wood, tx, 17, 30, 9); px(ctx, P['wood-d'], tx, 17, 30, 1); px(ctx, P['wood-d'], tx + 1, 26, 2, 1); px(ctx, P['wood-d'], tx + 27, 26, 2, 1);
    const hrs = String(data.hours || '').replace(/\D/g, '').slice(0, 4), dw = Math.max(3, hrs.length) * 4 + 3;
    px(ctx, P.outline, tx + 3, 19, dw + 2, 7); px(ctx, P.board, tx + 4, 20, dw, 5);
    if (hrs) text(ctx, hrs, tx + 6, 20, P.post);
    px(ctx, P.mask, tx + dw + 8, 21, 2, 2); px(ctx, P.mask, tx + dw + 12, 21, 2, 2); // knobs
    // turntable: plinth, record seen from above at a low angle, tonearm
    px(ctx, P['wood-d'], tx + 4, 14, 22, 3);
    const rx = tx + 6;
    px(ctx, P.board, rx + 2, 10, 12, 1); px(ctx, P.board, rx, 11, 16, 2); px(ctx, P.board, rx + 2, 13, 12, 1);
    px(ctx, P.plate, rx + 6, 11, 4, 2);
    const HI = [[rx + 3, 11], [rx + 7, 10], [rx + 12, 11], [rx + 8, 13]];
    const [hx, hy] = HI[Math.floor(n / 2) % 4]; px(ctx, P['white-d'], hx, hy, 2, 1);
    px(ctx, P['white-d'], tx + 23, 9, 1, 5); px(ctx, P['white-d'], tx + 18, 9, 5, 1); px(ctx, P.mask, tx + 17, 10, 1, 1);
    // a note drifts up from the record every few seconds
    const life = n % 24;
    if (life < 14) tiles(ctx, NOTE, rx + 4 - (life >> 2), 6 - (life >> 1), { 1: P.outline });
  },
};

// ---------------- King Gizzard ----------------
// An original character: a lizard in a wizard hat playing a flute on a small stage. The marquee shows how many
// shows the band has played. 2-frame loops: hat tip and tail flick, spotlights swap, the crowd bobs, notes rise.
const LIZARD = [
  '.........M........',
  '........MM........',
  '........MMm.......',
  '.......MyMm.......',
  '.......MMMmm......',
  '......MMMMMmm.....',
  '....mmmmmmmmmmm...',
  '.......GGGGG......',
  '.......GGGeGGG....',
  '.......GGGGGGGG...',
  '........GGGgGfFfff',
  '.......GGGGGGG....',
  '......GGbbbGGG....',
  '......GGbbbGG.....',
  '......GGbbbGG.....',
  '......GGbbbGG.....',
  '......GGGGGGG.....',
  '......GGg.GGg.....',
  '......GG...GG.....',
  '......GGG..GGG....',
];
const TAIL = [[[5, 14], [4, 15], [3, 16], [2, 17], [2, 18], [3, 19]], [[5, 14], [4, 15], [3, 15], [2, 14], [1, 13], [1, 12]]];
const kglw = {
  ms: 180, stride: 0, still: 0,
  draw(ctx, W, n, P, data) {
    const f = n % 2, beat = Math.floor(n / 2);
    // curtain with folds
    px(ctx, P.stand, 0, 0, W, 24);
    for (let x = 3; x < W; x += 6) px(ctx, P['navy-d'], x, 0, 1, 24);
    // marquee: shows played, bulbs chase
    const shows = String(data.shows || '').replace(/\D/g, '').slice(0, 4), mw = Math.max(3, shows.length) * 4 + 7;
    px(ctx, P.outline, 4, 2, mw + 2, 11); px(ctx, P.board, 5, 3, mw, 9);
    for (let x = 5; x < 5 + mw; x += 2) { px(ctx, (x + beat) % 4 < 2 ? P.post : P['lift-d'], x, 3); px(ctx, (x + beat) % 4 < 2 ? P['lift-d'] : P.post, x, 11); }
    if (shows) text(ctx, shows, 8, 5, P.post);
    // lamp bar: lamps alternate on the beat
    const lx = Math.max(mw + 30, Math.round(W * 0.45) - 9);
    px(ctx, P.outline, 0, 0, W, 2);
    for (let x = 6, k = 0; x < W; x += 12, k++) { const on = (k + beat) % 2 === 0; px(ctx, on ? P.post : P.mask, x, 2, 3, 1); if (on) for (let y = 3; y < 7; y++) if ((x + y) % 2 === 0) px(ctx, P.post, x + 1, y); }
    // stage, a pool of light under the player, amp stacks, a drum kit
    px(ctx, P.wood, 0, 24, W, 3); px(ctx, P['wood-d'], 0, 27, W, 1);
    for (let x = lx - 2; x <= lx + 20; x++) for (let y = 24; y <= 26; y++) if ((x + y) % 2 === 0 && Math.abs(x - lx - 9) < 12 - (y - 24) * 2) px(ctx, P.sun, x, y);
    [lx - 16, lx + 24].forEach(x => { px(ctx, P.mat, x, 12, 9, 12); px(ctx, P.mat2, x + 1, 13, 7, 1); px(ctx, P.mat2, x + 2, 16, 5, 5); px(ctx, P.mat, x + 4, 18, 1, 1); });
    const dx = lx + 38;
    if (dx + 18 < W) {
      px(ctx, P.white, dx + 4, 17, 9, 7); px(ctx, P.plate, dx + 4, 19, 9, 1); px(ctx, P['white-d'], dx + 12, 17, 1, 7); // bass drum
      px(ctx, P.mask, dx, 18, 4, 2); px(ctx, P.mask, dx + 14, 17, 4, 2); px(ctx, P['white-d'], dx + 1, 20, 1, 4); px(ctx, P['white-d'], dx + 15, 19, 1, 5); // toms on stands
      const hit = f ? 1 : 0; px(ctx, P.post, dx - 2, 13 + hit, 6, 1); px(ctx, P['white-d'], dx + 1, 14 + hit, 1, 10); // cymbal shakes
    }
    // the lizard
    const g = toGrid(LIZARD);
    if (f) { g[0][9] = '.'; g[0][10] = 'M'; }
    TAIL[f].forEach(([x, y]) => { g[y][x] = 'g'; });
    drawSprite(ctx, g, lx, 4, { M: P.foe, m: P['foe-d'], y: P.post, G: P.grass, g: P['grass-d'], b: P.hill2, e: P.outline, f: P['white-d'], F: P.mask }, P.outline);
    // notes rising from the flute
    for (let i = 0; i < 2; i++) { const life = (n + i * 9) % 18; if (life < 12) tiles(ctx, NOTE, lx + 19 + (life >> 2), 13 - life, { 1: P.white }); }
    // the pit and the crowd, lit from the stage, bobbing on the beat
    px(ctx, P.board, 0, 28, W, H - 28);
    for (let x = 1; x < W; x += 3) {
      const i = x * 7, h = rnd(i), up = rnd(i + beat * 13) < 0.3 ? 1 : 0, c = h < 0.5 ? P.mask : P.navy;
      px(ctx, c, x, 29 - up, 2, 3 + up);
      if (rnd(i + beat * 29) < 0.08) px(ctx, c, x + (h < 0.25 ? -1 : 2), 26 - up, 1, 3);
    }
  },
};

// ---------------- Sports ----------------
// A rink. A skater carries the puck in and scores; the goal light flashes. The scoreboard shows the score of
// your most relevant game today (live, then final, then the next one at 0-0). Skating glides, so the ice may
// move under the skates; the stride is a 2-frame push.
const SKATER = [
  ['.........NNN........', '........NNNNs.......', '........NNNse.......', '.......jjjjss.......', '......jjjjjjj.......', '.....jjjwjjjjss.....', '.....jjjjjjj..sS....', '......jjjjjj....S...', '......rrrrrr.....S..', '......rr..rr......S.', '.....rr....rr.....SS', '....kk......kk......', '....xxxx....xxxx....'],
  ['.........NNN........', '........NNNNs.......', '........NNNse.......', '.......jjjjss.......', '......jjjjjjj.......', '.....jjjwjjjjss.....', '.....jjjjjjj..sS....', '......jjjjjj....S...', '......rrrrrr.....S..', '.......rrrr.......S.', '.......rrrr.......SS', '......kk.kk.........', '.....xxxxxxxx.......'],
];
const sports = {
  ms: 120, stride: 3, still: 0,
  draw(ctx, W, n, P, data) {
    const d = n * this.stride, f = Math.floor(n / 2) % 2;
    // stands, scoreboard, boards with ad panels, ice with blue and red lines
    px(ctx, P.stand, 0, 0, W, 12);
    const crowd = [P.plate, P.navy, P.white, P['white-d']], off = Math.floor(d / 6), beat = Math.floor(n / 3);
    for (let x = 1; x < W; x += 2) for (let y = 1; y < 11; y += 2) { const i = (x + off) * 7 + y * 131, h = rnd(i); if (h < 0.35) continue; px(ctx, crowd[Math.floor(h * 97) % 4], x, y - (rnd(i + beat * 17) < 0.08 ? 1 : 0)); }
    const sb = String(data.board || '').replace(/[^0-9-]/g, '').slice(0, 7);
    if (sb) { const bw = sb.length * 4 + 5, bx = Math.round(W / 2 - bw / 2); px(ctx, P.outline, bx - 1, 0, bw + 2, 9); px(ctx, P.board, bx, 1, bw, 7); text(ctx, sb, bx + 3, 2, P.collar); }
    px(ctx, P.white, 0, 12, W, 4);
    for (let k = Math.floor(d / 40) - 1; k <= Math.floor((d + W) / 40) + 1; k++) { const x = k * 40 - d; px(ctx, [P.run, P.plate, P.lift][((k % 3) + 3) % 3], x + 4, 13, 20, 2); }
    px(ctx, P.mask, 0, 16, W, 1);
    px(ctx, P.white, 0, 17, W, H - 17);
    for (let x = 0; x < W; x++) { const wx = x + d; if (wx % 120 === 0) px(ctx, P.run, x, 17, 2, H - 17); if (wx % 120 === 60) px(ctx, P.plate, x, 17, 1, H - 17); if ((wx * 7) % 23 === 0) px(ctx, P['white-d'], x, 20 + (wx % 9)); }
    // a net every 260 px; when the skater reaches it the puck goes in and the light flashes
    const sx = Math.floor(W * 0.38) - 10;
    let goal = false;
    for (let k = Math.floor(d / 260) - 1; k <= Math.floor(d / 260) + 1; k++) {
      const gx = k * 260 + 230 - d; if (gx > W + 20 || gx < -30) continue;
      px(ctx, P.plate, gx - 6, 17, 1, H - 17); // goal line
      px(ctx, P.plate, gx, 20, 1, 10); px(ctx, P.plate, gx, 20, 9, 1); px(ctx, P.plate, gx + 8, 20, 1, 10);
      for (let y = 21; y < 30; y += 2) for (let x = gx + 1; x < gx + 8; x += 2) px(ctx, P['white-d'], x, y);
      if (sx + 22 >= gx - 2 && sx + 22 <= gx + 14) goal = true;
      if (goal) { px(ctx, n % 2 ? P.collar : P.plate, gx + 3, 16, 3, 2); }
    }
    // skater with stick and puck
    const g = toGrid(SKATER[f]);
    px(ctx, P['white-d'], sx + 5, 30, 12, 1); // shadow on the ice
    drawSprite(ctx, g, sx, 18, { N: P.navy, s: P.skin, e: P.outline, j: P.plate, w: P.white, r: P.navy, k: P.navy, x: P['white-d'], S: P.wood }, P.outline);
    if (!goal) px(ctx, P.outline, sx + 21, 29, 2, 1);
    else { px(ctx, P.outline, Math.min(W - 1, sx + 26), 26, 2, 1); if (n % 4 < 3) text(ctx, '!', sx + 8, 12, P.collar); }
  },
};

const SCENES = { cfb, week, fitness, reading, music, kglw, sports };

function mount(el) {
  if (!el.querySelector('canvas')) return () => {};
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const canvas = el.querySelector('canvas'), ctx = canvas.getContext('2d'), scene = SCENES[el.dataset.scene];
  let dead = false, W = 96, P = palette(), clock = scene.still * scene.ms, prev = 0, raf = 0, last = -1, visible = true, paused = false;
  try { paused = localStorage.getItem(KEY) === '1'; } catch (e) {}
  const draw = force => { const n = Math.floor(clock / scene.ms); if (!force && n === last) return; last = n; ctx.clearRect(0, 0, W, H); scene.draw(ctx, W, n, P, el.dataset); };
  const running = () => !paused && visible && !reduce.matches && !document.hidden;
  const loop = now => { clock += Math.max(0, Math.min(100, now - prev)); prev = now; draw(false); raf = running() && !dead ? requestAnimationFrame(loop) : 0; };
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
  const onClick = () => { paused = !paused; try { localStorage.setItem(KEY, paused ? '1' : '0'); } catch (e) {} sync(); };
  const onReduce = () => { draw(true); sync(); };
  el.addEventListener('click', onClick);
  const ro = new ResizeObserver(size); ro.observe(el);
  const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; sync(); }); io.observe(el);
  const mo1 = new MutationObserver(() => { P = palette(); draw(true); }); mo1.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  // Redraw when the page passes new data (any data-* attribute); the engine's own aria/title changes don't count.
  const mo2 = new MutationObserver(rs => { if (rs.some(r => r.attributeName && r.attributeName.startsWith('data-') && r.attributeName !== 'data-scene')) draw(true); });
  mo2.observe(el, { attributes: true });
  document.addEventListener('visibilitychange', sync);
  reduce.addEventListener('change', onReduce);
  size(); sync();
  return () => {
    dead = true; if (raf) cancelAnimationFrame(raf);
    el.removeEventListener('click', onClick); ro.disconnect(); io.disconnect(); mo1.disconnect(); mo2.disconnect();
    document.removeEventListener('visibilitychange', sync); reduce.removeEventListener('change', onReduce);
  };
}

/** Mount a scene on a `.ons-scene` element containing a <canvas>. Returns a cleanup function. */
export function mountScene(el) { return mount(el); }
