// ---------- helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ic = (name) => `<i data-lucide="${name}"></i>`;

// render Lucide icons + mount glyph canvases after any dynamic HTML
function icons() {
  try { window.lucide?.createIcons(); } catch {}
  window.Glyph?.scan();
}

// cursor spotlight for .sv-card (one delegated listener)
addEventListener("pointermove", (e) => {
  const c = e.target.closest?.(".sv-card");
  if (!c) return;
  const r = c.getBoundingClientRect();
  c.style.setProperty("--mx", e.clientX - r.left + "px");
  c.style.setProperty("--my", e.clientY - r.top + "px");
}, { passive: true });

// glyph burst: + □ · particles pop out of a button
function burst(el) {
  if (!el || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const chars = ["+", "□", "·", "+", "▪", "+"];
  for (let i = 0; i < 9; i++) {
    const s = document.createElement("span");
    s.className = "burst"; s.textContent = chars[i % chars.length];
    s.style.left = cx + "px"; s.style.top = cy + "px";
    document.body.appendChild(s);
    const a = (i / 9) * Math.PI * 2 + Math.random() * .5, d = 22 + Math.random() * 22;
    s.animate([{ transform: "translate(-50%,-50%) scale(.6)", opacity: 1 },
               { transform: `translate(calc(-50% + ${Math.cos(a) * d}px), calc(-50% + ${Math.sin(a) * d}px)) scale(1)`, opacity: 0 }],
              { duration: 650 + Math.random() * 250, easing: "cubic-bezier(.2,.7,.3,1)" }).onfinish = () => s.remove();
  }
  el.classList.remove("pop"); void el.offsetWidth; el.classList.add("pop");
}

function toast(msg, kind = "ok") {
  const box = $("#toasts");
  if (!box) return;
  const el = document.createElement("div");
  el.className = `toast fade-in ${kind}`;
  el.innerHTML = ic(kind === "err" ? "circle-alert" : kind === "ai" ? "sparkles" : "circle-check") + `<span>${esc(msg)}</span>`;
  box.appendChild(el);
  icons();
  setTimeout(() => { el.style.transition = "opacity .3s"; el.style.opacity = "0"; setTimeout(() => el.remove(), 300); }, 2600);
}

function setLoading(btn, on, label) {
  if (!btn) return;
  if (on) {
    btn.dataset.label = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> ${label || "Thinking…"}`;
  } else {
    btn.disabled = false;
    btn.innerHTML = btn.dataset.label;
  }
}

function needLogin(msg) {
  toast(msg || "Sign in with your @bmsce.ac.in email first", "err");
  setTimeout(() => { location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search); }, 1200);
}

async function postJSON(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  if (r.status === 401) { const d = await r.json().catch(() => ({})); needLogin(d.error); throw Object.assign(new Error(d.error), { login: true }); }
  if (!r.ok) throw new Error("Request failed");
  return r.json();
}

function aiBadge(mode) {
  return mode === "offline"
    ? `<span class="ai-badge off">${ic("zap")} Smart offline mode</span>`
    : `<span class="ai-badge">${ic("sparkles")}<span class="shimmer">AI generated</span></span>`;
}

const TYPE_COLOR = { "Notes": "#dbba95", "PYQ": "#ff5005", "Reference": "#d0bce1", "Video": "#ff8a52", "Lab Manual": "#9fd3b0", "Syllabus": "rgba(237,232,223,.6)" };
const typeBadge = (t) => `<span class="type-dot" style="--tc:${TYPE_COLOR[t] || TYPE_COLOR.Syllabus}">${esc(t)}</span>`;

// ---------- bookmarks (localStorage) ----------
const BM_KEY = "studyvault_bookmarks";
function getBookmarks() { try { return JSON.parse(localStorage.getItem(BM_KEY)) || []; } catch { return []; } }
function isBookmarked(id) { return getBookmarks().includes(Number(id)); }
function toggleBookmark(id, btn) {
  id = Number(id);
  let bm = getBookmarks();
  const on = !bm.includes(id);
  bm = on ? [...bm, id] : bm.filter((x) => x !== id);
  try { localStorage.setItem(BM_KEY, JSON.stringify(bm)); } catch {}
  document.querySelectorAll(`[data-bm="${id}"]`).forEach((b) => paintBookmark(b, on));
  if (on) burst(btn);
  toast(on ? "Saved to bookmarks" : "Removed from bookmarks");
  document.dispatchEvent(new CustomEvent("bookmarks-changed"));
}
function paintBookmark(btn, on) {
  btn.classList.toggle("on", on);
  if (btn.dataset.tip !== undefined) btn.dataset.tip = on ? "Saved" : "Save";
  const lbl = btn.querySelector("[data-bm-label]");
  if (lbl) lbl.textContent = on ? "Saved" : "Save";
}

// ---------- upvote / share ----------
async function upvote(id, btn) {
  const key = `sv_voted_${id}`;
  let voted = false;
  try { voted = localStorage.getItem(key); } catch {}
  if (voted) return toast("You already upvoted this");
  try {
    const d = await postJSON(`/api/resources/${id}/upvote`);
    try { localStorage.setItem(key, "1"); } catch {}
    document.querySelectorAll(`[data-votes="${id}"]`).forEach((el) => (el.textContent = d.upvotes));
    document.querySelectorAll(`[data-up="${id}"]`).forEach((b) => b.classList.add("on"));
    burst(btn);
    toast("Upvoted. Thanks for helping others!");
  } catch (e) { if (!e.login) toast("Couldn't upvote, try again", "err"); }
}

function shareWhatsApp(title, path, btn) {
  burst(btn);
  const link = location.origin + path;
  const text = `${title}\nFound this on Studit: ${link}`;
  window.open("https://wa.me/?text=" + encodeURIComponent(text), "_blank", "noopener");
}

// ---------- cards ----------
function cardHTML(r) {
  const tags = (r.tags || []).slice(0, 3).map((t) => `<span class="tag-s">#${esc(t)}</span>`).join("");
  const bm = isBookmarked(r.id);
  let voted = false;
  try { voted = localStorage.getItem(`sv_voted_${r.id}`); } catch {}
  return `
  <article class="sv-card lift group flex flex-col fade-in">
    <a href="/resource/${Number(r.id)}" class="p-5 flex-1 block">
      <div class="flex items-center gap-3">${typeBadge(r.type)}${r.semester ? `<span class="meta">Sem ${Number(r.semester)}</span>` : ""}${r.file_path ? `<span class="meta inline-flex items-center gap-1">${ic("file-text")}PDF</span>` : ""}</div>
      <h3 class="text-[1.02rem] font-medium leading-snug line-clamp-2 mt-3 group-hover:text-white">${esc(r.title)}</h3>
      <div class="text-sm text-bone/50 mt-1.5">${esc(r.subject)} · ${esc(r.uploader || "Anonymous")}</div>
      <div class="flex flex-wrap gap-1.5 mt-3">${tags}</div>
    </a>
    <div class="px-3 py-2 border-t border-bone/[.07] flex items-center gap-0.5">
      <button data-up="${Number(r.id)}" onclick="upvote(${Number(r.id)}, this)" class="icon-btn ${voted ? "on" : ""}" data-tip="Upvote">${ic("arrow-big-up")}<span data-votes="${Number(r.id)}">${Number(r.upvotes)}</span></button>
      <span class="icon-btn pointer-events-none">${ic("eye")}${Number(r.views)}</span>
      <span class="flex-1"></span>
      <button data-bm="${Number(r.id)}" onclick="toggleBookmark(${Number(r.id)}, this)" class="icon-btn ${bm ? "on" : ""}" data-tip="${bm ? "Saved" : "Save"}" aria-label="Bookmark">${ic("bookmark")}</button>
      <button data-title="${esc(r.title)}" onclick="shareWhatsApp(this.dataset.title, '/resource/${Number(r.id)}', this)" class="icon-btn" data-tip="WhatsApp" aria-label="Share to WhatsApp">${ic("send")}</button>
    </div>
  </article>`;
}

// empty state with glyph art: glyph = search | unlink | inbox | bookmark | send | sparkles ...
function emptyState(glyph, title, text, ctaHref, ctaText) {
  return `<div class="col-span-full sv-dashed text-center py-12 px-6 fade-in">
    <canvas data-glyph="${esc(glyph)}" data-size="150" class="mx-auto"></canvas>
    <div class="font-serif text-3xl mt-4">${title}</div>
    <p class="text-sm text-bone/55 mt-2 max-w-md mx-auto leading-relaxed">${text}</p>
    ${ctaHref ? `<a href="${ctaHref}" class="btn btn-ember btn-sm mt-6">${ctaText} <span class="arrow">→</span></a>` : ""}
  </div>`;
}

const skeleton = (n = 6) => Array.from({ length: n }, () =>
  `<div class="sv-card p-5"><div class="skel h-3 w-20"></div><div class="skel h-4 mt-5"></div><div class="skel h-4 w-2/3 mt-2"></div><div class="skel h-3 w-1/2 mt-5"></div></div>`).join("");

document.querySelectorAll("[data-bm]").forEach((b) => paintBookmark(b, isBookmarked(b.dataset.bm)));
