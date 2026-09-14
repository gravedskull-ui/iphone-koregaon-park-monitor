# iPhone 18 Pro Max — Apple Koregaon Park Pickup Monitor

Monitors Apple's India Store Pickup availability for:

- **Product:** iPhone 18 Pro Max
- **Capacity:** 512 GB
- **Finish:** Burgundy
- **Store:** Apple Koregaon Park, Pune
- **Apple part number:** `MJXV4HN/A`
- **Search PIN:** `411001`
- **Check cadence:** every 5 minutes via GitHub Actions
- **Push notification:** ntfy.sh (iOS app)

## Why this setup

Apple exposes a fulfillment/pickup JSON endpoint used by its store pages. The monitor queries it directly and treats only an explicit `pickupDisplay == "available"` result as in-stock. Errors, missing data, or ambiguous responses are treated as **unknown**, never as "out of stock".

The workflow stores the previous state in `state/status.json`, so you receive a notification when availability changes from unavailable/unknown to available rather than getting spammed every 5 minutes.

## 1. Create the GitHub repository

Create a new GitHub repository. A public repository is simplest because GitHub Actions scheduled workflows are available without GitHub Enterprise.

Upload all files from this project, preserving the `.github/workflows/` directory.

## 2. Create your private ntfy topic

Install the **ntfy** iOS app and subscribe to a unique private-ish topic, for example:

`abhijeet-iphone-kopa-8f3a91`

Do not use a predictable topic name. Anyone who knows an ntfy topic can potentially publish to it.

You can also use a different ntfy server if you prefer.

## 3. Add the GitHub secret

Repository → Settings → Secrets and variables → Actions → New repository secret

Name:

`NTFY_TOPIC`

Value:

your ntfy topic, e.g. `abhijeet-iphone-kopa-8f3a91`

The workflow uses the secret only to send the push notification.

## 4. Run the first check manually

GitHub → Actions → **Apple Pickup Monitor** → Run workflow.

The run should show:

- the Apple API response was successfully queried
- whether Koregaon Park was found
- current pickup state
- product/store details

The first run will establish the baseline. A notification is intentionally sent only when the state transitions into available.

## 5. What happens when stock appears

When Apple reports the exact target SKU as available at Koregaon Park:

1. The workflow detects `available`.
2. It sends a high-priority ntfy push notification.
3. The notification includes the store, product, and pickup message.
4. The state is saved as available.
5. Further 5-minute checks do not spam you while it remains available.
6. Once it goes unavailable again, the state resets.
7. The next availability transition triggers another alert.

## Important limitation

GitHub Actions schedules are **best-effort**, not a hard real-time scheduler. A `*/5 * * * *` schedule means GitHub attempts to run it every five minutes; jobs can occasionally start late because of GitHub Actions scheduling/load.

This is therefore a strong low-cost solution, but it is not a guaranteed 2-minute SLA.

Also, Apple can change or protect its internal fulfillment endpoint. If the endpoint begins returning blocked/invalid data, the monitor will fail safely rather than falsely claiming that stock is unavailable.

## Verify the SKU

The current target SKU is `MJXV4HN/A`, corresponding to iPhone 18 Pro Max 512GB Burgundy in India. If Apple changes regional SKUs, edit `PRODUCT_PART_NUMBER` in `monitor.py`.

## Optional email notifications

The included script supports email through SMTP environment variables, but ntfy is recommended because it gives an immediate iOS push without storing your mailbox password.

Set these GitHub secrets if you want email as well:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `ALERT_EMAIL_TO`
- `ALERT_EMAIL_FROM`

For Gmail, use an App Password rather than your normal Google password.

Then change:

`ENABLE_EMAIL = True`

in `monitor.py`.

## Files

- `monitor.py` — availability checker + ntfy/email notification logic
- `.github/workflows/pickup-monitor.yml` — 5-minute GitHub Actions schedule
- `state/status.json` — previous availability state
- `requirements.txt` — Python dependency
