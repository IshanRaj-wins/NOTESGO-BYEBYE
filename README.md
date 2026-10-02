# 📚 Studit

**One searchable hub for notes, previous-year papers and reference material, with an AI Exam Prep Assistant that turns "exam in 3 days" into a real plan.**

🌐 Live demo: https://study-recon.vercel.app

---

## 🧩 The problem
The night before an exam, students scramble. Notes are buried in WhatsApp groups, PYQs are in Google Drive links that expired last semester, and good reference material is spread across random sites. The students who find the right material aren't the smartest ones; they're the best connected.

## 💡 The solution
Studit puts it all in one place, where students **share, find, upvote and request** study resources, and an AI assistant builds exam plans from what's actually in the library.

- 🔍 **Search and filters**: by subject, semester and type (Notes · PYQ · Reference · Video · Lab Manual · Syllabus)
- ↕️ **Sort**: Top, Newest, Most viewed
- ➕ **Add resources**: paste a link or upload a PDF
- 👍 **Upvotes** push the best material to the top
- 🔥 **Trending before exams** strip
- 📝 **Request Board**: ask for missing material; others upvote or fulfil requests
- 🔖 **Bookmarks** saved in the browser
- 📲 **Share to WhatsApp** in one tap, since that's where students already are
- 👤 **Dashboard** (Supabase login) showing your uploads, upvotes and views

## ✨ AI features
All AI runs server-side in [`ai.py`](ai.py) through the Gemini API. The key never reaches the browser.

| Feature | What it does |
|---|---|
| **Exam Prep Assistant** (`/ask`) | Subject + days left + weak topics → a day-by-day plan that **links real resources from the database** |
| **✨ Auto-tag** (Add form) | Fills in subject, type and tags from the title and description |
| **✨ Key topics** (resource page) | A summary plus likely exam questions for that resource |

**Grounded, not hallucinated:** the model only sees resources that exist in the database and returns their IDs. The server drops any ID that doesn't exist and builds the links itself, so a plan can never contain an invented URL.

**Never crashes:** with no API key, an error, a timeout (20 s) or the daily budget used up, every feature falls back to a deterministic plan built from the database, labelled *offline*.

## 🗄️ Database
SQLite through Python's built-in `sqlite3` with raw SQL. It seeds itself on first run with around 30 resources across 6 subjects (DSA, DBMS, OS, Computer Networks, Engineering Maths, OOP with Java).

```
resources(id, title, description, subject, semester, type, url, file_path,
          tags, uploader, upvotes, views, created_at)
requests (id, subject, topic, requested_by, upvotes, fulfilled, created_at)
```

## 🌍 Impact: SDG 4, Quality Education
Targets **4.3** (equal access to education) and **4.a** (effective learning environments). Studit is free, needs no paid tools, and levels the field between students with good seniors or WhatsApp groups and students without them. The Request Board shows which material is missing and lets the community fill the gaps.

## 🛡️ Security
CSP headers, a same-origin check on every POST, per-IP rate limits, a daily AI budget with a kill switch (`AI_DISABLED=1`), sandboxed uploads, parameterised SQL, and refusal of Supabase service-role keys.

## 🚀 Run locally
```bash
pip install -r requirements.txt
cp .env.example .env        # optional: add GEMINI_API_KEY; the app works offline without it
python app.py               # → http://127.0.0.1:5000
```
Supabase login is optional; see [SUPABASE_SETUP.md](SUPABASE_SETUP.md).

## 🧭 Roadmap
- Move storage to **Supabase Postgres + Storage**. On Vercel, SQLite lives in `/tmp` per instance, so data isn't shared or permanent.
- Rate limits per logged-in user instead of per IP, so a whole college on one Wi-Fi doesn't share a single limit
- Full-text search (FTS5 / Postgres `tsvector`)

**Stack:** Python · Flask · SQLite · Jinja · Tailwind CSS (CDN) · vanilla JS · Gemini API · Supabase Auth
