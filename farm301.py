#!/usr/bin/env python3
"""farm301 v2: crusoe-воркер GitHub Actions. Токены тянет из публичного raw-файла
(домашний tokenfarm решает turnstile). Весь флоу с Azure IP — вне 1015-лимитов."""
import base64, json, os, random, re, string, subprocess, sys, time
import requests

CONSOLE = "https://console.crusoecloud.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
FEED = os.environ.get("FEED", "https://raw.githubusercontent.com/ronnikols/crusoe-1015-probe/master/tokens.txt")
DUMP = os.environ.get("DUMP", "ronnikols/crusoe-farm-dump")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
WORKER = os.environ.get("WORKER", "w0")
MINUTES = int(os.environ.get("MINUTES", "55"))
MAILS = [("tmpl", "https://tempmail.plus"), ("mercure", "https://api.mail.tm")]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def rnd(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def poll_token():
    """токены из репо через gh api (GITHUB_TOKEN раннера, без CDN-кэша)"""
    import subprocess
    import base64 as b64
    for _ in range(10):
        try:
            out = subprocess.run(["gh", "api", "repos/ronnikols/crusoe-1015-probe/contents/tokens.txt", "--jq", ".content"], capture_output=True, text=True, timeout=20)
            if out.returncode == 0 and out.stdout.strip():
                toks = [t for t in b64.b64decode(out.stdout).decode().split() if len(t) > 40]
                if toks:
                    return random.choice(toks)
        except Exception:
            pass
        time.sleep(6)
    return None


def mail_create():
    for attempt in range(6):
        kind, base = MAILS[attempt % len(MAILS)]
        try:
            if kind == "tmpl":
                return rnd(12) + "@mailto.plus", "", "", base, kind
            dom = DOM_CACHE.get(base)
            if not dom:
                doms = requests.get(f"{base}/domains", timeout=15).json()["hydra:member"]
                dom = next(d["domain"] for d in doms if d.get("isActive"))
                DOM_CACHE[base] = dom
            login, pw = rnd(8), rnd(12) + "Aa1!"
            r = requests.post(f"{base}/accounts", json={"address": f"{login}@{dom}", "password": pw}, timeout=15)
            if r.status_code < 400:
                tok = requests.post(f"{base}/token", json={"address": f"{login}@{dom}", "password": pw}, timeout=15).json()["token"]
                return f"{login}@{dom}", pw, tok, base, kind
        except Exception:
            time.sleep(1.5)
    return None, None, None, None, None


DOM_CACHE = {}


def mail_code(mtok, base, kind, timeout=170):
    t0 = time.time()
    seen = set()
    while time.time() - t0 < timeout:
        try:
            if kind == "tmpl":
                j = requests.get(f"{base}/api/mails/", params={"email": mtok, "first_id": 0, "limit": 20}, timeout=15).json()
                for m in j.get("mail_list", []):
                    if m.get("mail_id") in seen:
                        continue
                    body = m.get("text") or m.get("html") or ""
                    mm = re.search(r"\b(\d{6})\b", body)
                    if not mm and "crusoe" in str(m.get("from_mail", "")).lower():
                        full = requests.get(f"{base}/api/mails/{m.get('mail_id')}", params={"email": mtok, "first_id": 0}, timeout=15).json()
                        mm = re.search(r"\b(\d{6})\b", full.get("text") or full.get("html") or "")
                    if mm:
                        return mm.group(1)
                    seen.add(m.get("mail_id"))
            elif kind == "mercure":
                msgs = requests.get(f"{base}/messages", headers={"Authorization": f"Bearer {mtok}"}, timeout=15).json().get("hydra:member", [])
                for m in msgs:
                    if m["id"] in seen:
                        continue
                    full = requests.get(f"{base}/messages/{m['id']}", headers={"Authorization": f"Bearer {mtok}"}, timeout=15).json()
                    html = full.get("html") or []
                    body = (html[0] if isinstance(html, list) and html else "") or full.get("text") or ""
                    mm = re.search(r"\b(\d{6})\b", body)
                    if mm:
                        return mm.group(1)
                    seen.add(m["id"])
        except Exception:
            pass
        time.sleep(4)
    return None


def api_headers(csrf=None):
    h = {"Accept": "application/json", "User-Agent": UA, "Origin": CONSOLE, "Referer": CONSOLE + "/"}
    if csrf:
        h["X-CSRF-Token"] = csrf
    return h


def nodes_csrf(j):
    try:
        for n in j.get("ui", {}).get("nodes", []):
            if n.get("attributes", {}).get("name") == "csrf_token":
                return n["attributes"]["value"]
    except Exception:
        pass
    return None


def attempt(idx, s):
    tok = poll_token()
    if not tok:
        return "no_token"
    email, mpw, mtok, mbase, mkind = mail_create()
    if not email:
        return "mail"
    pw = "Crs!" + rnd(12) + "aA1"
    name = random.choice(["James", "Maria", "Linda", "Daniel", "Sofia"]) + " " + random.choice(["Walker", "Reyes", "Novak", "Bennett"])
    company = random.choice(["North", "Blue", "Summit", "Iron"]) + random.choice(["line", "stone", "works"]) + " " + random.choice(["Systems", "Digital", "Labs"])
    r = s.get(f"{CONSOLE}/api/v1", headers=api_headers(), timeout=40)
    if r.status_code != 200 or not r.headers.get("x-csrf-token"):
        return f"csrf{r.status_code}"
    csrf = r.headers["x-csrf-token"]
    body = {"email": email, "company": company, "source": "portal", "referral": "", "use_case": "cloud", "cf-turnstile-response": tok}
    r = s.post(f"{CONSOLE}/api/v1/organizations/prospects", json=body, headers=api_headers(csrf), timeout=40)
    if r.status_code == 403:  # токен скомуниздил другой воркер — новый
        tok2 = poll_token()
        if tok2:
            r = s.post(f"{CONSOLE}/api/v1/organizations/prospects", json={**body, "cf-turnstile-response": tok2}, headers=api_headers(csrf), timeout=40)
    if r.status_code == 429:
        return "STORM"  # окно CF закрыто — бэкофф в main, токен не жечь дальше
    if r.status_code != 200:
        return f"prospects{r.status_code}"
    r = s.get(f"{CONSOLE}/auth/self-service/registration/browser", headers=api_headers(), timeout=40)
    reg_flow = r.json().get("id")
    reg_csrf = nodes_csrf(r.json())
    if not reg_flow:
        return "regflow"
    r = s.post(f"{CONSOLE}/auth/self-service/registration?flow={reg_flow}",
               json={"csrf_token": reg_csrf, "method": "password", "password": pw, "traits": {"email": email, "fullname": name}, "signup_token": ""},
               headers=api_headers(), timeout=40)
    if r.status_code != 200:
        return f"register{r.status_code}"
    vflow = None
    for c in r.json().get("continue_with", []):
        if c.get("action") == "show_verification_ui":
            vflow = c.get("flow", {}).get("id")
    if not vflow:
        r2 = s.get(f"{CONSOLE}/auth/self-service/verification/flows", headers=api_headers(), timeout=40)
        vflow = r2.json().get("id")
    if not vflow:
        return "vflow"
    code = mail_code(mtok, mbase, mkind)
    if not code:
        return "nocode"
    r = s.get(f"{CONSOLE}/auth/self-service/verification/flows?id={vflow}", headers=api_headers(), timeout=40)
    r = s.post(f"{CONSOLE}/auth/self-service/verification?flow={vflow}",
               json={"method": "code", "code": code, "csrf_token": nodes_csrf(r.json()) or ""}, headers=api_headers(), timeout=40)
    if r.status_code != 200:
        return f"verify{r.status_code}"
    r = s.get(f"{CONSOLE}/auth/self-service/login/browser?refresh=true", headers=api_headers(), timeout=40)
    lg_flow = r.json().get("id")
    r = s.post(f"{CONSOLE}/auth/self-service/login?flow={lg_flow}",
               json={"csrf_token": nodes_csrf(r.json()), "method": "password", "password": pw, "identifier": email},
               headers=api_headers(), timeout=40)
    if r.status_code != 200:
        return f"login{r.status_code}"
    pid = None
    for _ in range(8):
        r = s.get(f"{CONSOLE}/api/v1/organizations/projects", headers=api_headers(csrf), timeout=40)
        items = (r.json() or {}).get("items") or []
        if items:
            pid = items[0]["id"]
            break
        s.post(f"{CONSOLE}/api/v1/organizations/entities", json={"organization_name": company}, headers=api_headers(csrf), timeout=40)
        time.sleep(2.2)
    if not pid:
        return "noprojects"
    r = s.post(f"{CONSOLE}/api/v1/users/limited-usage-api-key?usage=inference",
               json={"alias": "farm-" + rnd(4), "expires_at": "never", "project_id": pid}, headers=api_headers(csrf), timeout=40)
    if r.status_code != 200:
        return f"key{r.status_code}"
    key = (r.json().get("api_key_info") or {}).get("api_key") or r.json().get("apiKey") or ""
    if not key:
        return "key0"
    alive = "0"
    try:
        ra = requests.post("https://api.inference.crusoecloud.com/v1/chat/completions",
                           headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                           json={"model": "deepseek-ai/Deepseek-V4-Flash", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}, timeout=45)
        alive = "1" if ra.status_code == 200 else "0"
    except Exception:
        alive = "0"
    print(f"KEY {WORKER} {email}:{pw}:{key}:{alive}", flush=True)  # в лог для резервного парсинга
    return f"OK::{key}"


def main():
    log(f"=== FARM301v2 {WORKER}: {MINUTES} мин")
    t_end = time.time() + max(60, (MINUTES - 2) * 60)
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    stats = {"ok": 0, "att": 0, "fails": {}}
    keys = []
    while time.time() < t_end:
        try:
            res = attempt(0, s)
        except Exception as e:
            res = f"exc:{str(e)[:30]}"
        stats["att"] += 1
        if res.startswith("OK::"):
            stats["ok"] += 1
            keys.append(res[4:])
            log(f"OK ключ #{stats['ok']}")
        elif res == "STORM":
            stats["fails"][res] = stats["fails"].get(res, 0) + 1
            time.sleep(45 + random.random() * 45)  # окно CF закрыто — ждём reopening, не жечь фид
            continue
        else:
            stats["fails"][res] = stats["fails"].get(res, 0) + 1
        time.sleep(2)
    log(f"=== {WORKER} ИТОГ ok={stats['ok']} attempts={stats['att']} fails={json.dumps(stats['fails'])}")
    if keys and GH_TOKEN:
        try:
            payload = "\n".join(f"gh-actions:{WORKER}:{k}:1" for k in keys)
            cur = subprocess.run(["gh", "api", f"repos/{DUMP}/contents/farm301_keys.txt"], capture_output=True, text=True, timeout=30)
            sha = None
            old = ""
            if cur.returncode == 0:
                j = json.loads(cur.stdout)
                sha = j.get("sha")
                old = base64.b64decode(j.get("content", "")).decode()
            merged = old + payload + "\n"
            subprocess.run(["gh", "api", f"repos/{DUMP}/contents/farm301_keys.txt", "-f", f"message={WORKER} push", "-f", "content=" + base64.b64encode(merged.encode()).decode()] + (["-f", f"sha={sha}"] if sha else []), capture_output=True, timeout=30)
        except Exception as e:
            log(f"push err: {str(e)[:40]}")


if __name__ == "__main__":
    main()
