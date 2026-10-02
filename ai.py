"""All AI calls (Gemini REST) + deterministic offline fallbacks built from DB data."""
import json
import os
import re
import threading
import time

import requests

from db import SUBJECTS, TYPES, get_db

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MODELS = list(dict.fromkeys([MODEL, "gemini-flash-latest"]))  # backup model if the primary is overloaded
API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
_insight_cache = {}
_cache = {}  # identical prompts are answered from memory, not billed again
CACHE_MAX = 500

# Billing guard: hard cap on real Gemini HTTP calls per server instance per UTC day.
# Past it, every AI feature silently switches to the offline fallback.
DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "200") or 0)
_usage = {"day": "", "calls": 0}
_lock = threading.Lock()


def _key():
    if os.getenv("AI_DISABLED", "").strip().lower() in ("1", "true", "yes"):
        return ""  # kill switch: set AI_DISABLED=1 to stop all Gemini calls
    k = os.getenv("GEMINI_API_KEY", "").strip()
    return "" if not k or "your" in k.lower() or "placeholder" in k.lower() else k


def _take_budget():
    with _lock:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if _usage["day"] != today:
            _usage.update(day=today, calls=0)
        if _usage["calls"] >= DAILY_LIMIT:
            return False
        _usage["calls"] += 1
        return True


def ask_json(prompt, max_tokens=1024):
    """Returns parsed JSON, or None on any failure (caller uses fallback)."""
    key = _key()
    if not key:
        return None
    if prompt in _cache:
        return _cache[prompt]
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json",
                                 "maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        r = None
        for model in MODELS:  # on transient 429/5xx, retry once with the backup model
            if not _take_budget():
                print("AI daily limit reached; using offline mode")
                return None
            r = requests.post(API.format(model), headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                              json=body, timeout=20)
            if r.status_code not in (404, 429, 500, 502, 503, 504):
                break
            time.sleep(0.5)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
        data = json.loads(text)
        if len(_cache) >= CACHE_MAX:
            _cache.clear()
        _cache[prompt] = data
        return data
    except Exception as e:
        # requests error text can include the URL; the key is only in a header, never logged
        print("AI error:", type(e).__name__, str(e)[:200].replace(key, "***"))
        return None


def _str_list(v, n):
    return [str(x).strip() for x in v if str(x).strip()][:n] if isinstance(v, list) else []


def _link(r):
    return f"/uploads/{r['file_path']}" if r["file_path"] else r["url"]


# ---------------- Feature 1: Exam Prep plan ----------------
def study_plan(subject, days, weak):
    days = max(1, min(14, int(days or 3)))
    db = get_db()
    rows = db.execute(
        "SELECT id, title, type, tags, url, file_path, upvotes FROM resources WHERE subject = ? ORDER BY upvotes DESC LIMIT 15",
        (subject,)).fetchall()
    db.close()
    by_id = {r["id"]: {"id": r["id"], "title": r["title"], "type": r["type"], "link": _link(r)} for r in rows}
    catalog = [{"id": r["id"], "title": r["title"], "type": r["type"], "tags": r["tags"]} for r in rows]

    prompt = f"""You are an expert, encouraging exam study coach for engineering students.
Subject: {subject}. Days left until the exam: {days}. Student's weak topics: {weak or "not specified"}.
Use ONLY these resources from our library (JSON): {json.dumps(catalog)}
Build a realistic day-by-day plan with exactly {days} days. Prioritise weak topics early, keep the final day for
previous-year papers (PYQ) and revision. Each day cites 1-3 resource ids from the list above.
Return JSON only: {{"summary": str, "days": [{{"day": int, "focus": str, "tasks": [str], "resource_ids": [int]}}], "tips": [str]}}
Tasks are concrete and short (max 4 per day). 3-4 tips."""
    data = ask_json(prompt, 2048) if rows else None
    try:
        if data and isinstance(data.get("days"), list) and data["days"]:
            out_days = []
            for i, d in enumerate(data["days"][:days], 1):
                ids = [int(x) for x in d.get("resource_ids", []) if str(x).isdigit() and int(x) in by_id]
                out_days.append({"day": i, "focus": str(d.get("focus", f"Day {i}")),
                                 "tasks": _str_list(d.get("tasks"), 5),
                                 "resources": [by_id[x] for x in dict.fromkeys(ids)]})
            return {"mode": "ai", "subject": subject, "summary": str(data.get("summary", "")),
                    "days": out_days, "tips": _str_list(data.get("tips"), 5)}
    except Exception as e:
        print("AI plan parse error:", e)
    return _plan_fallback(subject, days, weak, list(by_id.values()))


def _plan_fallback(subject, days, weak, res):
    weak_list = [w.strip() for w in re.split(r"[,;\n]", weak or "") if w.strip()]
    pyqs = [r for r in res if r["type"] == "PYQ"]
    study = [r for r in res if r["type"] not in ("PYQ", "Syllabus")] or res
    out = []
    for i in range(1, days + 1):
        last = i == days and days > 1
        if last:
            focus, picks = "Previous-year papers & full revision", (pyqs or res)[:2]
            tasks = ["Solve one PYQ in exam conditions (timed)", "Mark questions that repeat across years",
                     "Revise formulas / definitions from your notes", "Sleep 7+ hours, no new topics tonight"]
        else:
            topic = weak_list[(i - 1) % len(weak_list)] if weak_list else None
            focus = f"Strengthen: {topic}" if topic else f"Core concepts, part {i}"
            picks = [study[(i - 1 + k) % len(study)] for k in range(min(2, len(study)))] if study else []
            tasks = [f"Study {topic} from the linked resources" if topic else "Go through the top-rated notes below",
                     "Write a one-page summary in your own words", "Solve 5 practice questions on today's topic",
                     "Quick 15-min recap of the previous day"]
        out.append({"day": i, "focus": focus, "tasks": tasks, "resources": list({r["id"]: r for r in picks}.values())})
    return {"mode": "offline", "subject": subject,
            "summary": f"A {days}-day {subject} plan built from the most upvoted resources on Studit"
                       + (f", starting with your weak areas ({', '.join(weak_list)})." if weak_list else "."),
            "days": out,
            "tips": ["Use active recall: close the notes and write what you remember.",
                     "PYQs reveal the pattern: topics that repeat are worth the most marks.",
                     "Study in 50-minute blocks with 10-minute breaks.",
                     "Teach a friend one topic a day; gaps show up instantly."]}


# ---------------- Feature 2: Auto-tag ----------------
KEYWORDS = {
    "DSA": ["dsa", "data structure", "algorithm", "linked list", "stack", "queue", "tree", "graph", "sorting", "heap", "hashing", "recursion", "dynamic programming"],
    "DBMS": ["dbms", "database", "sql", "normalization", "er diagram", "transaction", "relational", "query", "mysql", "bcnf"],
    "Operating Systems": ["operating system", " os ", "os ", "process", "scheduling", "deadlock", "paging", "memory management", "semaphore", "thread", "kernel"],
    "Computer Networks": ["network", " cn ", "cn ", "tcp", "osi", "subnet", "routing", "ip address", "protocol", "socket", "dns", "http"],
    "Engineering Maths": ["math", "laplace", "fourier", "integral", "differential", "matrix", "probability", "statistics", "calculus", "pde", "numerical"],
    "OOP with Java": ["java", "oop", "object oriented", "inheritance", "polymorphism", "class", "interface", "exception", "jdbc", "collections"],
}
TYPE_WORDS = [("PYQ", ["pyq", "question paper", "previous year", "past paper", "solved paper"]),
              ("Lab Manual", ["lab", "practical", "experiment"]),
              ("Video", ["video", "youtube", "playlist", "lecture series"]),
              ("Syllabus", ["syllabus", "curriculum", "exam pattern"]),
              ("Reference", ["book", "reference", "cheat sheet", "textbook", "guide"]),
              ("Notes", ["notes", "handwritten", "summary", "revision"])]
STOP = set("the a an and or of for to in on with by from unit notes pdf part full all my is this".split())


def auto_tag(title, description):
    prompt = f"""Classify this study resource for an engineering-student library.
Title: {title}
Description: {description}
subject must be exactly one of {SUBJECTS}. type must be exactly one of {TYPES}.
semester is an integer 1-8 (typical Indian B.Tech CSE curriculum). tags: 3-6 short lowercase topic keywords.
Return JSON only: {{"subject": str, "type": str, "semester": int, "tags": [str]}}"""
    data = ask_json(prompt, 256)
    if isinstance(data, dict) and data.get("subject") in SUBJECTS and data.get("type") in TYPES:
        sem = data.get("semester")
        return {"mode": "ai", "subject": data["subject"], "type": data["type"],
                "semester": int(sem) if str(sem).isdigit() and 1 <= int(sem) <= 8 else None,
                "tags": [t.lower() for t in _str_list(data.get("tags"), 6)]}
    return _tag_fallback(title, description)


def _tag_fallback(title, description):
    text = f" {title} {description} ".lower()
    scores = {s: sum(text.count(k) for k in kws) for s, kws in KEYWORDS.items()}
    subject = max(scores, key=scores.get) if max(scores.values()) else None
    rtype = next((t for t, words in TYPE_WORDS if any(w in text for w in words)), "Notes")
    tags = [k.strip() for k in KEYWORDS.get(subject, []) if k.strip() in text and len(k.strip()) > 2][:4]
    if rtype == "PYQ":
        tags.insert(0, "pyq")
    tags += [y for y in re.findall(r"\b20[12]\d\b", text)][:1]
    if len(tags) < 3:
        words = [w for w in re.findall(r"[a-z]{4,}", title.lower()) if w not in STOP]
        tags += [w for w in words if w not in tags][: 3 - len(tags)]
    sem = {"DSA": 3, "DBMS": 4, "Operating Systems": 5, "Computer Networks": 5, "Engineering Maths": 3, "OOP with Java": 3}.get(subject)
    return {"mode": "offline", "subject": subject, "type": rtype, "semester": sem, "tags": list(dict.fromkeys(tags))[:6]}


# ---------------- Feature 3: Key topics ----------------
def insights(rid):
    if rid in _insight_cache:
        return _insight_cache[rid]
    db = get_db()
    r = db.execute("SELECT * FROM resources WHERE id = ?", (rid,)).fetchone()
    db.close()
    if not r:
        return None
    prompt = f"""You are a university exam expert. A student is studying this resource:
Title: {r['title']}
Subject: {r['subject']} (semester {r['semester']}), type: {r['type']}
Description: {r['description']}
Tags: {r['tags']}
Return JSON only: {{"summary": str (2-3 sentences on what it covers and how to use it for exam prep),
"key_topics": [5-7 short topic names], "likely_questions": [5 realistic university exam questions, with marks like "(10 marks)"]}}"""
    data = ask_json(prompt)
    if isinstance(data, dict) and data.get("summary") and isinstance(data.get("key_topics"), list):
        out = {"mode": "ai", "summary": str(data["summary"]), "key_topics": _str_list(data["key_topics"], 8),
               "likely_questions": _str_list(data.get("likely_questions"), 6)}
    else:
        tags = [t.strip() for t in (r["tags"] or "").split(",") if t.strip() and t.strip() not in ("pyq", "lab", "syllabus")]
        tags = [t for t in tags if not t.isdigit()] or [r["subject"]]
        templates = ["Explain {} with a suitable example. (10 marks)", "What are the advantages and limitations of {}? (5 marks)",
                     "Write short notes on {}. (5 marks)", "Compare {} with a related concept using a table. (8 marks)",
                     "Solve a numerical / write a program demonstrating {}. (10 marks)"]
        out = {"mode": "offline",
               "summary": f"This {r['type'].lower()} covers {', '.join(tags[:4])} for {r['subject']}. "
                          f"Skim it once, then revisit the key topics below and practise the likely questions.",
               "key_topics": [t.title() for t in tags[:7]],
               "likely_questions": [templates[i].format(tags[i % len(tags)]) for i in range(5)]}
    if out["mode"] == "ai":
        _insight_cache[rid] = out
    return out
