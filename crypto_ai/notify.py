"""Best-effort Discord alerts. Silent unless DISCORD_WEBHOOK_URL is set; never raises."""
import os

import requests


def alert(msg: str) -> bool:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print(f"  [notify] DISCORD_WEBHOOK_URL not set -- would have sent: {msg}")
        return False
    try:
        requests.post(url, json={"content": f"\U0001F6D1 **[crypto_ai]** {msg}"}, timeout=10).raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"  [notify] Discord post failed: {e}")
        return False
