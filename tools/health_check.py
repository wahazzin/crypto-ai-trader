"""health_check.py -- is the crypto AI trader alive? Alerts to THIS repo's Discord channel (secret
DISCORD_WEBHOOK_URL). Also sends one-off messages (used by the weekly review). Paper only."""
import calendar
import json
import os
import subprocess
import sys
import time

import requests

API = "https://api.github.com"
REPO = os.environ.get("GITHUB_REPOSITORY", "wahazzin/crypto-ai-trader")
H = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {os.environ.get('GH_TOKEN', '')}"}


def send(msg):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("[no webhook]", msg); return
    requests.post(url, json={"content": msg[:1900]}, timeout=15)


def read_cycles_text(get=requests.get):
    """Whole cycles.jsonl from the data branch. No byte-range request: since ~2026-11-06
    raw.githubusercontent.com answers suffix ranges ("bytes=-6000") with 501 "Unsupported client range",
    which made this check report "couldn't read recent cycles (HTTPError)" every few hours. The file is small
    (~65 KB, +~2 KB/day), so reading it whole is fine. One retry for transient errors."""
    url = f"https://raw.githubusercontent.com/{REPO}/crypto-ai-data/cycles.jsonl"
    for attempt in range(2):
        r = get(url, timeout=30)
        if r.status_code < 500 or attempt == 1:
            r.raise_for_status()
            return r.text
        time.sleep(5)


def last_cycles(text, n=2):
    cyc = [json.loads(l) for l in text.splitlines() if l.startswith("{") and l.endswith("}")][-n:]
    if not cyc:
        raise ValueError("no cycles found in the file")
    return cyc


def problems():
    out = []
    try:
        n = requests.get(f"{API}/repos/{REPO}/actions/workflows/crypto_ai_loop.yml/runs", headers=H,
                         params={"status": "in_progress"}, timeout=30).json().get("total_count", 0)
        if n == 0:
            out.append(("loop", "Crypto AI trader: the 24/7 scanning loop is not running."))
    except Exception as e:
        out.append(("loop", f"Crypto AI trader: couldn't check the loop ({type(e).__name__})."))
    try:
        js = requests.get(f"{API}/repos/{REPO}/commits", headers=H, params={"sha": "crypto-ai-data", "per_page": 1}, timeout=30).json()
        age = time.time() - calendar.timegm(time.strptime(js[0]["commit"]["committer"]["date"], "%Y-%m-%dT%H:%M:%SZ"))
        if age > 8 * 3600:                    # cycles every 6 h always write state
            out.append(("state", f"Crypto AI trader: no state saved for {age / 3600:.1f} h (expected at least every 6 h)."))
    except Exception as e:
        out.append(("state", f"Crypto AI trader: couldn't read state ({type(e).__name__})."))
    try:
        # silent-failure check: the bot keeps running even if the free AI (Groq) stops answering
        cyc = last_cycles(read_cycles_text(), 2)
        bad = [c for c in cyc if c.get("status") != "OK" or not all(a.get("ok") for a in (c.get("ai") or {}).values())]
        if cyc and len(bad) == len(cyc):
            arms = sorted({a for c in cyc for a, v in (c.get("ai") or {}).items() if not v.get("ok")})
            out.append(("ai", f"Crypto AI trader: the AI failed in the last {len(cyc)} cycles "
                              f"(status {cyc[-1].get('status')}; failing: {', '.join(arms) or 'all'}). "
                              f"Exact errors: decisions.jsonl on branch crypto-ai-data."))
    except Exception as e:
        out.append(("ai", f"Crypto AI trader: couldn't read recent cycles ({type(e).__name__}: {str(e)[:120]})."))
    return out


def check():
    url = f"https://x-access-token:{os.environ.get('GH_TOKEN', '')}@github.com/{REPO}.git"
    d = "hs"
    if subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "health-state", url, d]).returncode != 0:
        os.makedirs(d, exist_ok=True)
        for c in (["init", "-q"], ["checkout", "-q", "-b", "health-state"], ["remote", "add", "origin", url]):
            subprocess.run(["git", "-C", d] + c)
    p = os.path.join(d, "alerts.json")
    last = json.load(open(p)) if os.path.exists(p) else {}
    probs, now = problems(), time.time()
    for k, msg in probs:
        if now - last.get(k, 0) > 6 * 3600:
            send(f"⚠️ {msg} Paper only, no money at risk."); last[k] = now
    for k in list(last):
        if last[k] and k not in [x for x, _ in probs]:
            send(f"✅ Crypto AI trader recovered: {k} OK again."); last[k] = 0
    json.dump(last, open(p, "w"))
    g = ["git", "-C", d, "-c", "user.name=crypto-ai-bot", "-c", "user.email=actions@github.com"]
    subprocess.run(g + ["add", "-A"]); subprocess.run(g + ["commit", "-q", "-m", "health"])
    subprocess.run(["git", "-C", d, "push", "-q", "origin", "HEAD:health-state"])
    print("problems:", probs)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "test":
        send("✅ Test from the crypto AI trader: alerts for this channel work.")
    elif a and a[0] == "message":
        send(os.environ.get("TEXT", ""))
    else:
        check()
