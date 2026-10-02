// Studit glyph art: a shape rendered as glowing pixels that dissolve into mono glyphs (+ □ · ▪).
// Usage: <canvas data-glyph="search" data-size="200"></canvas>  ·  data-glyph="text:404" draws text.
// Glyph.scan() mounts new canvases; Glyph.boost(el, true) speeds the dissolve (AI loading).
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  // phones / weak CPUs: 20 fps and 1x canvases
  const low = matchMedia("(max-width: 720px)").matches || (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 4;
  const FRAME = low ? 50 : 33;
  const EMBER = [255, 80, 5], SAND = [219, 186, 149], LILAC = [208, 188, 225], BONE = [237, 232, 223];
  const CHARS = ["+", "□", "·", "▪", "+", "◦", "+", "□"];

  // 24-unit shapes (Lucide geometry). mode: s = stroke, f = fill (alpha), c = cut out
  const SHAPES = {
    search: [["M11 3a8 8 0 1 0 0 16a8 8 0 1 0 0-16z", "f", .35], ["M11 3a8 8 0 1 0 0 16a8 8 0 1 0 0-16z M21 21l-4.3-4.3", "s"]],
    sparkles: [["M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z", "f", 1], ["M20 3v4 M22 5h-4 M4 17v2 M5 18H3", "s"]],
    book: [["M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z", "f", .55], ["M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z", "s"]],
    vault: [["M3 4a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z", "f", .3], ["M3 4a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z M6 20v2 M18 20v2", "s"],
            ["M12 7a4.5 4.5 0 1 0 0 9a4.5 4.5 0 1 0 0-9z", "f", 1], ["M12 10a1.5 1.5 0 1 0 0 3a1.5 1.5 0 1 0 0-3z", "c"]],
    hand: [["M18 11V6a2 2 0 0 0-4 0 M14 10V4a2 2 0 0 0-4 0v2 M10 10.5V6a2 2 0 0 0-4 0v8 M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15", "s"],
           ["M6 12h16v2a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-6-2.3L6 16z", "f", .45]],
    bookmark: [["M19 21l-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z", "f", .8], ["M19 21l-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z", "s"]],
    send: [["M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z", "f", .85], ["M21.854 2.147l-10.94 10.939", "c"]],
    files: [["M4 6h2v15h11v2H4z", "f", .45], ["M8 2h9l4 4v13H8z", "f", .85], ["M11 9h7 M11 12h7 M11 15h4", "c"]],
    unlink: [["M18.84 12.25l1.72-1.71a5 5 0 0 0-7.07-7.07l-1.72 1.71 M5.17 11.75l-1.71 1.71a5 5 0 0 0 7.07 7.07l1.71-1.71 M8 2v3 M2 8h3 M16 19v3 M19 16h3", "s"]],
    flame: [["M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z", "f", 1]],
    inbox: [["M22 12h-6l-2 3h-4l-2-3H2", "s"], ["M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z", "f", .4], ["M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z", "s"]],
  };

  const hash = (x, y) => { const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return s - Math.floor(s); };
  const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  const live = new Set();

  function sampleMask(spec, cols) {
    const R = cols * 4, off = document.createElement("canvas");
    off.width = off.height = R;
    const g = off.getContext("2d");
    g.fillStyle = g.strokeStyle = "#fff"; g.lineCap = g.lineJoin = "round";
    if (spec.startsWith("text:")) {
      const txt = spec.slice(5);
      g.font = `400 ${R * .62}px "Instrument Serif", Georgia, serif`;
      g.textAlign = "center"; g.textBaseline = "middle";
      const w = g.measureText(txt).width, k = Math.min(1, R * .92 / w);
      g.setTransform(k, 0, 0, k, R / 2 * (1 - k), R / 2 * (1 - k));
      g.fillText(txt, R / 2, R * .54);
    } else {
      const k = R / 24 * .84;
      g.setTransform(k, 0, 0, k, R * .08, R * .08);
      g.lineWidth = 2.3;
      for (const [d, mode, a = 1] of SHAPES[spec] || SHAPES.sparkles) {
        const p = new Path2D(d);
        g.globalCompositeOperation = mode === "c" ? "destination-out" : "source-over";
        g.globalAlpha = a;
        if (mode === "s" || mode === "c") g.stroke(p); else g.fill(p);
      }
    }
    const small = document.createElement("canvas");
    small.width = small.height = cols;
    const sg = small.getContext("2d");
    sg.imageSmoothingQuality = "high";
    sg.drawImage(off, 0, 0, cols, cols);
    const px = sg.getImageData(0, 0, cols, cols).data, m = new Float32Array(cols * cols);
    for (let i = 0; i < m.length; i++) m[i] = px[i * 4 + 3] / 255;
    return m;
  }

  function mount(cv) {
    if (cv.dataset.glyphOn) return;
    cv.dataset.glyphOn = "1";
    const size = Number(cv.dataset.size) || 180, cell = Number(cv.dataset.cell) || (size > 260 ? 8 : 7);
    const cols = Math.floor(size / cell), dpr = Math.min(devicePixelRatio || 1, low ? 1.25 : 1.5);
    cv.width = cv.height = Math.round(cols * cell * dpr);
    cv.style.width = cols * cell + "px"; cv.style.maxWidth = "100%"; cv.style.height = "auto";
    cv.setAttribute("aria-hidden", "true");
    const ctx = cv.getContext("2d");
    ctx.scale(dpr, dpr);
    let mask = sampleMask(cv.dataset.glyph, cols);
    // halo cells: empty cells near the shape get sparse ember glyphs, like the reference's fin sparks
    const near = new Uint8Array(cols * cols);
    for (let y = 0; y < cols; y++) for (let x = 0; x < cols; x++) {
      if (mask[y * cols + x] > .15) continue;
      outer: for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) {
        const X = x + dx, Y = y + dy;
        if (X >= 0 && Y >= 0 && X < cols && Y < cols && mask[Y * cols + X] > .4) { near[y * cols + x] = hash(x, y) < .22 ? 1 : 0; break outer; }
      }
    }
    const ox = new Float32Array(cols * cols), oy = new Float32Array(cols * cols);
    const st = { cv, t: Math.random() * 10, visible: false, px: -99, py: -99, last: 0 };
    st.remask = () => { mask = sampleMask(cv.dataset.glyph, cols); };

    cv.addEventListener("pointermove", (e) => { const r = cv.getBoundingClientRect(); st.px = (e.clientX - r.left) / r.width * cols; st.py = (e.clientY - r.top) / r.height * cols; });
    cv.addEventListener("pointerleave", () => { st.px = st.py = -99; });

    st.draw = (dt) => {
      st.t += dt * (cv.dataset.boost ? 3.2 : 1);
      const t = st.t, W = cols * cell;
      ctx.clearRect(0, 0, W, W);
      ctx.font = `${Math.round(cell * 1.25)}px "Geist Mono", ui-monospace, monospace`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const breathe = 1 + Math.sin(t * .9) * .012;
      ctx.save(); ctx.translate(W / 2, W / 2); ctx.scale(breathe, breathe); ctx.translate(-W / 2, -W / 2);
      for (let y = 0; y < cols; y++) for (let x = 0; x < cols; x++) {
        const i = y * cols + x, a = mask[i];
        // cursor repel
        const dx = x - st.px, dy = y - st.py, d = Math.hypot(dx, dy), R = cols * .2;
        const push = d < R ? (1 - d / R) : 0;
        ox[i] += ((push ? dx / (d || 1) * push * cell * 1.6 : 0) - ox[i]) * .14;
        oy[i] += ((push ? dy / (d || 1) * push * cell * 1.6 : 0) - oy[i]) * .14;
        const cx = x * cell + cell / 2 + ox[i], cy = y * cell + cell / 2 + oy[i], h = hash(x, y);
        if (a < .15) {
          if (!near[i]) continue;
          const tw = .5 + .5 * Math.sin(t * 2.2 + h * 40);
          if (tw < .35) continue;
          ctx.fillStyle = rgba(EMBER, tw * .85);
          ctx.fillText(CHARS[(h * 8) | 0], cx, cy);
          continue;
        }
        const band = Math.sin(x * .33 + t * 1.1) * Math.cos(y * .29 - t * .8) + Math.sin((x + y) * .17 + t * .6);
        const glyph = band > .95 - (1 - a) * .6 || push > .25 || (h > .97 && Math.sin(t * 3 + h * 50) > 0);
        const grad = (x + (cols - y)) / (2 * cols);
        let c = mix(EMBER, SAND, Math.min(1, grad * 1.25));
        if (band > 1.3) c = mix(c, LILAC, .6);
        const lum = (.82 + .18 * Math.sin(t * 1.7 + h * 12)) * Math.min(1, .25 + a * 1.1);
        if (glyph) {
          ctx.fillStyle = rgba(h > .5 ? LILAC : BONE, .55 + lum * .45);
          ctx.fillText(CHARS[((h * 97 + t * 2) | 0) % CHARS.length], cx, cy);
        } else {
          ctx.fillStyle = rgba(c, lum);
          ctx.fillRect(cx - cell / 2 + .6, cy - cell / 2 + .6, cell - 1.2, cell - 1.2);
        }
      }
      ctx.restore();
    };
    st.draw(0);
    live.add(st);
    io.observe(cv);
  }

  const io = new IntersectionObserver((es) => es.forEach((e) => { for (const s of live) if (s.cv === e.target) s.visible = e.isIntersecting; }), { rootMargin: "80px" });

  // weak devices: skip glyph redraws while the user is scrolling (the art is moving past anyway)
  let scrollingUntil = 0;
  if (low) addEventListener("scroll", () => (scrollingUntil = performance.now() + 180), { passive: true });
  let prev = performance.now();
  function loop(now) {
    const dt = Math.min((now - prev) / 1000, .05);
    if (now - prev >= FRAME && now > scrollingUntil) {
      prev = now;
      for (const s of live) { if (!s.cv.isConnected) { live.delete(s); io.unobserve(s.cv); continue; } if (s.visible && !document.hidden) s.draw(dt); }
    }
    requestAnimationFrame(loop);
  }

  window.Glyph = {
    scan(root = document) { root.querySelectorAll("canvas[data-glyph]").forEach(mount); },
    boost(el, on) { if (el) on ? (el.dataset.boost = "1") : delete el.dataset.boost; },
  };
  const start = () => { Glyph.scan(); if (!reduce) requestAnimationFrame(loop); };
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", start); else start();
  // fonts load late: redraw once so glyph characters use Geist Mono
  document.fonts?.ready.then(() => live.forEach((s) => { if (s.cv.dataset.glyph.startsWith("text:")) s.remask(); s.draw(0); }));
})();
