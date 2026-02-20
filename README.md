# DOJ Epstein Archive – "No Images Produced" Dataset

## Overview

This repository documents technical analysis of a subset of publicly released DOJ Epstein archive materials.

The focus is on files returned from the search query:

    "no images produced"

The DOJ archive frequently serves URLs labeled with a `.pdf` extension, even when the underlying file type is not a PDF. In many cases, the actual content may be:

- Video (e.g., `.mov`, `.mp4`)
- Audio (e.g., `.m4a`, `.mp3`, `.ogg`, `.opus`)
- Image (e.g., `.jpg`, `.png`)
- Archive (e.g., `.zip`)
- Or other media formats

This project attempts to programmatically determine the true file type of each entry.

---

## Current Status

This is a work-in-progress dataset.

- The base dataset has been collected.
- Extension resolution is partially complete.
- The current `resolved.partial.csv` reflects staged runs.
- Some entries remain unresolved due to site rate limiting.
- Some entries may require additional probing passes.

The CSV currently published is intentionally raw and reflects the actual state of resolution at the time of upload.

---

## Files in This Repository

### `no_images_produced_links.csv`

The baseline dataset extracted directly from DOJ search results.

These are the raw URLs as published by the DOJ site.  
Most entries end in `.pdf`, regardless of true underlying file type.

This file represents the full base set currently under analysis.

---

### `resolved.partial.csv`

A staged resolution dataset.

This file includes:

- `base_id`
- original URL
- base URL (extension stripped)
- resolution status
- resolved URL (if found)
- detected extension
- detected file type (via magic byte inspection)
- HTTP content-type
- resolution notes

Because the DOJ site enforces aggressive rate limiting and anti-bot controls, resolution must be performed in batches. As a result:

- Some rows are complete.
- Some rows are marked as rate-limited.
- Some rows remain unresolved.

This dataset will be updated incrementally as additional passes are completed.

---

## Technical Methodology

Resolution is performed using:

- Playwright-based session handling (to pass age verification and bot controls)
- HTTP Range requests to retrieve only initial bytes
- Magic byte inspection for file-type detection
- Content-Type validation
- Tiered extension probing (media-first strategy)
- HTML/gate detection to filter false-positive 200 responses
- Automatic rate-limit detection and cooldown logic
- Resume support via partial CSV

The DOJ archive frequently returns HTTP 200 responses for:

- Age verification redirects
- HTML "Page Not Found" templates
- Bot-detection pages

Therefore, naive extension checks are insufficient.  
Byte-level inspection is required to determine actual file type.

---

## Limitations

- The DOJ site enforces rate limiting.
- Session cookies are IP-bound.
- VPN/IP changes invalidate session state.
- Headless browser fingerprinting may affect stability.
- Some entries may only exist as placeholder documents.

Resolution runs are staged to avoid triggering perimeter controls.

---

## Disclaimer

All data referenced in this repository originates from publicly released Department of Justice materials.

This repository does not host, modify, or redistribute source files.  
It documents technical analysis and file-type resolution of publicly accessible URLs.
