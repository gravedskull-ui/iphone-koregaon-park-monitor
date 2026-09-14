import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

import requests

APPLE_PART_NUMBER = "MJXV4HN/A"
SEARCH_LOCATION = "411001"
TARGET_STORE = "Apple Koregaon Park"
TARGET_STORE_MATCH = "koregaon park"

APPLE_URL = (
    "https://www.apple.com/in/shop/fulfillment-messages"
    f"?pl=true&searchNearby=true&parts.0={quote(APPLE_PART_NUMBER)}"
    f"&location={quote(SEARCH_LOCATION)}"
    "&purchaseOption=fullPrice&mts.0=regular&mts.1=sticky&fts=true"
)

STATE_FILE = Path("state/status.json")

# Primary notification channel.
ENABLE_NTFY = True

# Optional email channel.
ENABLE_EMAIL = False

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-IN,en;q=0.9",
}


def load_state():
    if not STATE_FILE.exists():
        return {"available": False, "store": None}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"available": False, "store": None}


def save_state(available, store):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(
            {
                "available": available,
                "store": store,
                "part_number": APPLE_PART_NUMBER,
            },
            indent=2,
        )
        + "\n"
    )


def get_store_data():
    response = requests.get(APPLE_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()

    data = response.json()

    # Apple's response has historically appeared under body.content.pickupMessage,
    # while some variants expose stores directly under body. Handle both.
    body = data.get("body", {})
    content = body.get("content", {})
    pickup_message = content.get("pickupMessage", {})
    stores = pickup_message.get("stores")

    if stores is None:
        stores = body.get("stores")

    if not isinstance(stores, list):
        raise RuntimeError("Apple response did not contain a usable stores list.")

    return stores


def find_target_store(stores):
    matches = []

    for store in stores:
        name = str(store.get("storeName", ""))
        address = str(store.get("address", ""))
        number = str(store.get("storeNumber", ""))

        haystack = f"{name} {address}".lower()

        if TARGET_STORE_MATCH in haystack:
            matches.append((store, name, address, number))

    if not matches:
        available_names = [
            f"{s.get('storeName', '')} [{s.get('storeNumber', '')}]"
            for s in stores
        ]
        raise RuntimeError(
            "Target store was not found in Apple's response. "
            f"Stores returned: {available_names}"
        )

    # Prefer an exact store-name match if Apple supplies one.
    exact = [
        x for x in matches
        if x[1].strip().lower() == TARGET_STORE.lower()
    ]
    return exact[0] if exact else matches[0]


def extract_availability(store):
    parts = store.get("partsAvailability", {})
    item = parts.get(APPLE_PART_NUMBER)

    if not isinstance(item, dict):
        raise RuntimeError(
            f"SKU {APPLE_PART_NUMBER} was not present for the target store."
        )

    pickup_display = str(item.get("pickupDisplay", "")).strip().lower()
    title = (
        item.get("storePickupProductTitle")
        or item.get("messageTypes", {})
        .get("regular", {})
        .get("storePickupProductTitle")
        or f"iPhone 18 Pro Max 512GB Burgundy ({APPLE_PART_NUMBER})"
    )
    quote = (
        item.get("pickupSearchQuote")
        or item.get("pickupQuote")
        or item.get("storePickupQuote")
        or ""
    )

    if pickup_display == "available":
        return True, title, quote

    if pickup_display in {"unavailable", "not available", "unavailable today"}:
        return False, title, quote

    raise RuntimeError(
        f"Unexpected pickupDisplay value: {pickup_display!r}"
    )


def send_ntfy(title, message):
    if not ENABLE_NTFY:
        return

    if not NTFY_TOPIC:
        raise RuntimeError("NTFY_TOPIC is not configured.")

    url = f"{NTFY_SERVER}/{quote(NTFY_TOPIC, safe='')}"
    response = requests.post(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "urgent",
            "Tags": "iphone,apple,rotating_light",
            "Click": "https://www.apple.com/in/shop/buy-iphone/iphone-18-pro",
        },
        timeout=15,
    )
    response.raise_for_status()


def send_email(title, message):
    if not ENABLE_EMAIL:
        return

    required = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "ALERT_EMAIL_TO",
        "ALERT_EMAIL_FROM",
    ]

    missing = [x for x in required if not os.environ.get(x)]
    if missing:
        raise RuntimeError(
            "Email enabled but missing environment variables: "
            + ", ".join(missing)
        )

    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = os.environ["ALERT_EMAIL_FROM"]
    msg["To"] = os.environ["ALERT_EMAIL_TO"]
    msg.set_content(message)

    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])

    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        server.login(
            os.environ["SMTP_USERNAME"],
            os.environ["SMTP_PASSWORD"],
        )
        server.send_message(msg)


def notify(store_name, store_number, title, quote):
    message = (
        "🚨 Apple Store Pickup Available!\n\n"
        f"Product: {title}\n"
        "Capacity: 512GB\n"
        "Finish: Burgundy\n"
        f"Store: {store_name}\n"
        f"Store ID: {store_number or 'not supplied'}\n"
        f"Pickup: {quote or 'Available'}\n\n"
        "Buy/check now:\n"
        "https://www.apple.com/in/shop/buy-iphone/iphone-18-pro"
    )

    send_ntfy("🍎 iPhone 18 Pro Max pickup available", message)
    send_email("🍎 iPhone 18 Pro Max pickup available", message)


def main():
    previous = load_state()

    try:
        stores = get_store_data()
        store, store_name, address, store_number = find_target_store(stores)
        available, title, quote = extract_availability(store)

        print(f"Store: {store_name}")
        print(f"Store ID: {store_number}")
        print(f"Address: {address}")
        print(f"Product: {title}")
        print(f"Availability: {'AVAILABLE' if available else 'UNAVAILABLE'}")
        print(f"Pickup message: {quote}")

        previous_available = bool(previous.get("available", False))

        # Notify only on the transition into available.
        if available and not previous_available:
            notify(store_name, store_number, title, quote)
            print("Notification sent.")

        save_state(available, store_number)
        return 0

    except Exception as exc:
        # Unknown is deliberately not written as unavailable.
        # This prevents API blocks/errors from causing false state transitions.
        print(f"CHECK FAILED / UNKNOWN: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
