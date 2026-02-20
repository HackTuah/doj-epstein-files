# DOJ Epstein Archive – "No Images Produced" Dataset Resolver

## Overview

This repository documents the collection and technical analysis of publicly released DOJ Epstein archive materials, specifically entries returned from the search query:

    "no images produced"

The Department of Justice archive frequently serves files labeled with a `.pdf` extension, even when the underlying file type is not a PDF. In many cases, the actual file may be:

- Video (e.g., `.mov`, `.mp4`)
- Audio (e.g., `.m4a`, `.mp3`, `.ogg`, `.opus`)
- Image (e.g., `.jpg`, `.png`)
- Archive (e.g., `.zip`)
- Or another media format

The purpose of this project is to identify and resolve the true file type for each entry in this subset of the archive.

---

## Objectives

1. Collect all DOJ archive links returned from the search query "no images produced".
2. Normalize and store these links as a base dataset.
3. Programmatically determine the actual file type for each entry using:
   - HTTP content-type inspection
   - Byte-level magic signature detection
   - Controlled extension probing
4. Produce a clean dataset mapping each base file ID to its correct extension.

---

## Base Dataset

The initial dataset of URLs extracted from DOJ search results is provided here:

    no_images_produced_links.csv

This file contains the raw URLs exactly as published by the DOJ site.  
Most entries end in `.pdf`, regardless of the true underlying file type.

This dataset serves as the baseline for extension resolution.

---

## Output Dataset

The resolver produces:

    resolved.csv

This file includes:

- base_id
- original URL
- resolved URL
- detected extension
- detected file type (via magic bytes)
- HTTP content-type
- resolution notes

Resolution is performed in staged runs due to rate limiting enforced by the DOJ site.

---

## Technical Approach

The resolver implements:

- Playwright-based session handling to pass age verification and anti-bot controls
- HTTP Range requests (first ~96KB) for efficient byte inspection
- Magic byte detection for common media signatures, including:
  - MP4 / MOV (`ftyp`)
  - M4A
  - OGG / Opus
  - JPEG / PNG / GIF
  - ZIP / RAR / 7z
  - WAV / FLAC
  - PDF
- Tiered extension probing (media-first strategy)
- HTML/gate detection to filter out false-positive 200 responses
- Automatic rate-limit detection and cooldown logic
- Resume support via partial CSV

The DOJ archive frequently returns HTTP 200 responses for:

- Age verification redirects
- HTML "Page Not Found" templates
- Bot-detection responses

As a result, simple extension checks are insufficient.  
This resolver relies on byte-level validation to confirm actual file types.

---

## Operational Constraints

- The DOJ site enforces aggressive rate limiting.
- Session cookies are IP-bound.
- VPN or IP changes invalidate stored session state.
- Headless vs non-headless browser modes may affect fingerprinting behavior.

Resolution runs are staged to avoid triggering perimeter controls.

---

## Disclaimer

All data referenced in this repository originates from publicly released Department of Justice materials.

This repository does not host, modify, or redistribute source files.  
It documents analysis of publicly accessible URLs and file-type resolution methodology.
