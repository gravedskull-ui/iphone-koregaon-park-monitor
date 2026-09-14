import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests


# ============================================================
# TARGET CONFIGURATION
# ============================================================

APPLE_PART_NUMBER = "MJXV4HN/A"
APPLE_STORE_NUMBER = "R788"
APPLE_STORE_NAME = "Koregaon Park"

PRODUCT_NAME = "iPhone 18 Pro Max"
CAPACITY = "512GB"
FINISH = "Burgundy"


# ============================================================
# APPLE PICKUP API
# ============================================================

APPLE_URL = (
    "https://www.apple.com/in/shop/retail/pickup-message"
    f"?pl=true"
    f"&mts.0=regular"
    f"&parts.0={quote(APPLE_PART_NUMBER)}"
    f"&store={APPLE_STORE_NUMBER}"
)


# ============================================================
# LOCAL STATE
# ============================================================

STATE_FILE = Path("state/status.json")


# ============================================================
# NOTIFICATION CONFIGURATION
# ============================================================

NTFY_TOPIC = os.environ.get(
    "NTFY_TOPIC",
    ""
).strip()

NTFY_SERVER = os.environ.get(
    "NTFY_SERVER",
    "https://ntfy.sh"
).rstrip("/")


# GitHub Actions sends this as "true" when the
# manual "Send a test notification to ntfy"
# checkbox is selected.

TEST_NOTIFICATION = (
    os.environ.get(
        "TEST_NOTIFICATION",
        "false"
    ).lower()
    == "true"
)


# ============================================================
# HTTP CONFIGURATION
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/json, "
        "text/plain, "
        "*/*"
    ),
    "Accept-Language": (
        "en-IN,en;q=0.9"
    ),
    "Referer": (
        "https://www.apple.com/in/"
    ),
}


# ============================================================
# STATE MANAGEMENT
# ============================================================

def load_state():
    """
    Load the previous availability state.

    If no valid state exists, assume unavailable.

    This is important because the first successful check
    should establish a baseline rather than immediately
    generating an availability notification.
    """

    if not STATE_FILE.exists():
        return {
            "available": False,
            "store": APPLE_STORE_NUMBER,
            "part_number": APPLE_PART_NUMBER
        }

    try:
        state = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(state, dict):
            raise ValueError(
                "State file is not a JSON object."
            )

        return state

    except Exception as error:
        print(
            "WARNING: Could not read state file. "
            f"Starting with unavailable baseline. "
            f"Reason: {error}"
        )

        return {
            "available": False,
            "store": APPLE_STORE_NUMBER,
            "part_number": APPLE_PART_NUMBER
        }


def save_state(available):
    """
    Save the current availability state.

    Only successful Apple checks call this function.
    API failures therefore never overwrite a previously
    known state with 'unavailable'.
    """

    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    state = {
        "available": bool(available),
        "store": APPLE_STORE_NUMBER,
        "part_number": APPLE_PART_NUMBER
    }

    STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )


# ============================================================
# APPLE PICKUP CHECK
# ============================================================

def get_pickup_status():
    """
    Query Apple's current pickup API and return the
    availability information for the exact target SKU
    and store.
    """

    last_error = None

    # Small retry mechanism for transient Apple/API errors.
    for attempt in range(1, 4):

        try:

            print(
                f"Checking Apple pickup API "
                f"(attempt {attempt}/3)..."
            )

            response = requests.get(
                APPLE_URL,
                headers=HEADERS,
                timeout=20
            )

            print(
                f"Apple API HTTP status: "
                f"{response.status_code}"
            )

            response.raise_for_status()

            data = response.json()

            body = data.get(
                "body",
                {}
            )

            stores = body.get(
                "stores",
                []
            )

            if not stores:
                raise RuntimeError(
                    "Apple returned no stores."
                )

            # ------------------------------------------------
            # Find exact Koregaon Park store
            # ------------------------------------------------

            target_store = None

            for store in stores:

                store_number = str(
                    store.get(
                        "storeNumber",
                        ""
                    )
                )

                if (
                    store_number
                    == APPLE_STORE_NUMBER
                ):
                    target_store = store
                    break

            if target_store is None:
                raise RuntimeError(
                    "Apple did not return "
                    f"store {APPLE_STORE_NUMBER} "
                    f"({APPLE_STORE_NAME})."
                )

            # ------------------------------------------------
            # Find exact product SKU
            # ------------------------------------------------

            parts = target_store.get(
                "partsAvailability",
                {}
            )

            product = parts.get(
                APPLE_PART_NUMBER
            )

            if not isinstance(
                product,
                dict
            ):
                raise RuntimeError(
                    "Apple did not return SKU "
                    f"{APPLE_PART_NUMBER} "
                    f"for {APPLE_STORE_NAME}."
                )

            # ------------------------------------------------
            # Pickup availability
            # ------------------------------------------------

            pickup_display = str(
                product.get(
                    "pickupDisplay",
                    ""
                )
            ).strip().lower()

            # ------------------------------------------------
            # Product title
            # ------------------------------------------------

            message_types = product.get(
                "messageTypes",
                {}
            )

            regular_message = message_types.get(
                "regular",
                {}
            )

            title = regular_message.get(
                "storePickupProductTitle",
                f"{PRODUCT_NAME} "
                f"{CAPACITY} "
                f"{FINISH}"
            )

            # ------------------------------------------------
            # Pickup messages
            # ------------------------------------------------

            pickup_quote = product.get(
                "pickupSearchQuote",
                ""
            )

            store_pickup_quote = (
                regular_message.get(
                    "storePickupQuote",
                    ""
                )
            )

            # ------------------------------------------------
            # Interpret availability
            # ------------------------------------------------

            if pickup_display == "available":

                available = True

            elif pickup_display in (
                "unavailable",
                "ineligible"
            ):

                available = False

            else:

                raise RuntimeError(
                    "Unexpected Apple "
                    "pickupDisplay value: "
                    f"{pickup_display!r}"
                )

            return {
                "available": available,
                "title": title,
                "pickup_display": pickup_display,
                "pickup_quote": pickup_quote,
                "store_pickup_quote": (
                    store_pickup_quote
                ),
                "store_name": (
                    target_store.get(
                        "storeName",
                        f"Apple {APPLE_STORE_NAME}"
                    )
                ),
                "store_number": (
                    target_store.get(
                        "storeNumber",
                        APPLE_STORE_NUMBER
                    )
                )
            }

        except Exception as error:

            last_error = error

            print(
                f"Attempt {attempt} failed: "
                f"{error}"
            )

            if attempt < 3:

                print(
                    "Waiting 2 seconds "
                    "before retry..."
                )

                time.sleep(2)

    raise RuntimeError(
        "Apple pickup check failed after "
        f"3 attempts. Last error: {last_error}"
    )


# ============================================================
# NTFY COMMON SENDER
# ============================================================

def send_ntfy(
    title,
    message,
    priority="high",
    tags="iphone,apple"
):
    """
    Send a push notification through ntfy.
    """

    if not NTFY_TOPIC:

        raise RuntimeError(
            "NTFY_TOPIC GitHub secret is not configured."
        )

    url = (
        f"{NTFY_SERVER}/"
        f"{quote(NTFY_TOPIC, safe='')}"
    )

    response = requests.post(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": priority,
            "Tags": tags,
        },
        timeout=15
    )

    response.raise_for_status()

    return response


# ============================================================
# TEST NOTIFICATION
# ============================================================

def send_test_notification():
    """
    Send a test notification without contacting Apple.

    This is deliberately independent from the Apple
    availability check.
    """

    print(
        "🧪 Test notification mode enabled."
    )

    message = (
        "✅ Apple Pickup Monitor Test\n\n"

        "This is a TEST notification.\n\n"

        "The monitoring system successfully "
        "connected to ntfy.\n\n"

        "Target:\n"
        f"{PRODUCT_NAME}\n"
        f"{CAPACITY}\n"
        f"{FINISH}\n"
        f"Apple {APPLE_STORE_NAME}, Pune\n\n"

        "No Apple availability check was "
        "performed during this test.\n"

        "No purchase or reservation action "
        "was performed."
    )

    send_ntfy(
        title="🧪 Apple Pickup Monitor Test",
        message=message,
        priority="high",
        tags="test,iphone,apple"
    )

    print(
        "✅ TEST NOTIFICATION SENT SUCCESSFULLY"
    )


# ============================================================
# REAL AVAILABILITY NOTIFICATION
# ============================================================

def send_notification(result):
    """
    Send an urgent notification when the target
    iPhone becomes available for pickup.
    """

    pickup_message = (
        result.get(
            "store_pickup_quote",
            ""
        )
        or result.get(
            "pickup_quote",
            ""
        )
        or "Available for pickup"
    )

    message = (
        "🚨 iPHONE PICKUP AVAILABLE 🚨\n\n"

        f"Product: {result['title']}\n"
        f"Capacity: {CAPACITY}\n"
        f"Finish: {FINISH}\n\n"

        f"Store: Apple {APPLE_STORE_NAME}\n"
        f"Store ID: {APPLE_STORE_NUMBER}\n\n"

        f"Pickup: {pickup_message}\n\n"

        "⚡ Check Apple immediately:\n"
        "https://www.apple.com/in/shop/"
        "buy-iphone/iphone-18-pro"
    )

    send_ntfy(
        title=(
            "🚨 iPhone 18 Pro Max "
            "Pickup Available!"
        ),
        message=message,
        priority="urgent",
        tags=(
            "iphone,apple,"
            "rotating_light"
        )
    )

    print(
        "🚨 AVAILABILITY NOTIFICATION "
        "SENT SUCCESSFULLY"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Test mode MUST be checked BEFORE the Apple API.
    #
    # This makes the notification test independent from
    # Apple's availability/API.
    # --------------------------------------------------------

    if TEST_NOTIFICATION:

        try:

            send_test_notification()

            print(
                "✅ Test notification completed."
            )

            return 0

        except Exception as error:

            print(
                "❌ TEST NOTIFICATION FAILED: "
                f"{error}",
                file=sys.stderr
            )

            return 2


    # --------------------------------------------------------
    # Normal monitoring mode
    # --------------------------------------------------------

    previous = load_state()

    previous_available = bool(
        previous.get(
            "available",
            False
        )
    )

    print(
        "========================================"
    )

    print(
        "🍎 Apple iPhone Pickup Monitor"
    )

    print(
        "========================================"
    )

    print(
        f"Product: "
        f"{PRODUCT_NAME}"
    )

    print(
        f"Capacity: "
        f"{CAPACITY}"
    )

    print(
        f"Finish: "
        f"{FINISH}"
    )

    print(
        f"Store: "
        f"Apple {APPLE_STORE_NAME}"
    )

    print(
        f"Store ID: "
        f"{APPLE_STORE_NUMBER}"
    )

    print(
        f"SKU: "
        f"{APPLE_PART_NUMBER}"
    )

    print(
        f"Previous availability: "
        f"{previous_available}"
    )

    print(
        "========================================"
    )


    try:

        # ----------------------------------------------------
        # Check Apple
        # ----------------------------------------------------

        result = get_pickup_status()


        # ----------------------------------------------------
        # Print result
        # ----------------------------------------------------

        print(
            f"Store: "
            f"{result['store_name']}"
        )

        print(
            f"SKU: "
            f"{APPLE_PART_NUMBER}"
        )

        print(
            f"Product: "
            f"{result['title']}"
        )

        print(
            "Pickup status: "
            f"{result['pickup_display']}"
        )

        print(
            "Pickup message: "
            f"{result['store_pickup_quote']}"
        )


        # ----------------------------------------------------
        # Availability transition detection
        # ----------------------------------------------------

        current_available = bool(
            result["available"]
        )


        # ----------------------------------------------------
        # UNAVAILABLE → AVAILABLE
        # ----------------------------------------------------

        if (
            current_available
            and not previous_available
        ):

            print(
                "🚨 STATUS CHANGED:"
            )

            print(
                "UNAVAILABLE → AVAILABLE"
            )

            send_notification(
                result
            )


        # ----------------------------------------------------
        # STILL AVAILABLE
        # ----------------------------------------------------

        elif current_available:

            print(
                "🟢 Still available."
            )

            print(
                "No duplicate notification "
                "will be sent."
            )


        # ----------------------------------------------------
        # UNAVAILABLE
        # ----------------------------------------------------

        else:

            print(
                "🔴 Currently unavailable."
            )


        # ----------------------------------------------------
        # Save only after successful Apple check
        # ----------------------------------------------------

        save_state(
            current_available
        )

        print(
            "✅ State saved successfully."
        )

        print(
            "Monitoring check completed."
        )

        return 0


    except Exception as error:

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # We DO NOT save "unavailable" here.
        #
        # An API failure must never be interpreted as
        # the phone being unavailable.
        # ----------------------------------------------------

        print(
            "========================================"
        )

        print(
            "❌ CHECK FAILED / UNKNOWN"
        )

        print(
            str(error)
        )

        print(
            "Previous availability state "
            "has NOT been changed."
        )

        print(
            "========================================"
        )

        return 2


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(
        main()
    )
