# DOJ Epstein Archive -- "No Images Produced" Dataset

## Overview

This repository documents technical analysis of a subset of publicly
released DOJ Epstein archive materials.

The focus is on files returned from the search query:

    "no images produced"

The DOJ archive frequently serves URLs labeled with a .pdf extension,
even when the underlying file type is not a PDF. In many cases, the
actual content may be:

-   Video (e.g., .mov, .mp4)
-   Audio (e.g., .m4a, .mp3, .ogg, .opus)
-   Image (e.g., .jpg, .png)
-   Archive (e.g., .zip)
-   Or other media formats

This project attempts to programmatically determine the true file type
of each entry using magic byte inspection.

------------------------------------------------------------------------

## Current Status

This is a work-in-progress dataset.

-   The base dataset has been collected.
-   Extension resolution is partially complete.
-   The current resolved.partial.csv reflects staged runs.
-   Some entries remain unresolved due to site rate limiting.
-   Some entries may require additional probing passes.

The CSV currently published is intentionally raw and reflects the actual
state of resolution at the time of upload.

------------------------------------------------------------------------

## Files in This Repository

### no_images_produced_links.csv

The baseline dataset extracted directly from DOJ search results. These
are the raw URLs as published by the DOJ site. Most entries end in .pdf,
regardless of true underlying file type. This file represents the full
base set currently under analysis.

### resolve_extensions.py

The Python script used to bypass WAF protections, probe the URLs, and
determine the true file extensions without fully downloading the massive
media files.

### resolved.partial.csv

A staged resolution dataset. This file includes:

-   base_id
-   original URL
-   base URL (extension stripped)
-   resolution status
-   resolved URL (if found)
-   detected extension
-   detected file type (via magic byte inspection)
-   HTTP content-type
-   resolution notes

Because the DOJ site enforces aggressive rate limiting and anti-bot
controls, resolution must be performed in batches. This dataset will be
updated incrementally as additional passes are completed. The script
automatically reads this file to resume progress.

------------------------------------------------------------------------

## How to Use the Resolver Script

If you wish to run the resolution script yourself to continue probing
unresolved links or apply it to a new dataset, follow these steps.

### 1. Prerequisites

You will need Python 3 installed. Install the required Playwright
libraries:

``` bash
pip install playwright
playwright install chromium
```

### 2. Configuration

Open resolve_extensions.py and ensure the IN_CSV variable points to your
input file (e.g., no_images_produced_links.csv).

### 3. The First Run (Bypassing the Gate)

The DOJ site sits behind a strict Enterprise WAF (Akamai) that requires
a human to clear an age gate and CAPTCHA.

Open the script and ensure HEADLESS = False.

Run the script:

``` bash
python resolve_extensions.py
```

A Chromium browser will open. Manually solve the CAPTCHA and click "Yes"
on the Age Verification screen.

Wait 5 seconds for the page to fully load, then go back to your terminal
and press ENTER.

The script will save your authenticated session cookie to
justice_storage_state.json and begin resolving URLs.

### 4. Resuming Progress

If the script is interrupted or you are temporarily rate-limited, simply
run the script again. It will automatically read resolved.partial.csv,
calculate exactly which files are remaining, and resume where it left
off.

------------------------------------------------------------------------

## Technical Methodology

Resolution is performed using:

-   Playwright-based session handling: To pass age verification,
    generate valid cookies, and spoof standard browser headers.
-   HTTP Range Requests: To retrieve only the initial 64KB of a file,
    saving massive amounts of bandwidth.
-   Magic Byte Inspection: To reliably determine the true file type
    regardless of the server's HTTP headers.
-   Content-Type Validation & Tiered Probing: A media-first guessing
    strategy (.mp4, .mov, etc.).
-   HTML/Gate Detection: To filter false-positive HTTP 200 responses
    caused by soft-404s or WAF redirects.

The DOJ archive frequently returns HTTP 200 responses for age
verification redirects, HTML "Page Not Found" templates, and
bot-detection pages. Therefore, naive extension checks (like standard
requests loops) are insufficient. Byte-level inspection is required.

------------------------------------------------------------------------

## Limitations & WAF Evasion Tips

### IP Binding

Session cookies are strictly bound to your IP address. Changing your VPN
or restarting your router will invalidate justice_storage_state.json,
resulting in HTTP 401/403 errors. If this happens, delete the JSON file
and run the script again to generate a fresh cookie.

### Rate Limiting

The DOJ site enforces strict rate limiting. The script currently
processes 1 file at a time with randomized jitter delays (2.5s - 5.5s)
to mimic human behavior.

### Cellular Hotspots

If your residential IP or VPN is permanently flagged by the WAF,
connecting your machine to a 5G/LTE mobile hotspot often bypasses the
restriction due to high-trust Carrier-Grade NAT (CGNAT) IPs.

------------------------------------------------------------------------

## Disclaimer

All data referenced in this repository originates from publicly released
Department of Justice materials.

This repository does not host, modify, or redistribute source files. It
documents technical analysis and file-type resolution of publicly
accessible URLs for research and archival integrity purposes.

------------------------------------------------------------------------

## .gitignore

Before you run git add . and git commit, make absolutely sure you create
a file named .gitignore in the same folder and add this exact text to
it:

    # Ignore Playwright session cookies (DO NOT COMMIT THIS)
    justice_storage_state.json

    # Ignore Python cache
    __pycache__/
    *.pyc

This ensures your active session cookie stays safely on your machine.
