/* Shadow Motion v4. Canvas renderer shared by browser and offline preview. */
(function (root) {
  'use strict';
  const INK = '#1a2029', BODY_TOP = '#252d3a', RIM = '#5c6d84', IVORY = '#f6f1e3', ACCENT = '#d89b48';

  function smooth(ctx, p) {
    const n = p.length;
    ctx.beginPath();
    ctx.moveTo((p[n - 1][0] + p[0][0]) / 2, (p[n - 1][1] + p[0][1]) / 2);
    for (let i = 0; i < n; i++) {
      const a = p[i], b = p[(i + 1) % n];
      ctx.quadraticCurveTo(a[0], a[1], (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
    }
    ctx.closePath();
  }

  function cap(ctx, a, b, wa, wb, strokeCol) {
    const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1, nx = -dy / l, ny = dx / l;
    ctx.beginPath();
    ctx.moveTo(a[0] + nx * wa / 2, a[1] + ny * wa / 2);
    ctx.lineTo(b[0] + nx * wb / 2, b[1] + ny * wb / 2);
    ctx.lineTo(b[0] - nx * wb / 2, b[1] - ny * wb / 2);
    ctx.lineTo(a[0] - nx * wa / 2, a[1] - ny * wa / 2);
    ctx.closePath();
    ctx.fill();
    if (strokeCol) { ctx.strokeStyle = strokeCol; ctx.lineWidth = 1.4; ctx.stroke(); }
    ctx.beginPath(); ctx.arc(a[0], a[1], wa / 2, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(b[0], b[1], wb / 2, 0, Math.PI * 2); ctx.fill();
  }

  function headPath(ctx) {
    ctx.scale(1.16, 1.16);
    smooth(ctx, [
      [0, -47], [25, -41], [35, -15], [33, 12], [23, 34],
      [0, 46], [-23, 34], [-33, 12], [-35, -15], [-25, -41]
    ]);
    ctx.scale(1 / 1.16, 1 / 1.16);
  }

  function hairPath(ctx) {
    ctx.scale(1.16, 1.16);
    ctx.beginPath();
    ctx.moveTo(-32, -18);
    ctx.quadraticCurveTo(-36, -42, -14, -49);
    ctx.quadraticCurveTo(-4, -58, 8, -51);
    ctx.quadraticCurveTo(20, -56, 26, -44);
    ctx.quadraticCurveTo(38, -36, 32, -18);
    ctx.quadraticCurveTo(18, -36, 0, -37);
    ctx.quadraticCurveTo(-18, -36, -32, -18);
    ctx.closePath();
    ctx.scale(1 / 1.16, 1 / 1.16);
  }

  function drawLegsAndTorso(ctx, P, studio) {
    // Legs
    P.legs.forEach((l, i) => {
      cap(ctx, l.s, l.e, 40, 28);
      cap(ctx, l.e, l.w, 28, 19);
      const sx = i ? 1 : -1;
      ctx.beginPath();
      ctx.ellipse(l.foot[0] + sx * 3, l.foot[1] - 7, 23, 10.5, sx * 0.06, 0, Math.PI * 2);
      ctx.fill();
    });

    // Torso & Neck
    smooth(ctx, P.torso);
    ctx.fill();
    cap(ctx, P.neckBase, [P.head.x, P.head.y + 38], 30, 26);

    // Subtle Studio Jacket Lapels & Shirt V-Neck
    if (studio) {
      const nb = P.neckBase;
      ctx.save();
      ctx.fillStyle = 'rgba(246, 241, 227, 0.12)';
      ctx.beginPath();
      ctx.moveTo(nb[0] - 15, nb[1] - 4);
      ctx.lineTo(nb[0] + 15, nb[1] - 4);
      ctx.lineTo(nb[0], nb[1] + 54);
      ctx.closePath();
      ctx.fill();

      ctx.strokeStyle = 'rgba(92, 109, 132, 0.45)';
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.moveTo(nb[0] - 20, nb[1] - 2);
      ctx.lineTo(nb[0] - 28, nb[1] + 28);
      ctx.lineTo(nb[0], nb[1] + 62);
      ctx.lineTo(nb[0] + 28, nb[1] + 28);
      ctx.lineTo(nb[0] + 20, nb[1] - 2);
      ctx.stroke();
      ctx.restore();
    }
  }

  function drawHeadBase(ctx, P, studio) {
    const yawPx = (P.head.yaw || 0) * 18;
    const pitchPx = (P.head.pitch || 0) * 10;
    ctx.save();
    ctx.translate(P.head.x, P.head.y);
    ctx.rotate(P.head.tilt);
    // Ears shift opposite to head yaw for 3D parallax
    [-1, 1].forEach(s => {
      ctx.beginPath();
      ctx.ellipse(s * 40 - yawPx * 0.35, 3 - pitchPx * 0.3, 6, 11, 0, 0, Math.PI * 2);
      ctx.fill();
    });
    headPath(ctx);
    ctx.fill();
    if (studio) {
      hairPath(ctx);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawArm(ctx, a, bodyFill, isRim, studio) {
    ctx.save();
    if (!isRim) {
      // Soft drop-shadow & rim separation so hands in front of the chest stand out clearly!
      ctx.shadowColor = 'rgba(8, 10, 14, 0.55)';
      ctx.shadowBlur = 2;
      ctx.shadowOffsetY = 2;
    }
    const outline = isRim ? null : 'rgba(110, 130, 158, 0.38)';
    // Smooth shoulder blend (no protruding ball!)
    cap(ctx, a.s, a.e, 28, 21, outline);
    cap(ctx, a.e, a.w, 21, 14.5, outline);

    // Subtle sleeve cuff when in studio presenter mode
    if (!isRim && studio) {
      const ang = Math.atan2(a.w[1] - a.e[1], a.w[0] - a.e[0]);
      ctx.save();
      ctx.translate(a.w[0] - Math.cos(ang) * 6, a.w[1] - Math.sin(ang) * 6);
      ctx.rotate(ang);
      ctx.strokeStyle = 'rgba(246, 241, 227, 0.32)';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(0, -7);
      ctx.lineTo(0, 7);
      ctx.stroke();
      ctx.restore();
    }

    // One skin silhouette: outlining every phalanx made the hand look mechanical.
    ctx.shadowBlur = 0;
    const fingers=a.hand.fingers.slice().sort((a,b)=>(a.pts3?.[3][2]||0)-(b.pts3?.[3][2]||0));
    function skin(fill,padding) {
      ctx.fillStyle=fill;
      function finger(f){for(let j=0;j<3;j++)cap(ctx,f.pts[j],f.pts[j+1],f.w[j]+padding,f.w[j+1]+padding);}
      fingers.filter(f=>!f.thumb).forEach(finger);
      smooth(ctx,a.hand.palm);ctx.fill();
      if(padding){ctx.strokeStyle=fill;ctx.lineWidth=padding;ctx.stroke();}
      fingers.filter(f=>f.thumb).forEach(finger);
    }
    // Two complete passes outline the combined silhouette, not each joint.
    // Essential when a dark hand is in front of the dark chest/shoulder.
    if(!isRim)skin('#4c5a6b',1.6);
    skin(bodyFill,0);
    ctx.restore();
  }

  function face(ctx, P, studio, eyesOnly) {
    const h = P.head, E = P.eyes, B = P.brows, M = P.mouth;
    ctx.save();
    ctx.translate(h.x, h.y);
    ctx.rotate(h.tilt);
    ctx.scale(1.16, 1.16);

    const yaw = (h.yaw || 0) * 38;
    const pitch = (h.pitch || 0) * 14;

    // Subtle charismatic presenter beard/stubble shading in studio mode
    if (studio) {
      ctx.save();
      ctx.fillStyle = 'rgba(12, 15, 20, 0.35)';
      ctx.beginPath();
      ctx.ellipse(yaw * 0.45, 23 + pitch * 0.6, 24, 17, 0, 0.1, Math.PI - 0.1);
      ctx.fill();
      ctx.restore();
    }

    [-1, 1].forEach(s => {
      const ex = s * 15 + yaw * 0.75;
      const ey = -4 + pitch * 0.65;
      const open = Math.max(0.04, s < 0 ? E.lidL : E.lidR);
      const ry = 6.0 * Math.min(open, 1.38);

      // Sclera (eye white)
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(ex, ey, 8.4, ry, 0, 0, Math.PI * 2);
      ctx.fillStyle = IVORY;
      ctx.fill();
      ctx.clip();

      // Pupil + charismatic eye catchlight (spark of life!)
      const px = ex + E.gx * 3.4, py = ey + E.gy * 2.4;
      ctx.beginPath();
      ctx.arc(px, py, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = INK;
      ctx.fill();

      if (open > 0.25) {
        ctx.beginPath();
        ctx.arc(px - 1.2, py - 1.2, 1.15, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.fill();
      }
      ctx.restore();

      // Expressive Eyebrows
      const by = (s < 0 ? B.ly : B.ry) - 16.5 + pitch * 0.75;
      const tl = (s < 0 ? B.lt : B.rt) * 14;
      ctx.strokeStyle = '#75859c';
      ctx.lineWidth = 3.6;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(ex - s * 10.5, by + tl);
      ctx.quadraticCurveTo(ex, by - 3.0, ex + s * 10.5, by - tl * 0.35);
      ctx.stroke();
    });

    // Iconic Presenter Glasses (Da7ee7 vibe)
    if (studio) {
      ctx.save();
      ctx.strokeStyle = ACCENT;
      ctx.lineWidth = 2.2;
      [-1, 1].forEach(s => {
        const gx = s * 15.2 + yaw * 0.78, gy = -3.8 + pitch * 0.65;
        ctx.beginPath();
        ctx.roundRect ? ctx.roundRect(gx - 11.5, gy - 8.5, 23, 17, 4.5) : ctx.rect(gx - 11.5, gy - 8.5, 23, 17);
        ctx.stroke();
      });
      // Bridge
      ctx.beginPath();
      ctx.moveTo(-3.7 + yaw * 0.78, -4.5 + pitch * 0.65);
      ctx.quadraticCurveTo(yaw * 0.78, -6.5 + pitch * 0.65, 3.7 + yaw * 0.78, -4.5 + pitch * 0.65);
      ctx.stroke();
      ctx.restore();
    }

    if (eyesOnly) {ctx.restore();return;}
    // Expressive Bezier Mouth
    const mx = yaw * 0.62;
    const my = 24 + pitch * 0.75;
    const w = (5.5 + M.wide * 6.5) * (1 - M.round * 0.38);
    const o = M.open * 10.5;
    const sm = M.smile * 5.2;
    const cornerY = my - sm * 0.55;

    if (o > 0.65) {
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(mx - w, cornerY);
      ctx.quadraticCurveTo(mx, my - o * 0.35 + sm * 0.15, mx + w, cornerY);
      ctx.quadraticCurveTo(mx, my + o * 0.95 + sm * 0.45, mx - w, cornerY);
      ctx.closePath();

      // Inner mouth cavity
      ctx.fillStyle = '#3a1d24';
      ctx.fill();
      ctx.clip();

      // Upper teeth
      if (o > 1.8) {
        ctx.fillStyle = IVORY;
        ctx.fillRect(mx - w * 0.78, my - o * 0.35, w * 1.56, Math.min(3.4, o * 0.38));
      }
      // Tongue
      if (o > 3.2) {
        ctx.fillStyle = '#c45b62';
        ctx.beginPath();
        ctx.ellipse(mx, my + o * 0.58 + sm * 0.2, w * 0.55, o * 0.35, 0, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      // Crisp ivory lip outline
      ctx.strokeStyle = IVORY;
      ctx.lineWidth = 1.9;
      ctx.beginPath();
      ctx.moveTo(mx - w, cornerY);
      ctx.quadraticCurveTo(mx, my - o * 0.35 + sm * 0.15, mx + w, cornerY);
      ctx.quadraticCurveTo(mx, my + o * 0.95 + sm * 0.45, mx - w, cornerY);
      ctx.stroke();
    } else {
      ctx.strokeStyle = IVORY;
      ctx.lineWidth = 2.5;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(mx - w, cornerY);
      ctx.quadraticCurveTo(mx, my + sm * 0.65 + o * 0.5, mx + w, cornerY);
      ctx.stroke();
    }

    ctx.restore();
  }

  function background(ctx, W, H) {
    let g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, '#f3ebd8');
    g.addColorStop(0.68, '#d4c5a4');
    g.addColorStop(1, '#b8a582');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    g = ctx.createRadialGradient(640, 290, 40, 640, 290, 640);
    g.addColorStop(0, 'rgba(255,250,235,0.65)');
    g.addColorStop(1, 'rgba(255,250,235,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    ctx.fillStyle = '#a89572';
    ctx.fillRect(0, 648, W, H - 648);
    ctx.fillStyle = '#8c7a58';
    ctx.fillRect(0, 646, W, 3);
  }

  function draw(ctx, P, o) {
    o = o || {};
    const studio = o.studio !== false; // Default ON for charismatic presenter look
    const W = ctx.canvas.width, H = ctx.canvas.height, k = Math.min(W / 1280,H / 720);
    ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,W,H);
    ctx.setTransform(k, 0, 0, k, (W-1280*k)/2, (H-720*k)/2);

    if (o.bg !== false) {
      background(ctx, 1280, 720);
      ctx.fillStyle = 'rgba(50,38,20,0.24)';
      ctx.beginPath();
      ctx.ellipse(640 + (P.torso[0][0] - 622) * 0.5, 654, 118, 11, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.save();
    if(o.closeup){ctx.translate(640,360);ctx.scale(1.75,1.75);ctx.translate(-640,-280);}
    // 1. Rim light pass
    ctx.fillStyle = RIM;
    ctx.save();
    ctx.translate(-2.4, -2.4);
    drawLegsAndTorso(ctx, P, false);
    drawHeadBase(ctx, P, studio);
    ctx.restore();

    // 2. Main Torso & Head Base pass
    const g = ctx.createLinearGradient(0, 100, 0, 650);
    g.addColorStop(0, BODY_TOP);
    g.addColorStop(1, INK);
    ctx.fillStyle = g;
    const arms=P.arms.slice().sort((a,b)=>(a.depth||0)-(b.depth||0));
    arms.filter(a=>(a.depth||0)<-2).forEach(a=>drawArm(ctx,a,g,false,studio));
    drawLegsAndTorso(ctx, P, studio);
    drawHeadBase(ctx, P, studio);
    face(ctx, P, studio, o.eyesOnly);
    // Positive z points toward the viewer. Front hands may overlap the head.
    ctx.fillStyle = g;
    arms.filter(a=>(a.depth||0)>=-2).forEach(a=>drawArm(ctx,a,g,false,studio));

    // 5. Optional Debug Skeleton
    if (o.skeleton) {
      ctx.strokeStyle = '#ff5a3c';
      ctx.fillStyle = '#ff5a3c';
      ctx.lineWidth = 2;
      const L = (a, b) => { ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); };
      P.arms.forEach(a => {
        L(a.s, a.e); L(a.e, a.w);
        [a.s, a.e, a.w].forEach(p => { ctx.beginPath(); ctx.arc(p[0], p[1], 4, 0, Math.PI * 2); ctx.fill(); });
        a.hand.fingers.forEach(f => {
          for (let j = 0; j < 3; j++) L(f.pts[j], f.pts[j + 1]);
          f.pts.forEach(p => { ctx.beginPath(); ctx.arc(p[0], p[1], 2, 0, Math.PI * 2); ctx.fill(); });
        });
      });
      P.legs.forEach(l => { L(l.s, l.e); L(l.e, l.w); });
      if(P.joints){
        const j=Object.values(P.joints);for(let i=1;i<j.length;i++)L(j[i-1],j[i]);
        j.forEach(p=>{ctx.beginPath();ctx.arc(p[0],p[1],4,0,Math.PI*2);ctx.fill();});
        P.arms.forEach(a=>{if(a.clavicle3)L(...a.clavicle3);});
      }
    }
    ctx.restore();
  }

  root.ShadowDraw = { draw };
})(typeof window !== 'undefined' ? window : globalThis);
