# Studit architecture: the ₹0 plan

This file covers **what** to build and **in what order**. Free-tier numbers were checked on 2026-09-26. Re-check anything marked ⚠ against the linked source before relying on it, and check the exact REST shapes against the provider docs when implementing.

This version comes from an adversarial review. It fixes 19 flaws in the first draft. The biggest were:
- sign-in and PDF downloads sharing one Supabase egress quota;
- a single `pending` status meaning two different things;
- a bypassable AI cap;
- fake seed data going into production;
- a missing `.vercelignore` update that would have broken production.

## Target architecture

```
                        ┌──────────── Vercel bom1 (Flask, stateless) ─────────────┐
 Browser ── pages/API ─▶│ app.py ── db.py ──────HTTP──▶ Turso aws-ap-south-1: data │
    │                   │        ── ai.py ──────HTTP──▶ Gemini (owner or user key) │
    │                   │        ── storage.py ─HTTP──▶ Supabase org B: Storage    │
    │                   │        ── /auth/v1/user ────▶ Supabase org A: sign-in    │
    │                   └──────────────────────────────────────────────────────────┘
    │  PUT PDF via signed URL (bypasses Vercel's 4.5 MB limit)
    └───────────────────▶ org B Storage: "quarantine" (private) ──checks──▶ "public"
                          downloads: /resource/<id>/download (counted) ─302─▶ public URL
 Vercel cron (daily) ─▶ /cron/daily: pings org A + org B + Turso, expires stale uploads,
                        prunes ai_cache, writes a rotating DB backup, sends a digest
 Telegram (optional): admin alerts, backup copy, PDF mirror
```

| Concern | Service | Free limit (no card) |
|---|---|---|
| Database | Turso over its HTTP API | 5 GB, 500M rows read and 10M written a month, 1-day PITR |
| Sign-in | Supabase **org A** (existing project) | 50k MAU, **pauses after 7 days with no API/DB requests** |
| PDF files | Supabase Storage in **org B** (new free org, Mumbai) | 1 GB, 50 MB per file, 5 GB egress + 5 GB cached egress **per org** a month, same 7-day pause |
| AI | Gemini API, free tier | ⚠ per *project*: Flash-Lite about 15 RPM and 500 to 1,000 RPD, Flash less |
| Hosting | Vercel Hobby | 4.5 MB request/response body, one pinned region, daily cron (production deploy only) |

Decisions already made. Don't re-litigate these without asking:
- **Turso, not Supabase Postgres, Neon or D1.** Turso keeps the same SQLite dialect and needs no driver. Supabase Postgres pauses and would tie data to auth. Neon means Postgres plus a driver. D1's REST API is rate-limited.
- **Supabase Storage in a separate org.** Egress quotas are counted per org. If downloads exceed the quota, Supabase restricts the org and answers 402, and sign-in must not go down with it. This uses the maintainer's second (last) free project. Rejected alternatives: R2 needs a card, B2's free egress is only 3× what is stored, Firebase Storage needs the paid Blaze plan, and Cloudinary blocks PDF delivery.
- **Telegram is not the primary file store.** Bots can't download files over 20 MB, the download URL contains the bot token, links expire after about 60 minutes, and a reported upload can get the channel banned.
- **A user's own Gemini key goes through `ai.py`,** never browser-to-Gemini, so resource-id validation still runs.
- **Drive/links are the normal way to share; PDF uploads are the extra.** 5 GB of egress is only about 1,700 downloads of 3 MB a month.
- **Upvotes require sign-in** (one per account). Browsing stays open.
- **Production seeds only the 2 real PDFs.** The 31 demo rows stay local-only.

## Invariants (every phase)
- **One region:** Vercel `bom1`, Turso `aws-ap-south-1` (⚠ confirm the location exists when creating the DB), Supabase org B in `ap-south-1`.
- **AI fails open, moderation fails closed.** If AI is down, the app shows offline results. If a check can't run, the upload goes to `pending`, never `live`.
- **`.vercelignore` is an allowlist.** Every new file or folder the app needs (`storage.py`, …) is added in the same change.
- **Never wipe Turso.** Schema changes go through `meta(schema_version)`: `CREATE TABLE IF NOT EXISTS`, and `ALTER TABLE ADD COLUMN` that ignores "duplicate column" errors, because several instances can cold-start at once.
- **Ownership is by `user_id`** (Supabase user id), never by display name.
- **Every free quota has a meter and a kill switch:**

| Quota | Meter | When it runs low |
|---|---|---|
| Turso rows read | indexes on every listing, 60 s per-instance cache for stats and the default listing | nothing to switch; keep queries indexed |
| Storage 1 GB | `SUM(size_bytes)` of live + pending | above 900 MB, `/api/uploads/sign` refuses and says "share a Drive link" |
| Egress 5+5 GB | estimated bytes counted by `/resource/<id>/download` | at 80%, admin alert; admin button flips `public` bucket to private (downloads stop until the 1st) |
| Gemini RPD | `counters` table (site-wide and per user) | offline plans; screening stops early so ~150 requests stay free |
| Floods | in-memory per-IP limiter (per instance) | 429 |

---

## Phase 0: Groundwork (no new services)

**Goal:** fix what is already wrong and stop sign-in from pausing, before anything new.

1. `app.py`: when `VERCEL` is set and `FLASK_SECRET_KEY` is missing or weak, raise at import. A random key per instance logs users out at random. Locally, keep the random fallback.
2. `/api/auth/session`: store `{"id": u["id"], "email", "name"}` in the session. For now, `/dashboard` keeps matching by name. After Phase 1 it uses `user_id`.
3. Set `app.permanent_session_lifetime` (30 days) and cap the `seen` list at 50 ids. The cookie limit is 4 KB, and an oversized cookie silently logs the user out.
4. `vercel.json`: `"regions": ["bom1"]` and `"crons": [{"path": "/cron/daily", "schedule": "0 3 * * *"}]`.
5. `/cron/daily` needs `Authorization: Bearer $CRON_SECRET`, otherwise it returns 401. For now it makes one request to org A that reaches Postgres. The maintainer runs this once in the org A SQL editor: `create or replace function public.ping() returns int language sql as 'select 1';`, then the cron calls `POST {SUPABASE_URL}/rest/v1/rpc/ping` with the publishable key. Log failures, but always return quickly.
6. Add `CRON_SECRET` and `ADMIN_EMAIL` to `.env.example`.

Done when: [x] the app starts locally with no env vars, [ ] on a Vercel preview, a missing `FLASK_SECRET_KEY` fails loudly (verified locally with `VERCEL=1`; not yet on a real preview), [x] `/cron/daily` without the secret returns 401 and with it returns 200, [x] a signed-in session contains `id`, [x] the done criteria pass (server starts, `/` returns 200, feature works end to end, no JS console errors) (locally). **Deploying this to production needs the maintainer's sign-off.**

## Phase 1: Persistent database on Turso

**Goal:** data survives cold starts and redeploys. Locally, nothing changes.

1. In `db.py`, add a Turso HTTP client used when `TURSO_URL` and `TURSO_TOKEN` are set. Otherwise keep using `sqlite3` exactly as now. See the Turso HTTP API docs for the request shapes.
   - Convert `libsql://…` to `https://…`, then `POST {url}/v2/pipeline` with `Authorization: Bearer <token>` through one **module-level `requests.Session`**. Keep-alive saves a TLS handshake on every query.
   - Expose the surface `app.py` already uses: `get_db().execute(sql, params)` with `fetchone()`, `fetchall()`, iteration and `lastrowid`, plus a no-op `commit()` and `close()`. Rows support `row["col"]` and `row[0]`. Add `executemany`-style batching, so a page's queries can go in one pipeline where that is easy.
   - Use a 10 s timeout and raise a clear error on HTTP failure. Page routes render the friendly 500 and never leak SQL.
2. Migrations: add a `meta(key, value)` table holding `schema_version`. `init_db()` applies the missing steps in order and is idempotent. It checks for seeding with `SELECT 1 FROM resources LIMIT 1`, never `COUNT(*)`.
3. Seed: when `TURSO_URL` is set, seed **only the 2 real PDFs** (#32, #33 via `seed_files/`). Locally, keep all 31 demo rows.
4. Indexes: `resources(status, subject, upvotes)`, `resources(created_at)`, `resources(user_id)`, `requests(fulfilled, upvotes)`. Add a 60 s per-instance cache for `stats()` and for the unfiltered `/api/resources` listing.
5. New tables:
   - `votes(user_id, resource_id, PRIMARY KEY(user_id, resource_id))` and `request_votes(user_id, request_id, PK)`. Upvoting needs sign-in (the button sends the user to `/login?next=…`). Voting is `INSERT OR IGNORE`, then `UPDATE … upvotes = upvotes + changes()`. The cookie vote lists are removed.
   - `users(id, email, name, banned INT DEFAULT 0, created_at)`, upserted on sign-in.
   - `ai_cache(key PRIMARY KEY, value, created_at)` and `counters(key PRIMARY KEY, value, day)`. The AI cache and daily counter move from memory to these tables. The in-memory per-minute IP limiter stays as a flood guard.
   - `resources` gets `user_id TEXT`. `/dashboard` and ownership checks switch to it. Old rows keep `user_id` NULL.
6. There is no migration script: production data lives in `/tmp` today, so there is nothing to move.

Done when: [ ] the app runs locally with no env vars, [ ] with the Turso vars, a resource added survives a restart and redeploy, [ ] one account can upvote a resource only once, even from a second browser, [ ] Turso contains only the 2 real resources after first boot, [ ] two parallel cold starts don't error on migration, [ ] the done criteria pass (server starts, `/` returns 200, feature works end to end, no JS console errors).

## Phase 2: PDF storage, checks and moderation (ships as one piece)

**Goal:** fix uploads over 4.5 MB (currently broken on Vercel), stop storing PDFs on ephemeral disk, and make sure nothing goes public unchecked.

One-time setup:
- Create a **new free Supabase organization** and a project in it, region `ap-south-1`.
- Create three buckets: `quarantine` (private), `public` (public) and `backups` (private). `quarantine` and `public` have a 15 MB limit and MIME type `application/pdf`.
- Put `STORAGE_URL` and `STORAGE_SERVICE_KEY` in the Vercel env, server only.
- `storage.py` is the only place that reads the key. The existing refusal of a `service_role` key in the browser-facing config stays.

Schema additions to `resources`: `status TEXT DEFAULT 'live'`, `storage_path`, `size_bytes INTEGER`, `sha256`, `report_count INTEGER DEFAULT 0` and `reject_reason`. Seed rows stay `live`. New tables:
- `banned_hashes(sha256 PRIMARY KEY)`
- `reports(resource_id, user_id, reason, created_at, PRIMARY KEY(resource_id, user_id))`
- `egress(month PRIMARY KEY, bytes)`

**Status flow:** `uploading → checking → pending | live | rejected`, plus `hidden` from reports.
- `uploading` means a row exists but the file may not be there yet. It never counts as "pending review".
- Rows stuck in `uploading` for more than 2 hours are expired by the cron, and their objects are deleted.

Steps:
1. New `storage.py` (plain `requests`, service key) wraps the Storage REST API. It can create a signed upload URL (**upsert off**), get an object's metadata and size, download, move/copy, delete, list, and build the public URL. Add it to `.vercelignore`.
2. `POST /api/uploads/sign` (login required, not banned). Body: title, subject, semester, type, size.
   - Quotas are enforced **atomically** in the insert: `INSERT … SELECT … WHERE (SELECT COUNT(*) …) < N AND …`, with limits from the table below.
   - It also refuses when site storage is over 900 MB.
   - It inserts an `uploading` row and returns `{upload_url, resource_id}`. The path is `<user_id>/<random>.pdf` in `quarantine`.
3. `/add` page JS PUTs the file straight to the signed URL, with a progress bar, then calls `POST /api/uploads/<id>/check`. Add the org B origin to CSP `connect-src`.
4. `POST /api/uploads/<id>/check` (uploader only):
   1. Claim the row atomically with `UPDATE resources SET status='checking' WHERE id=? AND user_id=? AND status='uploading'`. If no row changed, stop, since this makes a double call harmless.
   2. Read the **real** object size from storage. Recheck the size limit and the quota against it, and save it to `size_bytes`.
   3. Download the file. Check the `%PDF` magic bytes, compute SHA-256, and reject if it's in `banned_hashes` or duplicates a live resource (link to that one).
   4. If it passes, set `pending` (manual review). Phase 3 adds AI screening at this point.
5. `/resource/<id>/download` adds `size_bytes` to `egress[month]`, then 302s to the public URL. It's an estimate (the public URL can be shared), which is why the kill switch exists. `/uploads/<name>` keeps working for seed files and local dev.
6. `/admin` (only `ADMIN_EMAIL`): pending, hidden and reported items with Preview (a short-lived signed URL), Approve (move to `public`, set `live`), Reject (delete, store the hash, record a reason) and Ban uploader. It also shows the storage and egress meters and the "downloads off" kill switch.
7. `POST /api/resources/<id>/report` (login required, one per user per resource). Reasons are inappropriate, **copyright**, wrong subject, spam and broken. At 3 distinct reports the resource is set to `hidden`.
8. Bans are checked on **every** write route: uploads, votes, requests and reports.
9. All public listings (`/browse`, `/api/resources`, stats, related, trending and the AI prompts) filter on `status='live'`. Uploaders see their own pending or rejected items, with the reason, on `/dashboard`.
10. A `/terms` page: the uploader confirms they have the right to share the file, no textbooks or paid material, a takedown email (`ADMIN_EMAIL`), and that AI features are for users 18 and over. The upload form links to it.
11. Cron additions:
    - expire stale `uploading` rows;
    - list one object in org B, which keeps it awake;
    - write a rotating `backups/backup-<weekday>.json` dump of every table (7 copies);
    - if `TELEGRAM_*` is set, send a digest: pending count, and storage and egress percent.
12. Locally without the storage vars, keep the current multipart upload into `uploads/` and set the status to `live`.

| Quota | Value |
|---|---|
| Uploads per user per day | 5 (users with fewer than 3 live uploads: 2) |
| `uploading` + `pending` at once per user | 3 |
| Max file size | 15 MB (also enforced by the bucket) |
| Total stored per user | 150 MB |
| Site-wide uploads per day | 100 |
| Site-wide stored | 900 MB |

Done when: [ ] a 10 MB PDF uploads on Vercel and lands in `pending`, [ ] the admin approves it and it downloads, [ ] declaring 1 KB and uploading 15 MB is caught at `/check`, [ ] calling `/check` twice is harmless, [ ] the 6th upload of a day is refused with a clear message, [ ] non-PDFs are refused, [ ] 3 reports hide a resource, [ ] a banned user can't upload or vote, [ ] a rejected file's re-upload is refused, [ ] an abandoned upload is cleaned up by the cron, [ ] local dev upload still works.

## Phase 3: AI screening

**Goal:** normal notes go live without waiting for the admin, and bad files are caught automatically.

1. `ai.screen_pdf(pdf_bytes, title, subject)` uses Flash-Lite (`GEMINI_SCREEN_MODEL`) with the PDF as `inline_data`. **Screening only** gets a 90 s timeout. It asks for JSON: `{"nsfw": bool, "is_study_material": bool, "matches_subject": bool, "matches_title": bool, "confidence": 0-1, "reason": str}`.
2. Files **over 10 MB skip the AI** and go to `pending`, because base64 of a 15 MB file is about 20 MB, right at the inline limit.
3. The decision:
   - `nsfw`, or a safety block (`promptFeedback.blockReason` or a `SAFETY` finish reason), means **rejected**: delete the file and store the hash.
   - Not study material, a subject or title mismatch, or confidence below 0.6 means **pending**.
   - Otherwise **live** (move to `public`).
4. Offline, errors, or fewer than about 150 of the day's requests left all mean `pending`, **never** `live`. Tag the result `"mode": "offline"`.
5. Trust: users with 5 or more live uploads and no upheld reports skip the "low confidence → pending" rule. The NSFW check always runs.
6. Optional Telegram alert for each new `pending` or auto-`hidden` item.

Done when: [ ] a normal notes PDF goes live, [ ] an off-topic PDF lands in pending, [ ] with `AI_DISABLED=1` uploads go to pending, [ ] a 12 MB PDF goes to pending without a Gemini call.

## Phase 4: Make Gemini last for 300 to 400 users

Background: a free-tier key has no billing, so it **can't charge anything**. When the quota runs out it returns 429 and the offline fallback runs. Limits are per Google Cloud project, not per key.

1. **Shared plan cache:** cache `study_plan` results in `ai_cache`, keyed by `sha256(subject | days | sorted lowercased weak topics | model)`. A cache hit costs no request.
2. **Per-user cap on the owner key:** 3 fresh AI plans per signed-in user per day (`counters`). Anonymous users get cached or offline plans only. Show "Daily AI limit reached, showing offline plan. Add your own free Gemini key for unlimited plans."
3. Use Flash-Lite for `auto_tag` and `insights`. Keep `GEMINI_MODEL` for `study_plan`.
4. **Bring your own key:**
   - A "Use my own Gemini key (optional)" field on `/ask` and `/dashboard`, linking to aistudio.google.com/apikey. Store it in `localStorage` only (`studit_gemini_key`; don't rename the existing bookmark keys). Add Test and Remove buttons.
   - JS sends it as the `X-Gemini-Key` header on the three `/api/ai/*` routes and nowhere else.
   - `app.py` passes it to `ai.py` as a parameter. **Never** log it, cache-key it, store it or echo it in errors. Send it outbound in the `x-goog-api-key` header, not `?key=`.
   - A valid user key skips the per-user cap. If the user key returns 400/401/403, return `"invalid_key"` and fall back to the owner key **still subject to the per-user cap**, then to offline. Otherwise a junk key would give unlimited owner-key plans.
   - Note by the field: "Use a key from a Google Cloud project **without billing** so it can never charge you. Free Gemini keys: Google may use prompts to improve its products. Only subject names and topics are sent."
5. CSP hardening: narrow `cdn.jsdelivr.net` to the exact package paths used, so an injected script is less likely to be able to read the stored key.

Done when: [ ] the same plan request twice makes one Gemini call, [ ] the 4th fresh plan of the day on the owner key shows the offline plan and message, [ ] a user key works past the cap, [ ] a junk key shows "invalid key" and doesn't get past the cap, [ ] a search of the code and logs finds no stored user key, [ ] 0 CSP errors.

## Phase 5 (optional): Telegram

Env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (a private channel or chat). This must never block or fail a user-facing flow.
1. After a resource goes live, send the PDF with `sendDocument` (≤50 MB) and store the returned `file_id` in `resources.tg_file_id`. It's used only for restoring files if org B data is lost, and never served to users.
2. The daily cron also sends that day's DB backup JSON, so there is an off-Supabase copy.
3. If the cron itself fails, it sends an alert. A cron that dies silently for 7 days means sign-in pauses.

Done when: [ ] a live upload appears in the channel, [ ] the daily backup file arrives, [ ] a forced cron error sends an alert.

---

## Sources
- Gemini rate limits (per project; see AI Studio for your numbers): https://ai.google.dev/gemini-api/docs/rate-limits
- Gemini free-tier numbers after the December 2025 cut (third-party): https://www.aifreeapi.com/en/posts/gemini-api-free-tier-rate-limits
- Gemini API terms (unpaid data use, 18+): https://ai.google.dev/gemini-api/terms
- Supabase pricing and free limits: https://supabase.com/pricing
- Supabase egress is per organization: https://supabase.com/docs/guides/platform/manage-your-usage/egress
- Supabase quota restrictions and grace period: https://supabase.com/docs/guides/platform/billing-faq
- Supabase signed upload URLs: https://supabase.com/docs/reference/python/storage-from-createsigneduploadurl
- Turso pricing: https://turso.tech/pricing · HTTP API: https://docs.turso.tech/sdk/http/reference
- Vercel function regions (Hobby: one region): https://vercel.com/docs/functions/configuring-functions/region
- Vercel function limits: https://vercel.com/docs/functions/limitations · Cron jobs: https://vercel.com/docs/cron-jobs
- Cloudflare R2 needs a payment method (why it's excluded): https://community.cloudflare.com/t/why-using-r2-free-tier-involves-giving-card-info/945179
- Telegram bot file limits: https://grammy.dev/guide/files
