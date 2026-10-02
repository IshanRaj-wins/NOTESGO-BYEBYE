// Studit auth: Supabase "Continue with Google", restricted to @bmsce.ac.in.
// The browser only holds the public publishable key; Flask re-verifies every token server-side.
(() => {
  const DOMAIN = "bmsce.ac.in";
  const cfg = window.SV_AUTH;
  if (!cfg || !window.supabase) return;
  const sb = window.supabase.createClient(cfg.url, cfg.key);
  window.svSupabase = sb;

  const $ = (s) => document.querySelector(s);

  // Hand the Supabase session to Flask, which checks the domain and sets a cookie
  async function handoff(session) {
    const r = await fetch("/api/auth/session", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: session.access_token }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { await sb.auth.signOut(); throw new Error(d.error || "Couldn't sign you in."); }
    location.href = cfg.next || "/dashboard";
  }

  // Sign out everywhere (used by the dashboard)
  window.svSignOut = async () => {
    try { await sb.auth.signOut(); } catch {}
    await fetch("/api/auth/logout", { method: "POST" });
    location.href = "/";
  };

  const btn = $("#google-btn");
  if (!btn) return;
  const label = btn.innerHTML;
  const msg = (text, kind = "err") => { const m = $("#msg"); m.textContent = text; m.className = `msg show ${kind}`; };
  const busy = (text) => { btn.disabled = true; btn.innerHTML = `<span class="spin"></span> ${text}`; };
  const reset = () => { btn.disabled = false; btn.innerHTML = label; };

  // Returning from Google (or an existing Supabase session): hand it to Flask once
  let handed = false;
  sb.auth.onAuthStateChange((event, session) => {
    if (handed || !session || !["SIGNED_IN", "INITIAL_SESSION"].includes(event)) return;
    handed = true;
    setTimeout(() => {
      busy("Signing you in…");
      handoff(session).catch((e) => { handed = false; reset(); msg(e.message); });
    });
  });

  // Supabase puts OAuth errors in the URL (e.g. the domain hook rejected the account)
  const err = new URLSearchParams(location.hash.slice(1) || location.search).get("error_description");
  if (err) msg(/bmsce/i.test(err) ? err : `Couldn't sign you in: ${err}`);

  btn.addEventListener("click", async () => {
    busy("Opening Google…");
    const { error } = await sb.auth.signInWithOAuth({ provider: "google", options: {
      redirectTo: location.origin + "/login?next=" + encodeURIComponent(cfg.next || "/dashboard"),
      queryParams: { hd: DOMAIN, prompt: "select_account" } } });
    if (error) { reset(); msg(error.message); }
  });
})();
