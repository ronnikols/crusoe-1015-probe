#!/usr/bin/env python3
# farm340: фарм через CDP-вкладки, egress LTE, почта maildrop.cc
# v2: N изолированных хром-инстансов (по одному на воркера) — куки не пересекаются
import asyncio, json, os, random, re, string, subprocess, threading, time, requests, websockets

CDP0 = 9240
BASE = "https://console.crusoecloud.com"
TARGET = int(os.environ.get("TARGET", "600"))
THREADS = int(os.environ.get("THREADS", "12"))
INSTANCES = int(os.environ.get("INSTANCES", "2"))
SLEEP_BETWEEN = int(os.environ.get("SLEEP", "3"))
D = os.environ.get("FARM_DIR", "/home/ronnikols/crusoe-farm")
os.makedirs(D, exist_ok=True)
LOG = os.environ.get("FLOG", D + "/farm342.log")
KEYS = D + "/farm342_keys.txt"
STATS = D + "/farm342_stats.json"
ENV = {**os.environ}
chrome_procs = []

def cdp(idx): return f"http://127.0.0.1:{CDP0 + idx}"

def start_chrome(idx):
    d = os.environ.get("PROFILE_DIR", "/home/ronnikols/.cache") + f"/cdp342-{idx}"
    os.makedirs(d, exist_ok=True)
    p = subprocess.Popen([os.environ.get("CHROME", "chromium"), f"--user-data-dir={d}", f"--remote-debugging-port={CDP0 + idx}",
        "--no-first-run", "--window-position=-32000,-32000",
        "--disable-dev-shm-usage", "--disable-gpu", "--mute-audio",
        "--blink-settings=imagesEnabled=false"], env=ENV,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chrome_procs.append(p)
    for t in range(20):
        try:
            requests.get(cdp(idx) + "/json/version", timeout=3); return True
        except Exception: time.sleep(1)
    return False

st = {"ok": 0, "alive": 0, "attempts": 0, "fails": {}, "last_event": "старт", "started": time.strftime("%H:%M:%S")}
stl = threading.Lock()

def log(m):
    with stl:
        print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
        with open(LOG, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

def save_stats(ev=None):
    with stl:
        if ev: st["last_event"] = ev
        with open(STATS, "w") as f: json.dump(st, f)

def fail(kind):
    with stl: st["fails"][kind] = st["fails"].get(kind, 0) + 1

def rnd(n=10): return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

FIRST = ["James","John","Robert","Michael","David","William","Richard","Joseph","Thomas","Charles","Daniel","Matthew","Andrew","Joshua","Kevin","Brian","George","Edward","Ronald","Timothy","Jason","Jeffrey","Ryan","Jacob","Gary","Eric","Stephen","Larry","Justin","Scott","Benjamin","Samuel","Gregory","Alexander","Patrick","Frank","Raymond","Jack","Dennis","Jerry","Tyler","Aaron","Jose","Adam","Nathan","Henry","Zachary","Douglas","Peter","Kyle","Noah","Ethan","Jeremy","Walter","Christian","Keith","Roger","Terry","Austin","Sean","Gerald","Carl","Harold","Dylan","Arthur","Lawrence","Jordan","Jesse","Bryan","Billy","Bruce","Willie","Gabriel","Alan","Juan","Logan","Wayne","Ralph","Roy","Eugene","Randy","Vincent","Russell","Elijah","Louis","Bobby","Philip","Johnny","Mary","Patricia","Jennifer","Linda","Elizabeth","Barbara","Susan","Jessica","Sarah","Karen","Nancy","Lisa","Margaret","Betty","Sandra","Ashley","Kimberly","Emily","Donna","Michelle","Carol","Amanda","Melissa","Deborah","Stephanie","Rebecca","Laura","Sharon","Cynthia","Kathleen","Amy","Angela","Shirley","Anna","Brenda","Pamela","Emma","Nicole","Helen","Samantha","Katherine","Christine","Debra","Rachel","Carolyn","Janet","Catherine","Maria","Heather","Diane","Ruth","Julie","Olivia","Joyce","Virginia","Victoria","Kelly","Lauren","Paula","Christina","Joan","Evelyn","Judith","Megan","Andrea","Cheryl","Hannah","Jacqueline","Martha","Gloria","Teresa","Ann","Sara","Madison","Frances","Kathryn","Janice","Jean","Abigail","Alice","Julia","Judy","Sophia","Grace","Denise","Amber","Doris","Marilyn","Danielle","Beverly","Isabelle","Theresa","Diana","Natalie","Brittany","Charlotte","Marie","Kayla","Alexis","Lori"]
LAST = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin","Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson","Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores","Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell","Carter","Roberts","Gomez","Phillips","Evans","Turner","Diaz","Parker","Cruz","Edwards","Collins","Reyes","Stewart","Morris","Morales","Murphy","Cook","Rogers","Gutierrez","Ortiz","Morgan","Cooper","Peterson","Bailey","Reed","Kelly","Howard","Ramos","Kim","Cox","Ward","Richardson","Watson","Brooks","Chavez","Wood","James","Bennett","Gray","Mendoza","Ruiz","Hughes","Price","Alvarez","Castillo","Sanders","Patel","Myers","Long","Ross","Foster","Jimenez","Powell","Bryant","Russell","Ortega","Washington","Coleman","Jenkins","Perry","Powell","Patterson","Bailey","Rivera","Russell","Griffin","Diaz","Alvarez"]
CO_A = ["Nimbus","Vertex","Quantum","Apex","Stellar","Nova","Zenith","Orion","Astra","Kestrel","Falcon","Meridian","Helios","Lumen","Cobalt","Obsidian","Aurora","Titan","Atlas","Prism","Vantage","Spectra","Beacon","Cascade","Ember","Granite","Harbor","Ironwood","Juniper","Keystone","Lantern","Manifold","Northwind","Onyx","Pinnacle","Quarry","Redwood","Silvertree","Summit","Talon","Umbra","Veridian","Westbrook","Xenon","Yarrow","Zephyr","Aegis","Brightside","Clearwater","Driftwood","Everline","Foundry","Grove","Halcyon","Ironclad","Jetstream","Kingfisher","Lattice","Midfield","Nectar","Outpost","Pillar","Quartz","Ridgeline","Sable","Terrace","Unified","Vantage","Willow","Arrow","Bastion","Compass","Delta","Echoline","Foothill","Glacier","Hearth","Isotope","Juniper","Kindred","Ledger","Mesa","Nautical","Origin","Pathway","Quintessence","Ridge","Stone","Timber","Union","Verdant","Whitfield","Amber","Birch","Cliff","Dune","Emberline","Fjord","Granite","Hollow","Inlet"]
CO_B = [" Analytics"," Systems"," Digital"," Labs"," Works"," Studio"," Technologies"," Solutions"," Dynamics"," Consulting"," Ventures"," Industries"," Robotics"," Software"," Networks"," Forge"," Collective"," Partners"," Innovations"," Engineering"]

def real_person():
    return random.choice(FIRST) + " " + random.choice(LAST)

def real_company():
    return random.choice(CO_A) + random.choice(CO_B)

def maildrop_inbox(user):
    try:
        r = requests.post("https://api.maildrop.cc/graphql", json={"query": '{inbox(mailbox:"%s"){id mailfrom subject date}}' % user}, timeout=15)
        return r.json().get("data", {}).get("inbox", [])
    except Exception:
        return []

def maildrop_msg(user, mid):
    try:
        r = requests.post("https://api.maildrop.cc/graphql", json={"query": '{message(mailbox:"%s",id:"%s"){subject html data}}' % (user, mid)}, timeout=15)
        return r.json().get("data", {}).get("message", {}) or {}
    except Exception:
        return {}

def wait_code(user, tmo=140, max_age_min=25):
    # универсально: вернуть ("link", url) или ("code", 6 цифр) из письма (только СВЕЖЕЕ, не старше max_age_min)
    import time as _t
    from datetime import datetime
    t0 = _t.time()
    while _t.time() - t0 < tmo:
        cands = []
        for m in maildrop_inbox(user):
            if "crusoe" not in (m.get("mailfrom", "") + m.get("subject", "")).lower(): continue
            try:
                dt = datetime.fromisoformat(m.get("date", "").replace("Z", "+00:00")).timestamp() if m.get("date") else 0
            except Exception:
                dt = 0
            if dt and _t.time() - dt > max_age_min * 60: continue
            cands.append((dt, m))
        cands.sort(reverse=True)
        for _, m in cands:
            if "crusoe" in (m.get("mailfrom", "") + m.get("subject", "")).lower():
                msg = maildrop_msg(user, m["id"])
                html = (msg.get("html") or "") + " " + (msg.get("data") or "")
                html2 = html.replace("&amp;", "&")
                txt = html2
                import re as _re
                links = _re.findall(r'href="(https?://[^"\s]+)"', txt)
                cands = [L for L in links if "console.crusoecloud.com" in L and not any(x in L for x in ["unsubscribe", "privacy", "terms", "/docs"])]
                pri = [L for L in cands if "/auth/" in L]
                if pri:
                    return ("link", pri[0])
                mm = _re.search(r"\b(\d{6})\b", txt)
                if mm and mm.group(1) != "999999":
                    return ("code", mm.group(1))
                if cands:
                    return ("link", cands[0])
        time.sleep(2)
    return None

def alive_check(key):
    try:
        r = requests.post("https://api.inference.crusoecloud.com/v1/chat/completions",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            json={"model": "deepseek-ai/Deepseek-V4-Flash", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}, timeout=30)
        return r.status_code == 200
    except Exception:
        return False

def one_account(idx, email):
    pw = "Crs!" + rnd(10) + "aA1"
    tab = requests.put(cdp(idx) + "/json/new?about:blank", timeout=10).json()
    wsurl = tab.get("webSocketDebuggerUrl"); tid = tab.get("id")
    if not wsurl: return "no tab"
    res = "err"
    try:
        res = asyncio.run(_flow(wsurl, idx, email, pw))
    except Exception as e:
        res = "exc " + str(e)[:80]
    try: requests.get(cdp(idx) + "/json/close/" + tid, timeout=5)
    except Exception: pass
    return res

async def _flow(wsurl, idx, email, pw):
    async with websockets.connect(wsurl, max_size=20 * 1024 * 1024, open_timeout=15) as w:
        nid = [1000 + idx * 100]
        async def cmd(method, params=None):
            nid[0] += 1
            await w.send(json.dumps({"id": nid[0], "method": method, "params": params or {}}))
            return nid[0]
        async def ev(expr, tmo=40):
            myid = await cmd("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
            t0 = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - t0 < tmo:
                try: d = json.loads(await asyncio.wait_for(w.recv(), 10))
                except Exception: continue
                if d.get("id") == myid: return d.get("result", {}).get("result", {}).get("value")
            return None
        await cmd("Network.enable")
        await cmd("Network.clearBrowserCookies")
        await cmd("Page.navigate", {"url": BASE + "/request"})
        # 1. ждём форму
        for i in range(50):
            await asyncio.sleep(2)
            n = await ev("[...document.querySelectorAll('input')].length")
            cb = await ev("document.querySelectorAll('input[type=checkbox]').length")
            if n and int(n) >= 4 and cb and int(cb) >= 1: break
        # 2. fill + submit (prospects 429 лечится ретраями, не фейком)
        fullname = real_person(); company = real_company()
        await ev(f"window.__co = '{company}'")
        n = await ev(f"""(()=>{{const set=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
          const q=[...document.querySelectorAll('input')].filter(i=>i.type!=='checkbox');
          const vals=['{email}','{pw}','{company}','{fullname}'];
          q.forEach((inp,i)=>{{inp.focus();set.call(inp,vals[i]||'x');inp.dispatchEvent(new Event('input',{{bubbles:true}}));}});
          [...document.querySelectorAll('input[type=checkbox]')].forEach(x=>{{x.click();Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'checked').set.call(x,true);x.dispatchEvent(new Event('input',{{bubbles:true}}));x.dispatchEvent(new Event('change',{{bubbles:true}}));const l=x.closest('label')||x.parentElement;if(l)l.click();}});
          return q.length}})()""")
        if not n or int(n) < 4: return "no form inputs=" + str(n)
        clicked_reg = False
        for attempt in range(6):
            # ждём РЕШЕННУЮ капчу: hidden input cf-turnstile-response непустой ИЛИ кнопка enabled
            for i in range(16):
                await asyncio.sleep(2)
                st_t = await ev("""(()=>{const t=document.querySelector('input[name="cf-turnstile-response"]')||document.querySelector('input[name*=turnstile]');
                  const b=[...document.querySelectorAll('button')].find(x=>/^create account$/i.test((x.innerText||'').trim()));
                  const tok=t?(t.value||''):'';
                  return JSON.stringify({has:!!t, toklen:tok.length, bdisabled:b?!!b.disabled:null});})()""")
                try: jj = json.loads(st_t or "{}")
                except Exception: jj = {}
                # клик по виджету если interactive (однократно за попытку)
                if jj.get("has") and not jj.get("toklen") and i == 4:
                    rect = await ev("""(()=>{const w=document.querySelector('.cf-turnstile')||document.querySelector('[class*=turnstile]')||document.querySelector('iframe[src*=challenges.cloudflare]');
                      if(!w) return null; const r=w.getBoundingClientRect(); return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()""")
                    if rect:
                        try:
                            x, y = json.loads(rect)["x"], json.loads(rect)["y"]
                            for tp in ("mousePressed", "mouseReleased"):
                                await cmd("Input.dispatchMouseEvent", {"type": tp, "x": x, "y": y, "button": "left", "clickCount": 1})
                        except Exception: pass
                # строго: если turnstile-input есть — ждать его токен
                if jj.get("toklen"):
                    break
                if not jj.get("has") and i >= 1:
                    break  # капчи нет — жать почти сразу
            await ev("""(()=>{const b=[...document.querySelectorAll('button')].find(x=>/^create account$/i.test((x.innerText||'').trim())); if(b&&!b.disabled){b.click();return 'ok'} return 'nobtn'})()""")
            t0 = asyncio.get_event_loop().time()
            regok2 = False
            while asyncio.get_event_loop().time() - t0 < 25:
                try: d = json.loads(await asyncio.wait_for(w.recv(), 2))
                except Exception: d = None
                if d:
                    m = d.get("method"); p = d.get("params", {})
                    if m == "Network.requestWillBeSent" and "self-service/registration?flow=" in p.get("request", {}).get("url", ""):
                        regok2 = True; break
                    if m == "Network.responseReceived" and "self-service/registration?flow=" in p.get("response", {}).get("url", ""):
                        regok2 = True; break
                u = await ev("location.href")
                if u and "/verify" in str(u):
                    regok2 = True; break
                txt = await ev("document.body.innerText.slice(0,180)")
                if txt and ("thanks for signing up" in txt.lower() or "check your inbox" in txt.lower() or "check your email" in txt.lower() or "6 digit code" in txt.lower()):
                    regok2 = True; break
            if regok2: clicked_reg = True
            if clicked_reg: break
            await asyncio.sleep(9)
        if not clicked_reg:
            t = await ev("document.body.innerText.slice(0,180)")
            if t and ("thanks for signing up" in t.lower() or "check your inbox" in t.lower() or "check your email" in t.lower() or "6 digit code" in t.lower()):
                clicked_reg = True
        if not clicked_reg:
            u = await ev("location.href")
            if u and ("/verify" in str(u) or "/thanks" in str(u)):
                clicked_reg = True
        if not clicked_reg:
            t = await ev("document.body.innerText.slice(0,150)")
            return "reg-not-sent: " + str(t)[:100]
        # 3. register подтверждён (clicked_reg) — сетевое ожидание не нужно
        regok = [clicked_reg]
        t0 = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - t0 < 3:
            try: d = json.loads(await asyncio.wait_for(w.recv(), 5))
            except Exception: continue
            if d.get("method") == "Network.requestWillBeSent":
                u = d["params"]["request"]["url"]
                if "self-service/registration?flow=" in u:
                    regok[0] = True; break
            if d.get("method") == "Network.responseReceived":
                rp = d["params"]["response"]
                if "self-service/registration?flow=" in rp["url"] and rp["status"] == 200:
                    regok[0] = True; break
        if not regok[0]:
            t = await ev("document.body.innerText.slice(0,200)")
            return "reg-not-sent: " + str(t)[:120]
        # страница check email — ждём 200-ответ на reg POST
        await asyncio.sleep(4)
        try:
            with open("/home/ronnikols/crusoe-farm/farm342_accs.txt", "a") as f:
                f.write(f"{email}:{pw}\n")
        except Exception:
            pass
        # 4. письмо: что внутри — код или ссылка (они A/B переключают)
        got = await asyncio.to_thread(wait_code, email.split("@")[0], 240)
        if not got: return "no email code/link"
        kind, val = got
        log(f"w{idx} {email}: verify {kind} {str(val)[:70]}")
        ok = [False]
        if kind == "link":
            await cmd("Page.navigate", {"url": val})
            t0 = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - t0 < 50:
                try: d = json.loads(await asyncio.wait_for(w.recv(), 4))
                except Exception:
                    u = await ev("location.href")
                    if u and any(x in str(u) for x in ["/projects", "/console", "/foundry"]): ok[0] = True; break
                    continue
                if d.get("method") == "Network.responseReceived":
                    rp = d["params"]["response"]; u = rp["url"]
                    if ("verification" in u or "self-service" in u) and rp["status"] in (200, 302): ok[0] = True; break
                    if "/api/v1/" in u and rp["status"] == 200: ok[0] = True; break
        else:
            # НАТИВНЫЙ ввод кода: keyDown/keyUp по цифрам (React OTP слышит настоящие кей-ивенты, insertText не давал автопереход → invalid)
            await ev("""(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
              const q=[...document.querySelectorAll('input')].filter(i=>i.type!=='checkbox'&&i.type!=='hidden');
              q.forEach(i=>{i.focus();s.call(i,'');i.dispatchEvent(new Event('input',{bubbles:true}))});
              const e=q.filter(i=>!i.value); if(e.length) e[0].focus(); return e.length})()""")
            for ch in str(val):
                await cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": ch, "text": ch, "windowsVirtualKeyCode": ord(ch)})
                await cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch, "windowsVirtualKeyCode": ord(ch)})
                await asyncio.sleep(0.3)
            await asyncio.sleep(2)
            # Continue: ТОЛЬКО JS-клик (координатный dispatchMouseEvent не срабатывает на Mantine)
            await ev("""(()=>{const b=[...document.querySelectorAll('button')].find(x=>/^(continue|verify|submit)$/i.test((x.innerText||'').trim()));if(b){b.click();return 'ok'}return 'nobtn'})()""")
            t0 = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - t0 < 40:
                try: d = json.loads(await asyncio.wait_for(w.recv(), 4))
                except Exception:
                    u = await ev("location.href")
                    if u and any(x in str(u) for x in ["/projects", "/console", "/foundry"]): ok[0] = True; break
                    continue
                if d.get("method") == "Network.responseReceived":
                    rp = d["params"]["response"]; u = rp["url"]
                    if "verification?flow=" in u and rp["status"] == 200: ok[0] = True; break
                    if "/api/v1/" in u and rp["status"] == 200: ok[0] = True; break
        await asyncio.sleep(8)
        # ЛОГИН-ПУТЬ (проверен login340): goto /login → email→Next→password→Next → console или verify(код)
        await cmd("Page.navigate", {"url": "https://console.crusoecloud.com/login"})
        await asyncio.sleep(6)
        for _ in range(10):
            r = await ev("""(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
              const q=[...document.querySelectorAll('input')].find(i=>(i.type==='text'||i.type==='email')&&!i.disabled);
              if(!q)return null;q.focus();s.call(q,'%s');q.dispatchEvent(new Event('input',{bubbles:true}));q.dispatchEvent(new Event('change',{bubbles:true}));
              return 'set'})()""" % email)
            if r:
                await ev("(()=>{const sub=[...document.querySelectorAll('button')].find(x=>x.type==='submit');if(sub)sub.click();if(document.querySelector('form'))document.querySelector('form').requestSubmit(sub);return 1})()")
                break
            await asyncio.sleep(3)
        for _ in range(10):
            r = await ev("""(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
              const q=[...document.querySelectorAll('input')].find(i=>i.type==='password'&&!i.disabled);
              if(!q)return null;q.focus();s.call(q,'%s');q.dispatchEvent(new Event('input',{bubbles:true}));q.dispatchEvent(new Event('change',{bubbles:true}));
              return 'set'})()""" % pw)
            if r:
                await ev("(()=>{const sub=[...document.querySelectorAll('button')].find(x=>x.type==='submit');if(sub)sub.click();if(document.querySelector('form'))document.querySelector('form').requestSubmit(sub);return 1})()")
                await asyncio.sleep(6)
                break
            await asyncio.sleep(3)
        # после password-Next возможен /verify (мультишаг шлёт НОВОЕ письмо) — вводим свежий код
        u2 = await ev("location.href") or ""
        if "/verify" in str(u2):
            code2 = await asyncio.to_thread(wait_code, email.split("@")[0], 200)
            if code2:
                await ev("""(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                  const q=[...document.querySelectorAll('input')].filter(i=>i.type!=='checkbox'&&i.type!=='radio'&&i.type!=='hidden');
                  q.forEach(i=>{i.focus();s.call(i,'');i.dispatchEvent(new Event('input',{bubbles:true}))});
                  const e=q.filter(i=>!i.value); if(e.length) e[0].focus(); return e.length})()""")
                for ch in str(code2):
                    await cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": ch, "text": ch, "windowsVirtualKeyCode": ord(ch)})
                    await cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch, "windowsVirtualKeyCode": ord(ch)})
                    await asyncio.sleep(0.3)
                await asyncio.sleep(2)
                await ev("""(()=>{const b=[...document.querySelectorAll('button')].find(x=>/^(continue|verify|submit)$/i.test((x.innerText||'').trim()));if(b){b.click();return 'ok'}return 'nobtn'})()""")
                await asyncio.sleep(6)
        await asyncio.sleep(4)
        keyres = await ev("""(async()=>{
          try{
            const r0 = await fetch('/api/v1', {credentials:'include', headers:{'Accept':'application/json'}});
            const csrf = r0.headers.get('x-csrf-token') || r0.headers.get('X-Csrf-Token');
            await fetch('/api/v1/organizations/entities', {method:'POST', credentials:'include',
              headers:{'Content-Type':'application/json','X-Csrf-Token':csrf||''},
              body: JSON.stringify({organization_name: window.__co || 'Systems'}).catch(()=>{});
            let pid=null;
            for(let i=0;i<8;i++){
              const rp = await fetch('/api/v1/organizations/projects', {credentials:'include', headers:{'Accept':'application/json'}});
              if(rp.ok){const j=await rp.json(); const items=(j.items||j.projects||[]); if(items&&items.length){pid=items[0].id; break;}}
              await new Promise(r=>setTimeout(r,2500));
            }
            if(!pid) return 'no projects';
            const rk = await fetch('/api/v1/users/limited-usage-api-key?usage=inference', {method:'POST', credentials:'include',
              headers:{'Content-Type':'application/json','X-Csrf-Token':csrf||''},
              body: JSON.stringify({alias:'f'+Math.random().toString(36).slice(2,6), expires_at:'never', project_id:pid})});
            const jk = await rk.json();
            const key = jk.apiKey || jk.api_key || (jk.api_key_info||{}).api_key || (jk.api_key_info||{}).key || jk.key || '';
            if(!key) return 'key empty '+rk.status+' '+JSON.stringify(jk).slice(0,100);
            return 'KEY:'+key;
          }catch(e){return 'api exc '+String(e).slice(0,80)}
        })()""", tmo=150)
        return keyres or "no keyres"

def worker(idx):
    while st["alive"] < TARGET:
        with stl: st["attempts"] += 1
        save_stats("ворк%d" % idx)
        em = "cr" + rnd(9) + "@maildrop.cc"
        r = one_account(idx, em)
        log(f"w{idx} {em}: {r}")
        if isinstance(r, str) and r.startswith("KEY:"):
            key = r[4:].strip()
            al = alive_check(key)
            with stl:
                st["ok"] += 1; st["alive"] += 1 if al else 0
                with open(KEYS, "a") as f:
                    f.write(f"{em}:{key}:{'1' if al else '0'}\n")
            save_stats("KEY +" + ("alive" if al else "dead"))
        else:
            fail((r or "?")[:28])
        time.sleep(SLEEP_BETWEEN)

if __name__ == "__main__":
    log(f"=== ФАРМ342 СТАРТ: инстансов {INSTANCES} воркеров {THREADS}, цель {TARGET}, egress LTE, maildrop.cc")
    save_stats("старт")
    ok = [start_chrome(i) for i in range(INSTANCES)]
    log(f"хромы подняты: {sum(ok)}/{THREADS}")
    ts = [threading.Thread(target=worker, args=(i % INSTANCES,), daemon=True) for i in range(THREADS)]
    [t.start() for t in ts]
    try:
        while any(t.is_alive() for t in ts):
            time.sleep(10)
    finally:
        for p in chrome_procs: p.kill()
    log("=== ЗАВЕРШЁН: alive=%d attempts=%d" % (st["alive"], st["attempts"]))
