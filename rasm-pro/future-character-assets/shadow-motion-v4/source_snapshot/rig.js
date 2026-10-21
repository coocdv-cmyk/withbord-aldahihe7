/* Shadow v3 Pro — Charismatic Procedural Presenter Engine.
   Spring-damper physics, 2-bone IK, secondary motion, eye-hand coordination, and Arabic prosody. */
(function (root) {
  'use strict';
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const fract = x => x - Math.floor(x);
  const hash = k => fract(Math.sin(k * 12.9898 + 78.233) * 43758.5453);
  const ease = x => { x = clamp(x); return x * x * (3 - 2 * x); };
  const easeOutBack = x => { x = clamp(x); const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };

  const W = 1280, H = 720, FPS = 30, CX = 640, FLOOR = 652;
  const LEN = { upper: 92, fore: 82, thigh: 120, shin: 118 };

  // Second-order spring solver with under-damped organic overshoot
  class Sp {
    constructor(n, w, z, init) {
      this.n = n; this.w = w; this.z = z;
      this.x = init ? init.slice() : Array(n).fill(0);
      this.v = Array(n).fill(0);
    }
    step(dt, t) {
      for (let i = 0; i < this.n; i++) {
        const a = this.w * this.w * (t[i] - this.x[i]) - 2 * this.z * this.w * this.v[i];
        this.v[i] += a * dt;
        this.x[i] += this.v[i] * dt;
      }
    }
  }

  // ---- Hand poses: curl 0..1 per finger [thumb,index,middle,ring,pinky], spread, wrist-up bend
  const HANDS = {
    relax:   { c: [.24, .18, .26, .34, .42], sp: .12, b: .04 },
    open:    { c: [.08, .05, .07, .10, .14], sp: .28, b: .16 },
    palmup:  { c: [.10, .08, .12, .16, .22], sp: .22, b: .34 },
    point:   { c: [.42, .02, .88, .92, .95], sp: .06, b: .08 },
    pointup: { c: [.45, .02, .88, .92, .95], sp: .06, b: .52 },
    pinch:   { c: [.52, .56, .24, .30, .36], sp: .16, b: .22 },
    count2:  { c: [.55, .02, .04, .88, .92], sp: .24, b: .42 },
    fist:    { c: [.68, .86, .90, .92, .94], sp: .02, b: .10 }
  };

  // ---- Gestures: comfortable reach (< 152px from shoulder so 0 clamped frames even on big beats)
  // o: [outward_x (negative = crosses in front of chest), downward_y], h: hand pose, lean, nod, lookHand
  const REST = { o: [26, 134], h: 'relax' };
  const GESTURES = {
    idle:          { L: REST, R: REST, lean: 0 },
    welcome:       { L: { o: [108, 48], h: 'palmup' }, R: { o: [108, 48], h: 'palmup' }, lean: 0, nod: -.12 },
    explain_r:     { L: { o: [18, 126], h: 'relax' },  R: { o: [86, 62],  h: 'open' },   lean: .35, nod: .08 },
    explain_l:     { L: { o: [86, 62],  h: 'open' },   R: { o: [18, 126], h: 'relax' },  lean: -.35, nod: .08 },
    chest_explain: { L: { o: [-18, 72], h: 'palmup' }, R: { o: [-14, 66], h: 'open' },   lean: .15, nod: .12 },
    point_l:       { L: { o: [134, 18], h: 'point' },  R: REST,                          lean: -.55, look: [-.45, -.05] },
    point_r:       { L: REST,                          R: { o: [134, 18], h: 'point' },  lean: .55,  look: [.45, -.05] },
    compare:       { L: { o: [92, 68],  h: 'palmup' }, R: { o: [92, 68],  h: 'palmup' }, lean: 0, alt: true },
    emphasize:     { L: { o: [-12, 92], h: 'relax' },  R: { o: [54, -14], h: 'pointup' },lean: .30, nod: .22 },
    question:      { L: { o: [74, 58],  h: 'palmup' }, R: { o: [74, 58],  h: 'palmup' }, lean: -.15, nod: -.18 },
    think:         { L: { o: [-22, 96], h: 'relax' },  R: { o: [-28, -8], h: 'pinch' },  lean: .20, nod: .10 },
    count_fingers: { L: { o: [-16, 88], h: 'open' },   R: { o: [42, 8],   h: 'count2' }, lean: .22, nod: .10 },
    mind_blown:    { L: { o: [58, -26], h: 'open' },   R: { o: [58, -26], h: 'open' },   lean: -.10, nod: -.20 },
    heart:         { L: REST,                          R: { o: [-38, 28], h: 'open' },   lean: -.18, nod: .15 }
  };

  // ---- Expressions: [lidL, lidR, browLy, browRy, browLtilt, browRtilt, gazeX, gazeY, smile]
  const EXPRESSIONS = {
    neutral:   [1.00, 1.00,  0.0,  0.0,  0.00,  0.00,  0.00,  0.00,  0.18],
    pleased:   [0.94, 0.94, -3.5, -3.5, -0.04,  0.04,  0.00,  0.00,  0.72],
    curious:   [1.16, 1.04, -5.5, -1.5, -0.08,  0.02,  0.18, -0.12,  0.28],
    thinking:  [0.84, 0.88, -1.5, -3.5,  0.04,  0.08, -0.38, -0.35,  0.05],
    skeptical: [0.82, 1.12,  2.5, -6.5,  0.16, -0.18,  0.10,  0.00,  0.08],
    surprised: [1.36, 1.36, -8.5, -8.5, -0.06,  0.06,  0.00, -0.08,  0.22],
    concerned: [0.92, 0.92, -3.0, -3.0, -0.22,  0.22,  0.00,  0.22, -0.15],
    serious:   [0.90, 0.90,  2.2,  2.2,  0.15, -0.15,  0.00,  0.00, -0.04],
    excited:   [1.24, 1.24, -6.5, -6.5, -0.05,  0.05,  0.00, -0.05,  0.85]
  };

  // ---- Mouth shapes [open, wide, round]
  const VISEMES = {
    X: [0.00, 0.52, 0.00],
    C: [0.24, 0.62, 0.08],
    A: [0.92, 0.68, 0.10],
    E: [0.48, 0.96, 0.00],
    I: [0.28, 0.98, 0.00],
    O: [0.76, 0.24, 0.95],
    U: [0.34, 0.12, 0.95],
    F: [0.16, 0.72, 0.05],
    M: [0.00, 0.44, 0.15]
  };

  // ---- Upgraded Arabic & Latin text-to-viseme with syllable vowel injection
  function visemeFor(ch, nextCh, k) {
    if ('مبپmbp'.includes(ch)) return 'M';
    if ('فvf'.includes(ch)) return 'F';
    if ('وؤُoóu'.includes(ch)) return k % 2 ? 'O' : 'U';
    if ('اأإآىَa'.includes(ch)) return 'A';
    if ('يئِeé'.includes(ch)) return 'E';
    if ('i'.includes(ch)) return 'I';
    if ('قخغعحهرضصطظ'.includes(ch)) return 'O'; // emphatic/guttural Arabic letters round/open mouth
    if ('شسزتدنلكجچ'.includes(ch)) return k % 3 === 0 ? 'E' : 'C';
    return 'C';
  }

  function speechToVisemes(text, t0, dur) {
    const clean = String(text).replace(/[،.؟!,?;:"]/g, ' ').trim();
    const words = clean.split(/\s+/).filter(Boolean), vis = [], beats = [];
    const units = words.reduce((a, w) => a + [...w].length * 1.15 + 1.2, 0) || 1;
    const u = dur / units;
    let t = t0, k = 0;
    words.forEach((w, wi) => {
      const ch = [...w];
      // Strong beat on first word and key content words
      if (wi === 0 || ch.length >= 4) {
        beats.push({ t: t + u * 0.4, s: wi === 0 ? 0.85 : 0.62 });
      }
      ch.forEach((c, ci) => {
        const next = ch[ci + 1] || '';
        const v = visemeFor(c.toLowerCase(), next, k++);
        vis.push({ t, v });
        t += u * 0.75;
        // Inject natural short vowel opening between Arabic consonants
        if (v === 'M' || v === 'C' || v === 'F') {
          vis.push({ t, v: (k % 2 === 0 ? 'A' : 'E') });
        }
        t += u * 0.40;
      });
      vis.push({ t, v: 'X' });
      t += u * 1.2;
    });
    return { visemes: vis, beats };
  }

  // ---- Two-bone IK solver with exact bone lengths
  function ik(s, target, a, b, sg) {
    const dx = target[0] - s[0], dy = target[1] - s[1], raw = Math.hypot(dx, dy);
    const d = clamp(raw, Math.abs(a - b) + 1, a + b - 0.5);
    const u = raw > 1e-6 ? [dx / raw, dy / raw] : [0, 1], p = [-u[1], u[0]];
    const q = (a * a - b * b + d * d) / (2 * d);
    const h = Math.sqrt(Math.max(0, a * a - q * q));
    return {
      s,
      e: [s[0] + u[0] * q + p[0] * h * sg, s[1] + u[1] * q + p[1] * h * sg],
      w: [s[0] + u[0] * d, s[1] + u[1] * d],
      clamped: Math.abs(raw - d) > 0.01,
      l1: a,
      l2: b
    };
  }

  // ---- Proportional Human Hand Geometry (HS = 0.88, natural arc curl without backward inversion)
  const FLEN = [[15, 13, 10], [13, 9.5, 7], [14.5, 10.5, 7.5], [13.5, 9.5, 7], [10.5, 7.5, 5.5]];
  const FBASE = [null, 0.78, 0.26, -0.26, -0.78];
  const FSPR = [0, 0.48, 0.14, -0.18, -0.55];

  function handGeom(w, ang, curls, spread, tsy) {
    const c = Math.cos(ang), s = Math.sin(ang);
    const HS = 0.88; // natural human hand proportion relative to forearm
    const P = (lx, ly) => [w[0] + HS * (lx * c - ly * s), w[1] + HS * (lx * s + ly * c)];
    const palm = [[-2, -9.5], [9, -12.5], [27, -13.5], [30, -5], [30, 5], [27, 13.5], [9, 14.5], [-2, 10.5]]
      .map(([x, y]) => P(x, y * tsy));
    const fingers = [];
    for (let f = 1; f < 5; f++) {
      const cu = clamp(curls[f], 0, 1);
      const base = [28, FBASE[f] * 10 * tsy];
      const pts = [P(base[0], base[1])];
      const wd = [8.6 - (f === 4 ? 1.4 : 0), 7.5, 6.5, 5.4];
      let x = base[0], y = base[1];
      let th = tsy * FSPR[f] * spread * 1.5;
      for (let j = 0; j < 3; j++) {
        // Smooth foreshortening + inward curl without negative cosine inversion
        const segScale = 1 - cu * [0.42, 0.52, 0.58][j];
        const bendAng = th - tsy * cu * [0.22, 0.45, 0.65][j];
        const L = FLEN[f][j] * segScale;
        x += L * Math.cos(bendAng);
        y += L * Math.sin(bendAng);
        pts.push(P(x, y));
      }
      fingers.push({ pts, w: wd, cum: cu });
    }
    // Thumb opposes naturally toward palm
    const tc = clamp(curls[0], 0, 1);
    let tx = 7, ty = tsy * 11, tth = tsy * (0.68 - tc * 0.48);
    const tp = [P(tx, ty)];
    for (let j = 0; j < 3; j++) {
      const L = FLEN[0][j] * (1 - tc * 0.22);
      tx += L * Math.cos(tth);
      ty += L * Math.sin(tth);
      tp.push(P(tx, ty));
      tth -= tsy * tc * (j === 0 ? 0.45 : 0.55);
    }
    fingers.push({ pts: tp, w: [10.2, 8.8, 7.6, 6.4], cum: tc, thumb: true });
    return { palm, fingers };
  }

  function createPerformer() {
    const sh0 = [[CX - 62, 244], [CX + 62, 244]];
    const S = {
      t: 0,
      wr: [0, 1].map(i => new Sp(2, 14.5, 0.64, [sh0[i][0] + (i ? 26 : -26), sh0[i][1] + 134])),
      curl: [0, 1].map(() => [24, 28, 25, 22, 20].map((w, i) => new Sp(1, w, 0.78, [HANDS.relax.c[i]]))),
      spread: [0, 1].map(() => new Sp(1, 15, 0.85, [0.12])),
      bend: [0, 1].map(() => new Sp(1, 12, 0.55, [0])),
      sh: [0, 1].map(() => new Sp(2, 13, 0.78)),
      // body: [0:chestX, 1:twist, 2:hipX, 3:headYaw, 4:headTilt, 5:headNod]
      body: new Sp(6, 6.8, 0.72),
      expr: new Sp(9, 14, 0.82, EXPRESSIONS.neutral),
      mouth: new Sp(3, 42, 0.82, VISEMES.X),
      hand: ['relax', 'relax'],
      speaking: 0,
      beatPulse: 0,
      nextBlink: 1.8,
      blinkStart: -1
    };

    const breathe = () => Math.sin(S.t * Math.PI * 2 / 3.4);

    function frame() {
      const b = S.body.x, br = breathe(), hipX = b[2], tw = b[1], ct = Math.cos(tw);
      const chestShift = b[0] + hipX * 0.55, hipShift = hipX;
      return {
        T(x, y) {
          const k = clamp((404 - y) / 160, 0, 1);
          return [
            CX + lerp(hipShift, chestShift, k) + x * lerp(1, ct, k),
            y + br * 1.8 * k + Math.abs(b[0]) * 0.08 * k
          ];
        },
        br
      };
    }

    function step(dt, inp) {
      const F = frame();
      const g = GESTURES[inp.gesture] || GESTURES.idle;
      const amt = clamp(inp.intensity == null ? 1 : inp.intensity, 0, 1.25);
      const ct = inp.cueT == null ? -1 : inp.cueT;
      const cd = inp.cueDur || 0;
      const active = inp.gesture !== 'idle' && ct >= 0 && ct < cd;

      // Anticipation & follow-through curve for human-like gesture phrasing
      let phase = 0;
      if (active) {
        if (ct < 0.16) phase = -0.10 * ease(ct / 0.16);
        else if (ct > cd - 0.45) phase = 1 - ease((ct - (cd - 0.45)) / 0.45);
        else phase = Math.min(1.06, easeOutBack(Math.min(1, (ct - 0.16) / 0.38)));
      }

      const sp = S.speaking;
      S.beatPulse = Math.max(0, S.beatPulse - dt * 3.5);

      for (let i = 0; i < 2; i++) {
        const sx = i ? 1 : -1;
        const spec = (i ? g.R : g.L) || REST;
        const shp = F.T(sx * 62, 244);

        const goal = [lerp(REST.o[0], spec.o[0], amt), lerp(REST.o[1], spec.o[1], amt)];
        const off = [
          REST.o[0] + (goal[0] - REST.o[0]) * phase,
          REST.o[1] + (goal[1] - REST.o[1]) * phase
        ];

        // Organic hand micro-motion & alternating weighing in 'compare' gesture
        const drift = (active ? 1.0 : 0.3) + sp * 0.45;
        const altWave = g.alt ? Math.sin(S.t * 3.8 + i * Math.PI) * 14 * phase : 0;
        off[0] += Math.sin(S.t * 3.1 + i * 2.1) * 3.2 * drift;
        off[1] += Math.cos(S.t * 2.4 + i * 1.4) * 2.6 * drift + altWave;

        const sh = S.sh[i].x;
        const base = [shp[0] + sh[1], shp[1] + sh[0]];

        // Safety radius clamp on target so arm never hits harsh IK limit
        let tx = base[0] + sx * off[0], ty = base[1] + off[1];
        const dist = Math.hypot(tx - base[0], ty - base[1]);
        if (dist > 152) {
          const sc = 152 / dist;
          tx = base[0] + (tx - base[0]) * sc;
          ty = base[1] + (ty - base[1]) * sc;
        }
        S.wr[i].step(dt, [tx, ty]);

        const name = active && ct > 0.08 ? spec.h : 'relax';
        const hp = HANDS[name] || HANDS.relax;
        S.hand[i] = name;
        S.curl[i].forEach((spn, f) => spn.step(dt, [hp.c[f] - S.beatPulse * 0.08]));
        S.spread[i].step(dt, [hp.sp + S.beatPulse * 0.06]);

        // Clavicle/shoulder natural lift when arm raises
        const wrist = S.wr[i].x;
        const up = clamp((shp[1] - wrist[1] + 55) / 180, 0, 1);
        S.sh[i].step(dt, [-9 * up - F.br * 1.2, sx * clamp(Math.abs(wrist[0] - shp[0]) / 150, 0, 1) * 3.5]);

        // Secondary wrist follow-through (drag behind forearm velocity)
        const v = S.wr[i].v;
        const ex = ik(base, wrist, LEN.upper, LEN.fore, sx);
        const fVec = [ex.w[0] - ex.e[0], ex.w[1] - ex.e[1]];
        const fl = Math.hypot(fVec[0], fVec[1]) || 1;
        const cross = (fVec[0] * v[1] - fVec[1] * v[0]) / fl;
        S.bend[i].step(dt, [-hp.b * sx - clamp(cross * 0.0022, -0.58, 0.58) + (sx > 0 ? 0.04 : -0.04)]);
      }

      // Dynamic body posture, weight shift, and expressive head orientation
      const lean = active ? (g.lean || 0) * amt * clamp(phase, 0, 1) : 0;
      const gNod = active ? (g.nod || 0) * amt * clamp(phase, 0, 1) : 0;
      const hipSway = Math.sin(S.t * 2 * Math.PI / 6.8) * 4.2 + lean * 3.5;
      const headYawTarget = lean * 0.16 + sp * Math.sin(S.t * 1.4) * 0.08 + Math.sin(S.t * 0.7) * 0.03;
      const headTiltTarget = lean * 0.07 + Math.sin(S.t * 0.9) * 0.025 + sp * Math.cos(S.t * 2.1) * 0.035;
      const headNodTarget = gNod + sp * Math.sin(S.t * 3.6) * 0.08;

      S.body.step(dt, [
        lean * 12,
        lean * 0.22,
        hipSway,
        headYawTarget,
        headTiltTarget,
        headNodTarget
      ]);

      // Facial expressions + automatic eyebrow lift on vocal beats & open mouth
      const baseEx = (EXPRESSIONS[inp.expr] || EXPRESSIONS.neutral).slice();
      const m = inp.mouth || VISEMES.X;
      const vocalLift = S.beatPulse * 3.2 + clamp(m[0] - 0.3, 0, 1) * 1.8;
      baseEx[2] -= vocalLift; // left brow lifts on emphasis
      baseEx[3] -= vocalLift; // right brow lifts on emphasis
      baseEx[0] += S.beatPulse * 0.10; // eyes widen slightly on emphasis
      baseEx[1] += S.beatPulse * 0.10;

      // Glance briefly toward pointing hand at the start of a pointing cue, then back to camera
      if (active && g.look && ct > 0.12 && ct < 1.15) {
        baseEx[6] += g.look[0];
        baseEx[7] += g.look[1];
      }

      S.expr.step(dt, baseEx);
      S.mouth.step(dt, m);
      S.speaking += ((inp.mouth && m[0] > 0.05 ? 1 : 0) - S.speaking) * Math.min(1, dt * 4);
      S.t += dt;
    }

    function beat(s) {
      s = clamp(s == null ? 0.65 : s, 0.2, 1.2);
      S.beatPulse = Math.min(1, S.beatPulse + s * 0.85);
      for (let i = 0; i < 2; i++) {
        const restX = i ? CX + 88 : CX - 88;
        const away = Math.hypot(S.wr[i].x[0] - restX, S.wr[i].x[1] - 378);
        // Subtle gesture accent without over-stretching the arm
        if (away > 28 && S.wr[i].x[1] < 365) {
          S.wr[i].v[1] += 85 * s;
          S.wr[i].v[0] += (i ? 1 : -1) * 28 * s;
        }
      }
      // Natural head nod & slight tilt on speech emphasis
      S.body.v[5] += 1.45 * s;
      S.body.v[4] += (Math.sin(S.t * 4.3) >= 0 ? 0.22 : -0.22) * s;
    }

    function pose() {
      const F = frame(), t = S.t, b = S.body.x, ex = S.expr.x;
      const arms = [0, 1].map(i => {
        const sx = i ? 1 : -1;
        const shp = F.T(sx * 62, 244);
        const sh = S.sh[i].x;
        const s = [shp[0] + sh[1], shp[1] + sh[0]];
        const a = ik(s, S.wr[i].x, LEN.upper, LEN.fore, sx);
        const ang = Math.atan2(a.w[1] - a.e[1], a.w[0] - a.e[0]) + S.bend[i].x[0];
        const curls = S.curl[i].map(q => clamp(q.x[0], -0.05, 1.05));
        return Object.assign(a, {
          hand: handGeom(a.w, ang, curls, S.spread[i].x[0], i ? 1 : -1),
          handAngle: ang,
          handName: S.hand[i]
        });
      });

      // Fixed natural straight-stance legs (feet planted at y=634, zero bow-legged distortion)
      const legs = [0, 1].map(i => {
        const sx = i ? 1 : -1;
        const hip = F.T(sx * 33, 398);
        const ank = [CX + sx * 35, FLOOR - 18];
        return Object.assign(ik(hip, ank, LEN.thigh, LEN.shin, sx), { foot: [ank[0] + sx * 5, FLOOR] });
      });

      const torso = [
        [-18, 206], [-50, 220], [-66, 244], [-58, 282], [-45, 314],
        [-38, 356], [-42, 398], [-28, 422], [0, 426], [28, 422],
        [42, 398], [38, 356], [45, 314], [58, 282], [66, 244],
        [50, 220], [18, 206]
      ].map(([x, y]) => F.T(x, y));

      const neckBase = F.T(0, 220);
      const head = {
        x: neckBase[0] + b[3] * 20,
        y: neckBase[1] - 70 + b[5] * 3.5,
        tilt: b[4] + (ex[8] > 0.4 ? -0.025 : 0),
        yaw: b[3],
        pitch: b[5]
      };

      // O(1) deterministic natural blink (fast close, smooth open) + micro-saccades
      const bPeriod = 3.2;
      const bSlot = Math.floor(t / bPeriod);
      const bTime = bSlot * bPeriod + 0.9 + hash(bSlot * 7 + 3) * 1.9;
      let blink = 0;
      if (t >= bTime && t < bTime + 0.18) {
        const u = (t - bTime) / 0.18;
        blink = u < 0.35 ? ease(u / 0.35) : 1 - ease((u - 0.35) / 0.65);
      }

      const sk = Math.floor(t / 2.1);
      const gz = [(hash(sk) - 0.5) * 0.32, (hash(sk + 9) - 0.5) * 0.20];
      const m = S.mouth.x;

      return {
        t, arms, legs, torso, head, neckBase,
        eyes: {
          lidL: ex[0] * (1 - blink * 0.96),
          lidR: ex[1] * (1 - blink * 0.96),
          gx: clamp(ex[6] + gz[0], -0.85, 0.85),
          gy: clamp(ex[7] + gz[1], -0.75, 0.75)
        },
        brows: { ly: ex[2], ry: ex[3], lt: ex[4], rt: ex[5] },
        mouth: {
          open: clamp(m[0], 0, 1),
          wide: clamp(m[1], 0, 1),
          round: clamp(m[2], 0, 1),
          smile: clamp(ex[8], -0.4, 1)
        },
        breath: F.br
      };
    }

    return { step, beat, pose, state: S };
  }

  function compile(script) {
    const c = {
      cues: (script.cues || []).slice().sort((a, b) => a.t - b.t),
      vis: (script.visemes || []).slice(),
      beats: (script.beats || []).slice(),
      duration: script.duration || 30
    };
    (script.speech || []).forEach(s => {
      const r = speechToVisemes(s.text, s.t, s.dur);
      c.vis.push(...r.visemes);
      c.beats.push(...r.beats);
    });
    c.vis.sort((a, b) => a.t - b.t);
    c.beats.sort((a, b) => a.t - b.t);
    return c;
  }

  function inputAt(c, t) {
    let cue = null;
    for (const q of c.cues) if (t >= q.t && t < q.t + q.dur) cue = q;
    let v = 'X';
    for (const q of c.vis) { if (q.t <= t) v = q.v; else break; }
    return {
      gesture: cue ? cue.gesture : 'idle',
      expr: cue ? cue.expr || 'neutral' : 'neutral',
      cueT: cue ? t - cue.t : -1,
      cueDur: cue ? cue.dur : 0,
      intensity: cue && cue.intensity != null ? cue.intensity : 1,
      mouth: VISEMES[v] || VISEMES.X
    };
  }

  function sample(script, fps, dur) {
    const c = compile(script), P = createPerformer(), dt = 1 / 120, out = [];
    let bi = 0, t = 0;
    const n = Math.round((dur || c.duration) * (fps || FPS));
    for (let f = 0; f <= n; f++) {
      const T = f / (fps || FPS);
      while (t < T - 1e-9) {
        while (bi < c.beats.length && c.beats[bi].t <= t) P.beat(c.beats[bi++].s);
        P.step(dt, inputAt(c, t));
        t += dt;
      }
      out.push(P.pose());
    }
    return out;
  }

  const api = {
    W, H, FPS, CX, FLOOR, LEN, GESTURES, EXPRESSIONS, HANDS, VISEMES,
    createPerformer, compile, inputAt, sample, speechToVisemes, ik
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.ShadowRig = api;
})(typeof window !== 'undefined' ? window : globalThis);