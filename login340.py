import asyncio, json, re, sys, time, urllib.request, websockets
import requests as rq

EMAIL, PW = sys.argv[1], sys.argv[2]
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 9231
KEYS = "/home/ronnikols/crusoe-farm/farm340_keys.txt"

def log(m): print(time.strftime("[%H:%M:%S] ") + str(m), flush=True)

def alive_check(key):
    try:
        r = rq.post("https://api.inference.crusoecloud.com/v1/chat/completions",
            headers={"Authorization": "Bearer " + key}, json={"model": "deepseek-ai/Deepseek-V4-Flash",
            "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}, timeout=30)
        return r.status_code == 200
    except Exception: return False

def wait_code(user, tmo=280, max_age_min=30):
    t0 = time.time()
    while time.time() - t0 < tmo:
        try:
            r = rq.post("https://api.maildrop.cc/graphql", timeout=15,
                json={"query": '{inbox(mailbox:"%s"){id mailfrom subject date}}' % user})
            ms = (r.json().get("data") or {}).get("inbox", []) or []
        except Exception:
            ms = []
        cands = []
        for m in ms:
            if "crusoe" not in (m.get("mailfrom","") + m.get("subject","")).lower(): continue
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(m.get("date","").replace("Z","+00:00")).timestamp() if m.get("date") else 0
            except Exception:
                dt = 0
            if dt and time.time() - dt > max_age_min * 60: continue
            cands.append((dt, m))
        cands.sort(reverse=True)
        for _, m in cands:
            try:
                r2 = rq.post("https://api.maildrop.cc/graphql", timeout=15,
                    json={"query": '{message(mailbox:"%s",id:"%s"){html data}}' % (user, m["id"])})
                d = (r2.json().get("data") or {}).get("message") or {}
                h = (d.get("html") or "") + " " + (d.get("data") or "")
                mm = re.search(r"\b(\d{6})\b", h)
                if mm and mm.group(1) != "999999": return mm.group(1)
            except Exception: pass
        time.sleep(4)
    return None

NID = [800000]
async def cmd(w, method, params=None):
    NID[0] += 1
    await w.send(json.dumps({"id": NID[0], "method": method, "params": params or {}}))

async def ev(w, expr, tmo=30):
    NID[0] += 1; i = NID[0]
    await w.send(json.dumps({"id": i, "method": "Runtime.evaluate",
        "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
    t0 = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - t0 < tmo:
        try: d = json.loads(await asyncio.wait_for(w.recv(), tmo))
        except Exception: continue
        if d.get("id") == i:
            return (d.get("result") or {}).get("result", {}).get("value")
    return None

async def type_code(w, code):
    await ev(w, """(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      const q=[...document.querySelectorAll('input')].filter(i=>i.type!=='checkbox'&&i.type!=='radio'&&i.type!=='hidden');
      q.forEach(i=>{i.focus();s.call(i,'');i.dispatchEvent(new Event('input',{bubbles:true}))});
      const e=q.filter(i=>!i.value); if(e.length) e[0].focus(); return e.length})()""")
    for ch in str(code):
        await cmd(w, "Input.dispatchKeyEvent", {"type": "keyDown", "key": ch, "text": ch, "windowsVirtualKeyCode": ord(ch)})
        await cmd(w, "Input.dispatchKeyEvent", {"type": "keyUp", "key": ch, "windowsVirtualKeyCode": ord(ch)})
        await asyncio.sleep(0.3)
    await asyncio.sleep(2)
    await ev(w, """(()=>{const b=[...document.querySelectorAll('button')].find(x=>/^(continue|verify|submit|next)$/i.test((x.innerText||'').trim()));
      if(b){b.click();return 'ok'} return 'nobtn'})()""")

async def login_multistep(w):
    # email → Next → password → Next
    for _ in range(10):
        r = await ev(w, """(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
          const q=[...document.querySelectorAll('input')].find(i=>(i.type==='text'||i.type==='email')&&!i.disabled);
          if(!q)return null;q.focus();s.call(q,'%s');q.dispatchEvent(new Event('input',{bubbles:true}));q.dispatchEvent(new Event('change',{bubbles:true}));
          return 'set'})()""" % EMAIL)
        if r:
            pwvis = await ev(w, """(()=>{const q=[...document.querySelectorAll('input')].find(i=>i.type==='password'&&!i.disabled&&(i.offsetWidth||i.getClientRects().length)); return q?1:0})()""")
            if not pwvis:
                await ev(w, """(()=>{const sub=[...document.querySelectorAll('button')].find(x=>x.type==='submit');if(sub)sub.click();return 1})()""")
            log("email шаг")
            break
        await asyncio.sleep(3)
    for _ in range(10):
        r = await ev(w, """(()=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
          const q=[...document.querySelectorAll('input')].find(i=>i.type==='password'&&!i.disabled&&!i.value);
          if(!q)return null;q.focus();s.call(q,'%s');q.dispatchEvent(new Event('input',{bubbles:true}));q.dispatchEvent(new Event('change',{bubbles:true}));
          return 'set'})()""" % PW)
        if r:
            await ev(w, """(()=>{const sub=[...document.querySelectorAll('button')].find(x=>x.type==='submit');if(sub)sub.click();return 1})()""")
            log("password шаг")
            return True
        await asyncio.sleep(3)
    return False

async def keyfetch(w):
    keyres = await ev(w, """(async()=>{
      try{
        const r0 = await fetch('/api/v1', {credentials:'include', headers:{'Accept':'application/json'}});
        const csrf = r0.headers.get('x-csrf-token') || r0.headers.get('X-Csrf-Token');
        await fetch('/api/v1/organizations/entities', {method:'POST', credentials:'include',
          headers:{'Content-Type':'application/json','X-Csrf-Token':csrf||''},
          body: JSON.stringify({organization_name:'Systems'})});
        let pid=null;
        for(let i=0;i<12;i++){
          const rp = await fetch('/api/v1/organizations/projects', {credentials:'include', headers:{'Accept':'application/json'}});
          if(rp.ok){const j=await rp.json(); const it=(j.items||j.projects||[]); if(it&&it.length){pid=it[0].id; break;}}
          await new Promise(r=>setTimeout(r,3000));
        }
        if(!pid) return 'no projects';
        const rk = await fetch('/api/v1/users/limited-usage-api-key?usage=inference', {method:'POST', credentials:'include',
          headers:{'Content-Type':'application/json','X-Csrf-Token':csrf||''},
          body: JSON.stringify({alias:'f'+Math.random().toString(36).slice(2,6), expires_at:'never', project_id:pid})});
        const jk = await rk.json();
        const key = jk.apiKey || jk.api_key || (jk.api_key_info||{}).api_key || (jk.api_key_info||{}).key || jk.key || '';
        if(!key) return 'key empty '+rk.status+' '+JSON.stringify(jk).slice(0,120);
        return 'KEY:'+key;
      }catch(e){return 'api exc '+String(e).slice(0,80)}
    })()""", 120)
    log("keyres=" + str(keyres)[:130])
    if keyres and str(keyres).startswith("KEY:"):
        key = str(keyres)[4:].strip()
        al = await asyncio.to_thread(alive_check, key)
        with open(KEYS, "a") as f: f.write(f"{EMAIL}:{key}:{'1' if al else '0'}\n")
        log(f"*** KEY {EMAIL} alive={al}")

async def main():
    user = EMAIL.split("@")[0]
    tab = rq.put(f"http://127.0.0.1:{PORT}/json/new?https://console.crusoecloud.com/login", timeout=10).json()
    log("tab новая")
    async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=20*1024*1024, open_timeout=25) as w:
        await asyncio.sleep(6)
        try:
            ok = await login_multistep(w)
        except Exception as e:
            ok = None; log("mstep exc " + repr(e)[:60])
        # ждать: verify-страница (код) ИЛИ консоль (в т.ч. если multistep не нужен — сессия уже есть)
        state = None
        u = ""
        t0 = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - t0 < 30:
            await asyncio.sleep(4)
            u = await ev(w, "location.href", 10) or ""
            if "/verify" in u: state = "verify"; break
            if "/login" not in u and "/request" not in u: state = "console"; break
        if state is None:
            # возможно уже на консоли, но не в цикле выше — проверка после mstep-фейла
            if "/login" in u:
                log("застряли на /login, пароль неверен?"); return
            state = "console"
        log("state=" + str(state) + " " + str(u)[:60])
        if state == "verify":
            code = await asyncio.to_thread(wait_code, user, 280)
            log("код: " + str(code))
            if not code: return
            await type_code(w, code)
            t0 = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - t0 < 40:
                await asyncio.sleep(4)
                u = await ev(w, "location.href", 10) or ""
                if "/verify" not in u: break
        await asyncio.sleep(5)
        await keyfetch(w)
    try: rq.get(f"http://127.0.0.1:{PORT}/json/close/{tab['id']}", timeout=5)
    except Exception: pass

asyncio.run(main())
