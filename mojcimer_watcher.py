import os, json, time, re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------- CONFIG ----------
BASE = "https://www.mojcimer.si"
LIST_URL = BASE + "/seznam-prostih-sob/?page={}"   # pages 1..N
PAGES_TO_SCAN = [1, 2, 3]                          # scan first 3 pages
SEEN_FILE = "seen.json"
CITY_KEYWORDS = ("koper", "capodistria")           # match either, case-insensitive
REQUEST_TIMEOUT = 20
POLITE_DELAY_SECONDS = 1                            # between messages
USER_AGENT = "Mozilla/5.0 (compatible; MojCimerWatcher/1.0)"

# WhatsApp env
load_dotenv()
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_TO = os.getenv("WHATSAPP_TO", "")
WHATSAPP_TEMPLATE_NAME = os.getenv("WHATSAPP_TEMPLATE_NAME", "").strip()
WHATSAPP_TEMPLATE_LANG = os.getenv("WHATSAPP_TEMPLATE_LANG", "en_US").strip() or "en_US"

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

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
    """Scrape listing links + nearby text from listing pages."""
    items = {}
    for p in PAGES_TO_SCAN:
        html = page_html(LIST_URL.format(p))
        soup = BeautifulSoup(html, "html.parser")

        # Grab anchors that lead to detail pages under /seznam-prostih-sob/...
        for a in soup.select('a[href*="/seznam-prostih-sob/"]'):
            href = a.get("href") or ""
            if "/seznam-prostih-sob/" not in href:
                continue
            # Avoid paging/filter links that include '?' without an ID path
            if "?" in href and not href.rstrip("/").split("/")[-1].isdigit():
                continue
            link = href if href.startswith("http") else (BASE + href)

            # make a short text snippet from closest container
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
    """Return True if listing is in Koper (quick check + fallback to detail page)."""
    if looks_like_koper(item.get("snippet", "")):
        return True
    # Fallback: fetch detail page and search anywhere in text
    try:
        detail_html = page_html(item["url"])
        # Strip tags and search for keywords in plain text
        txt = BeautifulSoup(detail_html, "html.parser").get_text(" ", strip=True).lower()
        return any(k in txt for k in CITY_KEYWORDS)
    except Exception:
        return False

def send_whatsapp_text(body):
    endpoint = f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": WHATSAPP_TO,
        "type": "text",
        "text": {"body": body}
    }
    r = session.post(endpoint, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    if r.status_code >= 300:
        raise RuntimeError(f"WhatsApp text failed: {r.status_code} {r.text}")

def send_whatsapp_template(url, snippet):
    endpoint = f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": WHATSAPP_TO,
        "type": "template",
        "template": {
            "name": WHATSAPP_TEMPLATE_NAME,
            "language": {"code": WHATSAPP_TEMPLATE_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": url},
                        {"type": "text", "text": snippet or ""}
                    ]
                }
            ]
        }
    }
    r = session.post(endpoint, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    if r.status_code >= 300:
        raise RuntimeError(f"WhatsApp template failed: {r.status_code} {r.text}")

def notify(item):
    msg = f"🆕 Novo stanovanje (Koper) na MojCimer:\n{item['url']}\n\n{item.get('snippet','')}"
    if WHATSAPP_TEMPLATE_NAME:
        send_whatsapp_template(item["url"], item.get("snippet", ""))
    else:
        # Works only if you recently chatted with the business (24h window).
        send_whatsapp_text(msg)

def main():
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_ID and WHATSAPP_TO):
        raise SystemExit("Missing WhatsApp .env values. Fill WHATSAPP_TOKEN/WHATSAPP_PHONE_ID/WHATSAPP_TO.")

    seen = load_seen()
    listings = extract_listings()
    # Only new + Koper
    new = [it for it in listings if it["url"] not in seen and filter_koper(it)]

    for it in new:
        try:
            notify(it)
            time.sleep(POLITE_DELAY_SECONDS)
        except Exception as e:
            print("Send failed:", e)
        finally:
            seen.add(it["url"])

    save_seen(seen)

if __name__ == "__main__":
    main()
