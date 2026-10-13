"""llm_probe.py -- READ-ONLY: does each configured AI provider (Groq, OpenRouter backup) answer right now?
Sends one tiny prompt per endpoint. Never prints keys. Output: research/out/llm_probe.md"""
import json
import os
import time

import requests

from crypto_ai.lock import load_config

OUT = os.path.join(os.path.dirname(__file__), "out")


def main():
    cfg = load_config()["llm"]
    L = [f"# AI provider check ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", ""]
    for ep in cfg["endpoints"]:
        key = os.environ.get(ep["key_env"])
        if not key:
            L.append(f"- **{ep['name']}**: ❌ no key set (secret {ep['key_env']} missing)"); continue
        body = {"model": ep["model"], "messages": [{"role": "user", "content": "Reply with the single word OK."}],
                "max_tokens": 50, **ep.get("extra_body", {})}
        t = time.time()
        try:
            r = requests.post(ep["url"], headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
            ok = r.status_code == 200
            txt = (r.json()["choices"][0]["message"].get("content") or "")[:40] if ok else r.text[:200]
            L.append(f"- **{ep['name']}** ({ep['model']}): {'✅' if ok else '❌'} HTTP {r.status_code} in {time.time() - t:.1f}s — {txt!r}")
        except Exception as e:
            L.append(f"- **{ep['name']}**: ❌ {type(e).__name__}")
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "llm_probe.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
