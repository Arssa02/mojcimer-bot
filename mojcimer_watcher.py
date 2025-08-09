import os, json, time
import requests
from bs4 import BeautifulSoup

# --- Scraper config ---
BASE = "https://www.mojcimer.si"
LIST_URL = BASE + "/seznam-prostih-sob/?page={}"
PAGES_TO_SCAN = [1, 2, 3]
SEEN_FILE = "seen.json"
CITY_KEYWORDS = ("koper", "capodistria")
REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; MojCimerWatcher/1.0)"

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# --- Telegram env ---
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)

def page_html(url):
    r = session.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text

def extract_listings():
    items = {}
    for p in PAGES_TO_SCAN:
        html = page_html(LIST_URL.format(p))
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a[href*="/seznam-prostih-sob/"]'):
            href = a.get("href") or ""
            if "/seznam-prostih-sob/" not in href:
                continue
            # skip non-detail links with query strings
            if "?" in href and not href.rstrip("/").split("/")[-1].isdigit():
                continue
            link = href if href.startswith("http") else (BASE + href)
            container = a.find_parent()
            raw_text = container.get_text(" ", strip=True) if container else a.get_text(" ", strip=True)
            snippet = " ".join(raw_text.split())
            if len(snippet) > 250:
                snippet = snippet[:247] + "..."
            items[link] = {"url": link, "snippet": snippet}
    return list(items.values())

def looks_like_koper(text):
    t = text.lower()
    return any(k in t for k in CITY_KEYWORDS)

def filter_koper(item):
    if looks_like_koper(item.get("snippet", "")):
        return True
    try:
        detail_html = page_html(item["url"])
        txt = BeautifulSoup(detail_html, "html.parser").get_text(" ", strip=True).lower()
        return any(k in txt for k in CITY_KEYWORDS)
    except Exception:
        return False

def send_telegram(text):
    if not (TG_TOKEN and TG_CHAT):
        raise SystemExit("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID.")
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT, "text": text, "disable_web_page_preview": True}
    r = session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    if r.status_code >= 300:
        raise RuntimeError(f"Telegram send failed: {r.status_code} {r.text}")

def notify(item):
    msg = f"🆕 Novo stanovanje (Koper) na MojCimer:\n{item['url']}\n\n{item.get('snippet','')}"
    send_telegram(msg)

def main():
    seen = load_seen()
    listings = extract_listings()
    new = [it for it in listings if it["url"] not in seen and filter_koper(it)]
    for it in new:
        try:
            notify(it)
            time.sleep(1)
        except Exception as e:
            print("Send failed:", e)
        finally:
            seen.add(it["url"])
    save_seen(seen)

if __name__ == "__main__":
    main()
