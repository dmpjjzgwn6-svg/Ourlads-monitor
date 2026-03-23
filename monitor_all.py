import os
import re
import json
import time
import hashlib

import requests
from bs4 import BeautifulSoup

STATE_FILE = "state.json"
URLS_FILE = "team_urls.txt"

WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def discord_post(msg: str):
    if not WEBHOOK:
        print("DISCORD_WEBHOOK_URL missing; skipping Discord post.")
        return
    r = requests.post(WEBHOOK, json={"content": msg}, timeout=25)
    r.raise_for_status()

def fetch(url: str) -> str:
    delays = [0, 3, 8, 15]
    last_err = None
    for d in delays:
        if d:
            time.sleep(d)
        try:
            r = requests.get(url, headers=HEADERS, timeout=45)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
    print(f"Fetch failed for {url}: {last_err}")
    return ""

def load_urls() -> list[str]:
    try:
        with open(URLS_FILE, "r", encoding="utf-8") as f:
            urls = []
            for line in f:
                u = line.strip()
                if not u or u.startswith("#"):
                    continue
                urls.append(u)
            return urls
    except FileNotFoundError:
        print("team_urls.txt not found. Create it with one full URL per line.")
        return []

def extract_team_name_updated_and_text(team_html: str):
    soup = BeautifulSoup(team_html, "html.parser")

    h = soup.find(["h1", "h2"])
    team_name = h.get_text(" ", strip=True) if h else "Unknown Team"

    full_text = soup.get_text("\n", strip=True)

    m = re.search(r"Updated:\s*([0-9]{2}/[0-9]{2}/[0-9]{4}[^\n]*)", full_text)
    updated = m.group(1).strip() if m else "Unknown"

    watched = f"Updated: {updated}\n{full_text}"
    return team_name, updated, watched

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)

def main():
    urls = load_urls()
    print(f"Loaded {len(urls)} team URLs from team_urls.txt")
    if not urls:
        return

    state = load_state()
    changed = []
    new_state = {}

    for url in urls:
        html = fetch(url)
        if not html:
            if url in state:
                new_state[url] = state[url]
            continue

        team_name, updated, watched = extract_team_name_updated_and_text(html)
        h = sha(watched)

        prev = state.get(url)
        if prev and prev.get("hash") != h:
            changed.append((team_name, updated, url))

        new_state[url] = {"team": team_name, "updated": updated, "hash": h}
        time.sleep(0.25)

    if changed:
        lines = [f"🏈 **Ourlads depth charts changed ({len(changed)} teams)**"]
        for team_name, updated, url in changed[:25]:
            lines.append(f"- **{team_name}** (Updated: {updated}) — {url}")
        if len(changed) > 25:
            lines.append(f"- …and {len(changed) - 25} more")
        discord_post("\n".join(lines))

    print(f"Saving state for {len(new_state)} teams")
    if not new_state:
        print("New state is empty; not overwriting state.json.")
        return

    save_state(new_state)
