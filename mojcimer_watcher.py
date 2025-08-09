import os, json, time
import requests
from bs4 import BeautifulSoup

BASE = "https://www.mojcimer.si"
LIST_URL = BASE + "/seznam-prostih-sob/?page={}"
PAGES_TO_SCAN = [1, 2, 3]
SEEN_FILE = "seen.json"
CITY_KEYWORDS = ("koper", "capodistria")
REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; MojCimerWatcher/1.0)"

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
    items = {}
    for p in PAGES_TO_SCAN:
        html = page_html(LIST_URL.format(p))
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a[href*="/seznam-prostih-sob/"]'):
            href = a.get("href") or ""
            if "/seznam-prostih-sob/" not in href:
                continue
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

def send_whatsapp_text(body):
    phone_id = os.environ["WHATSAPP_PHONE_ID"]
    token = os.environ["WHATSAPP_TOKEN"]
    to = os.environ["WHATSAPP_TO"]
    endpoint = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp","to": to,"type": "text","text": {"body": body}}
    r = session.post(endpoint, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    if r.status_code >= 300:
        raise RuntimeError(f"WhatsApp text failed: {r.status_code} {r.text}")

def send_whatsapp_template(url, snippet):
    phone_id = os.environ["WHATSAPP_PHONE_ID"]
    token = os.environ["WHATSAPP_TOKEN"]
    to = os.environ["WHATSAPP_TO"]
    tmpl = os.getenv("WHATSAPP_TEMPLATE_NAME", "").strip()
    lang = os.getenv("WHATSAPP_TEMPLATE_LANG", "en_US").strip() or "en_US"
    endpoint = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": tmpl,
            "language": {"code": lang},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": url},
                    {"type": "text", "text": snippet or ""}
                ]
            }]
        }
    }
    r = session.post(endpoint, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    if r.status_code >= 300:
        raise RuntimeError(f"WhatsApp template failed: {r.status_code} {r.text}")

def notify(item):
    msg = f"🆕 Novo stanovanje (Koper) na MojCimer:\n{item['url']}\n\n{item.get('snippet','')}"
    if os.getenv("WHATSAPP_TEMPLATE_NAME"):
        send_whatsapp_template(item["url"], item.get("snippet",""))
    else:
        send_whatsapp_text(msg)

def main():
    required = ["WHATSAPP_TOKEN","WHATSAPP_PHONE_ID","WHATSAPP_TO"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing secrets: {', '.join(missing)}")

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
