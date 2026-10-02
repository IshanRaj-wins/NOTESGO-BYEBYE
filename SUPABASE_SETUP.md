# Supabase setup (5 minutes)

1. **Create a project** at https://supabase.com/dashboard.
2. **Keys → `.env`** (Project Settings → API Keys):
   ```
   SUPABASE_URL=https://<project-ref>.supabase.co
   SUPABASE_PUBLISHABLE_KEY=sb_publishable_...   # or the legacy anon key
   ```
   Never paste the `service_role` / secret key: it would be exposed to the browser.
3. **Google sign-in** (no emails/OTPs are sent, so nothing lands in spam):
   - Google Cloud Console → APIs & Services → **OAuth consent screen**: External, app name "Studit".
   - **Credentials → Create credentials → OAuth client ID** → Web application.
     Authorized redirect URI: `https://<project-ref>.supabase.co/auth/v1/callback`
   - Supabase **Auth → Providers → Google**: enable, paste the Client ID + Client Secret, save.
   - Optional: **Auth → Providers → Email** can be turned off.
4. **Auth → URL Configuration**: Site URL `http://127.0.0.1:5000`, add `http://127.0.0.1:5000/login`
   (and your deployed `https://<site>/login`) to Redirect URLs.
5. **Only allow @bmsce.ac.in** (server-side, cannot be bypassed from the browser). In the SQL Editor run:
   ```sql
   create or replace function public.hook_bmsce_only(event jsonb)
   returns jsonb language plpgsql as $$
   begin
     if lower(split_part(event->'user'->>'email', '@', 2)) = 'bmsce.ac.in' then
       return '{}'::jsonb;
     end if;
     return jsonb_build_object('error', jsonb_build_object(
       'message', 'Only @bmsce.ac.in emails can join Studit.', 'http_code', 403));
   end $$;

   grant execute on function public.hook_bmsce_only to supabase_auth_admin;
   revoke execute on function public.hook_bmsce_only from authenticated, anon, public;
   ```
   Then **Auth → Hooks → Before User Created** → Postgres function `public.hook_bmsce_only`.
6. Restart `python app.py`, open http://127.0.0.1:5000/login.

The domain is checked three times: in the browser (instant feedback), by the Supabase hook (blocks sign-up),
and by Flask when it verifies the access token (`/api/auth/session`) before setting the session cookie.

## Keep-alive ping (Phase 0)
Free projects pause after 7 days without database requests, and a paused project means nobody can sign in. The daily Vercel cron (`/cron/daily`) calls a tiny function so the database sees a request every day. Run this once in **SQL Editor**:

```sql
create or replace function public.ping() returns int language sql stable as 'select 1';
grant execute on function public.ping() to anon;
```

Then add `CRON_SECRET` (any random string of 16+ characters) to the Vercel env. Vercel sends it to the cron automatically.
