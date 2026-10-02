import os
import secrets
import shutil
import time
import uuid
from collections import defaultdict, deque
from datetime import timedelta
from functools import wraps
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

import requests as http
from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

import ai
from db import SUBJECTS, TYPES, get_db, init_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = "/tmp/uploads" if os.getenv("VERCEL") else os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
SEED_DIR = os.path.join(BASE_DIR, "seed_files")
for _f in os.listdir(SEED_DIR) if os.path.isdir(SEED_DIR) else []:
    if _f.lower().endswith(".pdf") and not os.path.exists(os.path.join(UPLOAD_DIR, _f)):
        shutil.copy(os.path.join(SEED_DIR, _f), UPLOAD_DIR)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
_sk = (os.getenv("FLASK_SECRET_KEY") or "").strip()
if len(_sk) < 24 or "change_me" in _sk:  # a guessable key lets anyone forge a logged-in session
    if os.getenv("VERCEL"):  # a random key per instance would log users out at random
        raise RuntimeError("FLASK_SECRET_KEY is missing or weak; set a 64-char hex value in Vercel env.")
    _sk = secrets.token_hex(32)
app.secret_key = _sk
app.permanent_session_lifetime = timedelta(days=30)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=bool(os.getenv("VERCEL")))
init_db()

ALLOWED_DOMAIN = "@bmsce.ac.in"
def _env(*names):
    # Pasted dashboard values often carry quotes, spaces, \r or a BOM; strip them.
    for n in names:
        v = (os.getenv(n) or "").strip().strip("﻿").strip().strip("'\"").strip()
        if v:
            return v
    return ""

SUPABASE_URL = _env("SUPABASE_URL").rstrip("/")
if SUPABASE_URL and "://" not in SUPABASE_URL:
    SUPABASE_URL = "https://" + SUPABASE_URL
SUPABASE_KEY = _env("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY")
_auth_issues = []  # value-free reasons, safe to show on the login page
if not SUPABASE_URL:
    _auth_issues.append("SUPABASE_URL is not set")
elif not SUPABASE_URL.startswith("https://") or "your-project-ref" in SUPABASE_URL:
    _auth_issues.append("SUPABASE_URL is not an https://<ref>.supabase.co URL")
if not SUPABASE_KEY:
    _auth_issues.append("SUPABASE_PUBLISHABLE_KEY is not set")
elif len(SUPABASE_KEY) <= 20 or SUPABASE_KEY.startswith("paste_"):
    _auth_issues.append("SUPABASE_PUBLISHABLE_KEY is still a placeholder")
def _is_secret_key(k):
    # Never ship a Supabase service_role / secret key to the browser.
    if k.startswith("sb_secret_"):
        return True
    try:
        import base64, json as _j
        part = k.split(".")[1]
        return _j.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("role") == "service_role"
    except Exception:
        return False


if SUPABASE_KEY and _is_secret_key(SUPABASE_KEY):
    SUPABASE_KEY = ""
    _auth_issues.append("SUPABASE key is a SECRET/service_role key; use the publishable (anon) key")
AUTH_READY = not _auth_issues
if _sk != (os.getenv("FLASK_SECRET_KEY") or "").strip():
    print("WARNING: FLASK_SECRET_KEY missing/weak; using a random one (sessions reset on restart).")

SORTS = {"top": "upvotes DESC, views DESC", "new": "created_at DESC", "views": "views DESC"}


CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https:",
    "connect-src 'self' https://cdn.jsdelivr.net" + (f" {SUPABASE_URL}" if SUPABASE_URL.startswith("https://") else ""),
    "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'",
])


@app.after_request
def security_headers(resp):
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    h.setdefault("Content-Security-Policy", CSP)
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.path.startswith("/api/") or session.get("user"):
        h.setdefault("Cache-Control", "no-store")
    if os.getenv("VERCEL"):
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


# ---------------- rate limiting ----------------
# (bucket, max requests, window seconds). In-memory per server instance; the hard
# billing cap is AI_DAILY_LIMIT in ai.py plus the Google-side quota.
LIMITS = {
    "ai": [(8, 60), (40, 86400)],       # Gemini-backed routes
    "auth": [(10, 60)],                  # hits Supabase
    "write": [(30, 60), (300, 86400)],   # upvotes, requests, uploads
    "upload": [(5, 600)],
    "all": [(240, 60)],                  # everything else, basic flood guard
}
_hits = defaultdict(deque)
MAX_TRACKED = 20000


def client_ip():
    # Vercel sets x-real-ip / x-forwarded-for itself and overwrites client values.
    # Locally those headers are attacker-controlled, so trust only the socket address.
    if os.getenv("VERCEL"):
        return (request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For", "")
                .split(",")[0]).strip() or "?"
    return request.remote_addr or "?"


def rate_limited(bucket):
    now, ip = time.time(), client_ip()
    if len(_hits) > MAX_TRACKED:  # stop spoofed/rotating IPs from eating memory
        for k in [k for k, q in _hits.items() if not q or now - q[-1] > 86400]:
            del _hits[k]
        if len(_hits) > MAX_TRACKED:
            _hits.clear()
    q = _hits[(bucket, ip)]
    longest = max(w for _, w in LIMITS[bucket])
    while q and now - q[0] > longest:
        q.popleft()
    if any(sum(1 for t in q if now - t <= w) >= n for n, w in LIMITS[bucket]):
        return True
    q.append(now)
    return False


def bucket_for(path, method):
    if path.startswith("/api/ai/"):
        return "ai"
    if path.startswith("/api/auth/"):
        return "auth"
    if method == "POST" and path == "/add":
        return "upload"
    if method == "POST":
        return "write"
    return "all"


@app.before_request
def guard():
    if request.method == "POST":
        # CSRF / cross-site abuse: browsers always send Origin on cross-site POSTs.
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            return jsonify({"error": "Cross-site request blocked."}), 403
    b = bucket_for(request.path, request.method)
    if b != "all" and rate_limited("all"):
        return jsonify({"error": "Too many requests. Slow down a little."}), 429
    if rate_limited(b):
        msg = "Too many AI requests. Wait a minute and try again." if b == "ai" else "Too many requests. Slow down a little."
        if request.path.startswith("/api/"):
            return jsonify({"error": msg}), 429
        return msg, 429, {"Content-Type": "text/plain; charset=utf-8", "Retry-After": "60"}


def row_to_dict(r):
    d = dict(r)
    d["tags"] = [t.strip() for t in (d.get("tags") or "").split(",") if t.strip()]
    d["link"] = url_for("uploaded", name=d["file_path"]) if d.get("file_path") else d.get("url")
    return d


def stats():
    db = get_db()
    s = db.execute(
        "SELECT COUNT(*) AS resources, COUNT(DISTINCT subject) AS subjects,"
        " COUNT(DISTINCT uploader) AS contributors, COALESCE(SUM(views),0) AS views FROM resources"
    ).fetchone()
    db.close()
    return dict(s)


@app.context_processor
def globals_():
    return {"SUBJECTS": SUBJECTS, "TYPES": TYPES, "user": session.get("user"),
            "SUPABASE": {"url": SUPABASE_URL, "key": SUPABASE_KEY, "ready": AUTH_READY, "issues": _auth_issues}}


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if session.get("user"):
            return view(*a, **kw)
        if request.path.startswith("/api/"):
            return jsonify({"error": f"Sign in with your {ALLOWED_DOMAIN} email to do that.", "login": True}), 401
        return redirect(url_for("login", next=request.full_path.rstrip("?")))
    return wrapper


@app.route("/")
def landing():
    return render_template("landing.html", stats=stats())


@app.route("/login")
def login():
    nxt = request.args.get("next", "")
    safe = nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt and not any(ord(c) < 32 for c in nxt)
    return render_template("login.html", next=nxt[:300] if safe else "/dashboard")


@app.route("/api/auth/session", methods=["POST"])
def api_auth_session():
    token = str((request.get_json(silent=True) or {}).get("access_token", ""))[:4096]
    if not AUTH_READY or not token:
        return jsonify({"error": "Auth is not configured."}), 400
    try:
        r = http.get(f"{SUPABASE_URL}/auth/v1/user", timeout=10,
                     headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"})
        u = r.json() if r.ok else {}
    except Exception:
        return jsonify({"error": "Couldn't reach Supabase. Try again."}), 502
    email = (u.get("email") or "").lower()
    if not email.endswith(ALLOWED_DOMAIN):
        return jsonify({"error": f"Only {ALLOWED_DOMAIN} accounts can join Studit."}), 403
    if not u.get("email_confirmed_at"):
        return jsonify({"error": "Confirm your email first. Check your college inbox."}), 403
    meta = u.get("user_metadata") or {}
    name = (meta.get("full_name") or meta.get("name") or email.split("@")[0]).strip()[:50]
    if not u.get("id"):
        return jsonify({"error": "Couldn't verify your account. Try again."}), 502
    session.permanent = True
    session["user"] = {"id": str(u["id"]), "email": email, "name": name}
    return jsonify(session["user"])


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.pop("user", None)
    return jsonify({"ok": True})


@app.route("/dashboard")
@login_required
def dashboard():
    u = session["user"]
    db = get_db()
    mine = [row_to_dict(r) for r in db.execute(
        "SELECT * FROM resources WHERE uploader = ? ORDER BY created_at DESC", (u["name"],))]
    reqs = [dict(r) for r in db.execute(
        "SELECT * FROM requests WHERE requested_by = ? ORDER BY created_at DESC", (u["name"],))]
    db.close()
    impact = {"uploads": len(mine), "upvotes": sum(r["upvotes"] for r in mine), "views": sum(r["views"] for r in mine)}
    return render_template("dashboard.html", mine=mine, reqs=reqs, impact=impact, stats=stats())


@app.route("/browse")
def index():
    db = get_db()
    trending = [row_to_dict(r) for r in db.execute(
        "SELECT * FROM resources WHERE type IN ('PYQ','Notes') ORDER BY (upvotes*2 + views/20.0) DESC LIMIT 6")]
    db.close()
    return render_template("index.html", stats=stats(), trending=trending)


@app.route("/api/resources")
def api_resources():
    where, params = [], []
    q = request.args.get("q", "").strip()[:100]
    if q:
        where.append("(title LIKE ? OR description LIKE ? OR tags LIKE ? OR subject LIKE ?)")
        params += [f"%{q}%"] * 4
    for field in ("subject", "type"):
        v = request.args.get(field, "").strip()
        if v:
            where.append(f"{field} = ?")
            params.append(v)
    sem = request.args.get("semester", "").strip()
    if sem.isdigit():
        where.append("semester = ?")
        params.append(int(sem))
    ids = [i for i in request.args.get("ids", "").split(",") if i.isdigit()][:100]
    if "ids" in request.args:
        if not ids:
            return jsonify([])
        where.append(f"id IN ({','.join('?' * len(ids))})")
        params += [int(i) for i in ids]
    order = SORTS.get(request.args.get("sort", "top"), SORTS["top"])
    sql = "SELECT * FROM resources" + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY {order} LIMIT 100"
    db = get_db()
    rows = [row_to_dict(r) for r in db.execute(sql, params)]
    db.close()
    return jsonify(rows)


@app.route("/api/resources/<int:rid>/upvote", methods=["POST"])
def api_upvote(rid):
    voted = session.get("voted", [])
    db = get_db()
    if rid not in voted:  # one vote per browser session
        db.execute("UPDATE resources SET upvotes = upvotes + 1 WHERE id = ?", (rid,))
        db.commit()
        session["voted"] = (voted + [rid])[-300:]
    row = db.execute("SELECT upvotes FROM resources WHERE id = ?", (rid,)).fetchone()
    db.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify({"upvotes": row["upvotes"]})


@app.route("/api/stats")
def api_stats():
    return jsonify(stats())


@app.route("/resource/<int:rid>")
def resource(rid):
    db = get_db()
    seen = session.get("seen", [])
    if rid not in seen:  # count a view once per session
        db.execute("UPDATE resources SET views = views + 1 WHERE id = ?", (rid,))
        db.commit()
        session["seen"] = (seen + [rid])[-50:]  # keep the cookie well under 4 KB
    row = db.execute("SELECT * FROM resources WHERE id = ?", (rid,)).fetchone()
    if not row:
        db.close()
        abort(404)
    related = [row_to_dict(r) for r in db.execute(
        "SELECT * FROM resources WHERE subject = ? AND id != ? ORDER BY upvotes DESC LIMIT 4", (row["subject"], rid))]
    db.close()
    return render_template("resource.html", r=row_to_dict(row), related=related)


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "GET":
        return render_template("add.html", error=None, form=request.args)
    f = request.form
    title, subject, rtype = f.get("title", "").strip()[:200], f.get("subject", ""), f.get("type", "")
    url = f.get("url", "").strip()[:500]
    file = request.files.get("file")
    has_file = bool(file and file.filename)
    if not title or subject not in SUBJECTS or rtype not in TYPES:
        return render_template("add.html", error="Please fill title, subject and type.", form=f), 400
    if not url and not has_file:
        return render_template("add.html", error="Add a link or upload a PDF.", form=f), 400
    file_path = None
    if has_file:
        if not file.filename.lower().endswith(".pdf"):
            return render_template("add.html", error="Only PDF uploads are supported.", form=f), 400
        if file.stream.read(5) != b"%PDF-":
            return render_template("add.html", error="That file isn't a valid PDF.", form=f), 400
        file.stream.seek(0)
        file_path = f"{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)[-80:] or 'file.pdf'}"
        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"
        file.save(os.path.join(UPLOAD_DIR, file_path))
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    sem = f.get("semester", "")
    db = get_db()
    cur = db.execute(
        "INSERT INTO resources (title, description, subject, semester, type, url, file_path, tags, uploader)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (title, f.get("description", "").strip()[:2000], subject, int(sem) if sem.isdigit() else None, rtype,
         url or None, file_path, f.get("tags", "").strip()[:200], session["user"]["name"]),
    )
    db.commit()
    new_id = cur.lastrowid
    db.close()
    return redirect(url_for("resource", rid=new_id, added=1))


@app.route("/ask")
def ask():
    return render_template("ask.html", preset=request.args.get("subject", ""))


@app.route("/api/ai/plan", methods=["POST"])
def api_ai_plan():
    d = request.get_json(silent=True) or {}
    subject = d.get("subject") if d.get("subject") in SUBJECTS else SUBJECTS[0]
    days = str(d.get("days_left", 3))
    return jsonify(ai.study_plan(subject, int(days) if days.isdigit() else 3, str(d.get("weak_topics", ""))[:300]))


@app.route("/api/ai/tag", methods=["POST"])
def api_ai_tag():
    d = request.get_json(silent=True) or {}
    return jsonify(ai.auto_tag(str(d.get("title", ""))[:200], str(d.get("description", ""))[:1000]))


@app.route("/api/ai/insights/<int:rid>", methods=["POST"])
def api_ai_insights(rid):
    out = ai.insights(rid)
    return (jsonify(out), 200) if out else (jsonify({"error": "not found"}), 404)


@app.route("/requests")
def requests_board():
    db = get_db()
    rows = db.execute("SELECT * FROM requests ORDER BY fulfilled ASC, upvotes DESC, created_at DESC").fetchall()
    db.close()
    return render_template("requests.html", reqs=[dict(r) for r in rows])


@app.route("/api/requests", methods=["POST"])
@login_required
def api_request_create():
    d = request.get_json(silent=True) or {}
    subject, topic = d.get("subject"), str(d.get("topic", "")).strip()[:200]
    if subject not in SUBJECTS or len(topic) < 3:
        return jsonify({"error": "Pick a subject and describe what you need."}), 400
    db = get_db()
    cur = db.execute("INSERT INTO requests (subject, topic, requested_by, upvotes) VALUES (?,?,?,1)",
                     (subject, topic, session["user"]["name"]))
    db.commit()
    row = dict(db.execute("SELECT * FROM requests WHERE id = ?", (cur.lastrowid,)).fetchone())
    db.close()
    return jsonify(row), 201


@app.route("/api/requests/<int:qid>/<action>", methods=["POST"])
@login_required
def api_request_action(qid, action):
    if action not in ("upvote", "fulfil"):
        abort(404)
    key = f"req_{action}"
    done = session.get(key, [])
    if qid in done:
        db = get_db()
        row = db.execute("SELECT * FROM requests WHERE id = ?", (qid,)).fetchone()
        db.close()
        return jsonify(dict(row)) if row else (jsonify({"error": "not found"}), 404)
    session[key] = (done + [qid])[-300:]
    db = get_db()
    db.execute("UPDATE requests SET upvotes = upvotes + 1 WHERE id = ?" if action == "upvote"
               else "UPDATE requests SET fulfilled = 1 WHERE id = ?", (qid,))
    db.commit()
    row = db.execute("SELECT * FROM requests WHERE id = ?", (qid,)).fetchone()
    db.close()
    return jsonify(dict(row)) if row else (jsonify({"error": "not found"}), 404)


@app.route("/uploads/<path:name>")
def uploaded(name):
    if not name.lower().endswith(".pdf") or name != secure_filename(name):
        abort(404)
    resp = send_from_directory(UPLOAD_DIR, name, mimetype="application/pdf")
    # Uploaded files are untrusted: no scripts, no same-origin access.
    resp.headers["Content-Security-Policy"] = "sandbox; default-src 'none'; object-src 'none'"
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


# ---------------- cron ----------------
@app.route("/cron/daily")
def cron_daily():
    # Vercel Cron sends "Authorization: Bearer $CRON_SECRET"; without the secret set, nobody gets in.
    want = _env("CRON_SECRET")
    got = request.headers.get("Authorization", "")
    if len(want) < 16 or "change_me" in want or not secrets.compare_digest(got, f"Bearer {want}"):
        return jsonify({"error": "unauthorized"}), 401
    out = {}
    # Keep the sign-in project awake: free Supabase projects pause after 7 days with no DB requests.
    if AUTH_READY:
        try:
            r = http.post(f"{SUPABASE_URL}/rest/v1/rpc/ping", json={}, timeout=10,
                          headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
            out["supabase_auth"] = r.status_code
        except Exception as e:
            out["supabase_auth"] = type(e).__name__
    else:
        out["supabase_auth"] = "not configured"
    print("cron/daily:", out)
    return jsonify(out)


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "not found"}), 404
    return render_template("404.html"), 404


@app.errorhandler(413)
def too_large(e):
    return "File too large (max 20 MB).", 413, {"Content-Type": "text/plain; charset=utf-8"}


@app.errorhandler(500)
def server_error(e):
    # Never leak tracebacks / config to the client.
    if request.path.startswith("/api/"):
        return jsonify({"error": "Something went wrong."}), 500
    return "Something went wrong. Please try again.", 500, {"Content-Type": "text/plain; charset=utf-8"}


if __name__ == "__main__":
    app.run(debug=False, port=5000)
