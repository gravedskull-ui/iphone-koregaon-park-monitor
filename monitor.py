import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

APPLE_PART_NUMBER = "MJXV4HN/A"
APPLE_STORE_NUMBER = "R788"
APPLE_STORE_NAME = "Koregaon Park"

APPLE_URL = (
    "https://www.apple.com/in/shop/retail/pickup-message"
    f"?pl=true"
    f"&mts.0=regular"
    f"&parts.0={quote(APPLE_PART_NUMBER)}"
    f"&store={APPLE_STORE_NUMBER}"
)

STATE_FILE = Path("state/status.json")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_SERVER = os.environ.get(
    "NTFY_SERVER",
    "https://ntfy.sh"
).rstrip("/")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-IN,en;q=0.9",
}


def load_state():
    if not STATE_FILE.exists():
        return {
            "available": False,
            "store": APPLE_STORE_NUMBER
        }

    try:
        return json.loads(
            STATE_FILE.read_text()
        )
    except Exception:
        return {
            "available": False,
            "store": APPLE_STORE_NUMBER
        }


def save_state(available):
    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    STATE_FILE.write_text(
        json.dumps(
            {
                "available": available,
                "store": APPLE_STORE_NUMBER,
                "part_number": APPLE_PART_NUMBER
            },
            indent=2
        ) + "\n"
    )


def get_pickup_status():
    response = requests.get(
        APPLE_URL,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    body = data.get("body", {})
    stores = body.get("stores", [])

    if not stores:
        raise RuntimeError(
            "Apple returned no stores."
        )

    target_store = None

    for store in stores:
        if (
            str(store.get("storeNumber", ""))
            == APPLE_STORE_NUMBER
        ):
            target_store = store
            break

    if target_store is None:
        raise RuntimeError(
            f"Apple did not return store {APPLE_STORE_NUMBER}."
        )

    parts = target_store.get(
        "partsAvailability",
        {}
    )

    product = parts.get(
        APPLE_PART_NUMBER
    )

    if not isinstance(product, dict):
        raise RuntimeError(
            f"SKU {APPLE_PART_NUMBER} "
            "was not returned by Apple."
        )

    pickup_display = str(
        product.get(
            "pickupDisplay",
            ""
        )
    ).strip().lower()

    title = (
        product
        .get("messageTypes", {})
        .get("regular", {})
        .get(
            "storePickupProductTitle",
            "iPhone 18 Pro Max 512GB Burgundy"
        )
    )

    pickup_quote = (
        product.get(
            "pickupSearchQuote",
            ""
        )
    )

    store_pickup_quote = (
        product
        .get("messageTypes", {})
        .get("regular", {})
        .get(
            "storePickupQuote",
            ""
        )
    )

    if pickup_display == "available":
        available = True

    elif pickup_display in (
        "unavailable",
        "ineligible"
    ):
        available = False

    else:
        raise RuntimeError(
            "Unexpected Apple pickupDisplay: "
            f"{pickup_display!r}"
        )

    return {
        "available": available,
        "title": title,
        "pickup_display": pickup_display,
        "pickup_quote": pickup_quote,
        "store_pickup_quote": store_pickup_quote
    }


def send_notification(result):
    if not NTFY_TOPIC:
        raise RuntimeError(
            "NTFY_TOPIC GitHub secret is not configured."
        )

    message = (
        "🚨 Apple Store Pickup Available!\n\n"
        f"Product: {result['title']}\n"
        "Capacity: 512GB\n"
        "Finish: Burgundy\n"
        f"Store: Apple {APPLE_STORE_NAME}\n"
        f"Store ID: {APPLE_STORE_NUMBER}\n"
        f"Pickup: {result['store_pickup_quote']}\n\n"
        "Check Apple immediately:\n"
        "https://www.apple.com/in/shop/buy-iphone/iphone-18-pro"
    )

    url = (
        f"{NTFY_SERVER}/"
        f"{quote(NTFY_TOPIC, safe='')}"
    )

    response = requests.post(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": "🍎 iPhone 18 Pro Max Pickup Available",
            "Priority": "urgent",
            "Tags": "iphone,apple,rotating_light",
            "Click": (
                "https://www.apple.com/in/shop/"
                "buy-iphone/iphone-18-pro"
            )
        },
        timeout=15
    )

    response.raise_for_status()


def main():
    previous = load_state()

    try:
        result = get_pickup_status()

        print(
            f"Store: Apple {APPLE_STORE_NAME}"
        )

        print(
            f"SKU: {APPLE_PART_NUMBER}"
        )

        print(
            f"Product: {result['title']}"
        )

        print(
            "Pickup status: "
            f"{result['pickup_display']}"
        )

        print(
            f"Pickup message: "
            f"{result['store_pickup_quote']}"
        )

        previous_available = bool(
            previous.get("available", False)
        )

        if (
            result["available"]
            and not previous_available
        ):
            send_notification(result)

            print(
                "🚨 Availability detected. "
                "Notification sent."
            )

        elif result["available"]:
            print(
                "Still available. "
                "No duplicate notification sent."
            )

        else:
            print(
                "Currently unavailable."
            )

        save_state(
            result["available"]
        )

        return 0

    except Exception as error:
        print(
            "CHECK FAILED / UNKNOWN: "
            f"{error}",
            file=sys.stderr
        )

        return 2


if __name__ == "__main__":
    sys.exit(main())
