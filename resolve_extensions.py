#!/usr/bin/env python3
import csv
import os
import re
import time
import urllib.parse as up
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# -----------------------------
# CONFIGURATION
# -----------------------------
# Place your input CSV in the same directory as this script, or update this path.
# The CSV must have a column named "url" containing the base links.
IN_CSV = "input_links.csv" 

# Directory where output files and session state will be saved (default: current directory)
OUT_DIR = Path(".") 

OUT_CSV = OUT_DIR / "resolved_links.csv"
PARTIAL_CSV = OUT_DIR / "resolved_links.partial.csv"

# Saves session state so you only have to solve the captcha/age gate once
STORAGE_STATE = OUT_DIR / "justice_storage_state.json"

# IMPORTANT: Keep HEADLESS = False for the very first run so the browser pops up 
# and allows you to manually solve the Cloudflare/Akamai gate. 
# Once STORAGE_STATE is saved successfully, you can change this to True.
HEADLESS = False           
TIMEOUT_MS = 30_000
THROTTLE_SEC = 0.01

# How many bytes to fetch per candidate (enough to detect file type reliably)
RANGE_BYTES = 64 * 1024
RANGE_HEADER = {"Range": f"bytes=0-{RANGE_BYTES-1}"}

# Candidate extensions to try (ordered by likelihood)
# Note: "pdf" is intentionally excluded to prevent false-positive HTML matches.
CANDIDATE_EXTS = [
    # Tier 1: The most common hits
    "mov", "mp4", "m4a", "mp3", "ogg", "opus",
    "jpg", "jpeg", "png", "gif", "webp", "zip", "7z", "rar",
    
    # Tier 2: Broader A/V and Archives
    "m4v", "webm", "mkv", "avi", "mpg", "mpeg", "3gp", "3g2", "flv",
    "aac", "wav", "flac", "oga", "wma", "aif", "aiff",
    "tif", "tiff", "bmp", "avif", "heic",
    "tar", "gz", "tgz", "bz2", "xz",
    
    # Tier 3: Documents and Data
    "txt", "csv", "tsv", "json", "xml", "html", "htm", "md", "log",
    "doc", "docx", "rtf", "odt", "xls", "xlsx", "ods", "ppt", "pptx", "odp",
]

# Autosave every N unique bases
AUTOSAVE_EVERY = 50

# Optional caps while testing (set to None for full run)
MAX_UNIQUE_BASES = None   
MAX_ROWS = None           

# -----------------------------
# URL helpers
# -----------------------------
def normalize_url(u: str) -> str:
    """Percent-encode spaces etc while preserving existing % escapes."""
    u = (u or "").strip()
    if not u:
        return ""
    s = up.urlsplit(u)
    path = up.quote(s.path, safe="/%")
    query = up.quote_plus(s.query, safe="=&%")
    return up.urlunsplit((s.scheme, s.netloc, path, query, s.fragment))

def strip_extension(u: str) -> str:
    """Remove trailing .ext from URL path."""
    u = normalize_url(u)
    return re.sub(r"\.[A-Za-z0-9]{1,6}($|\?)", "", u)

def get_base_id(base_url: str) -> str:
    return base_url.rstrip("/").split("/")[-1]

# -----------------------------
# Response classification
# -----------------------------
HTML_PREFIXES = (b"<!doctype html", b"<html", b"<head", b"<body")
HTML_SNIPPET_TOKENS = [
    b"page not found",
    b"not found",
    b"404",
    b"access denied",
    b"are you 18 years of age or older",
    b"age verify",
    b"verify your age",
]

def looks_like_age_verify_url(url: str) -> bool:
    return "age-verify" in (url or "").lower()

def short_ct(headers: Dict[str, str]) -> str:
    return (headers.get("content-type") or "").split(";")[0].strip().lower()

def looks_like_html(body: bytes, ct: str, final_url: str) -> bool:
    if looks_like_age_verify_url(final_url):
        return True
    if "text/html" in (ct or ""):
        return True
    b = body.lstrip()[:2048].lower()
    if any(b.startswith(p) for p in HTML_PREFIXES):
        return True
    for tok in HTML_SNIPPET_TOKENS:
        if tok in b:
            return True
    return False

def detect_magic(body: bytes) -> Tuple[str, str]:
    b = body[:64]

    if b.startswith(b"PK\x03\x04"):
        return ("zip", "zip")
    if b.startswith(b"Rar!\x1a\x07\x00") or b.startswith(b"Rar!\x1a\x07\x01\x00"):
        return ("rar", "rar")
    if b.startswith(b"7z\xbc\xaf\x27\x1c"):
        return ("7z", "7z")
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("image", "png")
    if b.startswith(b"\xff\xd8\xff"):
        return ("image", "jpg")
    if b.startswith(b"GIF87a") or b.startswith(b"GIF89a"):
        return ("image", "gif")
    if b.startswith(b"RIFF") and body[8:12] == b"WAVE":
        return ("audio", "wav")
    if b.startswith(b"ID3") or (len(b) > 1 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0):
        return ("audio", "mp3")

    if len(body) >= 12 and body[4:8] == b"ftyp":
        brand = body[8:12]
        if brand in (b"M4A ", b"M4B ", b"m4a ", b"f4a "):
            return ("audio", "m4a")
        if brand == b"qt  ":
            return ("video", "mov")
        return ("video_or_audio", "mp4")

    if b.startswith(b"OggS"):
        return ("audio", "ogg")
    if b.startswith(b"fLaC"):
        return ("audio", "flac")
    if b.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return ("image", "webp")

    sample = body[:256]
    if sample and all((c in b"\t\r\n" or 32 <= c <= 126) for c in sample):
        return ("text", "txt")

    return ("unknown", "")

def is_real_file(body: bytes, ct: str, final_url: str) -> bool:
    if looks_like_html(body, ct, final_url):
        return False
    kind, _ = detect_magic(body)
    if kind != "unknown":
        return True
    if ct and ("text/html" not in ct) and len(body) > 0:
        return True
    return False

# -----------------------------
# Data structures
# -----------------------------
@dataclass
class ResolvedRow:
    input_url: str
    base: str
    found: bool
    resolved_url: str = ""
    resolved_ext: str = ""
    detected_kind: str = ""
    content_type: str = ""
    http_status: str = ""
    note: str = ""

# -----------------------------
# IO
# -----------------------------
def read_input_urls(path: str) -> List[str]:
    urls = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            u = normalize_url(row["url"])
            if u:
                urls.append(u)
    if MAX_ROWS is not None:
        urls = urls[:MAX_ROWS]
    return urls

def write_output_csv(path: Path, rows: List[ResolvedRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "input_url", "base", "found", "resolved_url",
                "resolved_ext", "detected_kind", "content_type",
                "http_status", "note",
            ],
        )
        w.writeheader()
        for row in rows:
            w.writerow(row.__dict__)

def load_partial_rows(path: Path) -> List[ResolvedRow]:
    rows = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(ResolvedRow(
                input_url=row.get("input_url", ""),
                base=row.get("base", ""),
                found=str(row.get("found", "")).strip().lower() in ("true", "1", "yes", "y"),
                resolved_url=row.get("resolved_url", ""),
                resolved_ext=row.get("resolved_ext", ""),
                detected_kind=row.get("detected_kind", ""),
                content_type=row.content_type if hasattr(row, 'content_type') else row.get("content_type", ""),
                http_status=row.http_status if hasattr(row, 'http_status') else row.get("http_status", ""),
                note=row.get("note", "")
            ))
    return rows

# -----------------------------
# Session setup
# -----------------------------
def ensure_session(page, context):
    page.goto("https://www.justice.gov/epstein/search", wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    print("\nBrowser opened.")
    print("Do this in the browser window if prompted:")
    print("  1) 'I'm not a robot' / captcha")
    print("  2) Age verify 'Yes'")
    input("\nWhen done, press ENTER here to continue... ")
    context.storage_state(path=str(STORAGE_STATE))
    print(f"[+] Saved session state: {STORAGE_STATE}\n")

# -----------------------------
# Core resolution
# -----------------------------
def fetch_probe(page, url: str) -> Tuple[str, str, bytes, str]:
    resp = page.request.get(url, headers=RANGE_HEADER, timeout=TIMEOUT_MS)
    final_url = resp.url
    ct = short_ct(resp.headers)
    body = resp.body()
    status = str(resp.status)
    return final_url, ct, body, status

def resolve_base(page, base: str) -> Tuple[bool, str, str, str, str, str]:
    best_candidate = None

    for ext in CANDIDATE_EXTS:
        candidate = f"{base}.{ext}"
        try:
            final_url, ct, body, status = fetch_probe(page, candidate)
        except Exception:
            time.sleep(THROTTLE_SEC)
            continue

        if not is_real_file(body, ct, final_url):
            time.sleep(THROTTLE_SEC)
            continue

        kind, suggested_ext = detect_magic(body)

        score = 0
        if suggested_ext and suggested_ext == ext:
            score += 3
        if kind != "unknown":
            score += 2
        if ct and ("application" in ct or "audio" in ct or "video" in ct or "image" in ct):
            score += 1

        best_candidate = (score, final_url, ext, kind, ct, status, suggested_ext)
        if score >= 5:
            break

        time.sleep(THROTTLE_SEC)

    if not best_candidate:
        return (False, "", "", "", "", "")

    _, final_url, ext, kind, ct, status, suggested_ext = best_candidate
    resolved_ext = suggested_ext if suggested_ext else ext
    return (True, final_url, resolved_ext, kind, ct, status)

# -----------------------------
# MAIN
# -----------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    input_urls = read_input_urls(IN_CSV)
    if not input_urls:
        raise RuntimeError("No URLs found in input CSV.")

    bases = []
    seen = set()
    for u in input_urls:
        b = strip_extension(u)  
        if b not in seen:
            seen.add(b)
            bases.append(b)

    existing_rows = load_partial_rows(PARTIAL_CSV)
    done_bases = {r.base for r in existing_rows if r.base}
    
    remaining_bases = [b for b in bases if b not in done_bases]
    
    if MAX_UNIQUE_BASES is not None:
        remaining_bases = remaining_bases[:MAX_UNIQUE_BASES]

    print(f"Input rows: {len(input_urls)}")
    print(f"Already done: {len(done_bases)}")
    print(f"Remaining bases to resolve: {len(remaining_bases)}")
    print(f"Output: {OUT_CSV}\n")

    base_to_inputs: Dict[str, List[str]] = {}
    for u in input_urls:
        b = strip_extension(u)
        base_to_inputs.setdefault(b, []).append(u)

    base_cache: Dict[str, ResolvedRow] = {}
    rows_out: List[ResolvedRow] = existing_rows

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx_kwargs = {}
        if STORAGE_STATE.exists():
            ctx_kwargs["storage_state"] = str(STORAGE_STATE)

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        if not STORAGE_STATE.exists():
            ensure_session(page, context)

        for idx, base in enumerate(remaining_bases, 1):
            base_id = get_base_id(base)

            if base in base_cache:
                cached = base_cache[base]
                for inp in base_to_inputs.get(base, [cached.input_url]):
                    rows_out.append(ResolvedRow(**{**cached.__dict__, "input_url": inp}))
                continue

            found, resolved_url, resolved_ext, kind, ct, status = resolve_base(page, base)

            if found:
                note = "ok"
                print(f"[{idx}/{len(remaining_bases)}] ✅ {base_id} -> .{resolved_ext} ({kind}, {ct})")
            else:
                note = "no real file detected (likely HTML 'page not found' for all candidates, or gated)"
                print(f"[{idx}/{len(remaining_bases)}] ❌ {base_id} -> (no hit)")

            template_row = ResolvedRow(
                input_url=base_to_inputs.get(base, [""])[0],
                base=base,
                found=found,
                resolved_url=resolved_url,
                resolved_ext=resolved_ext,
                detected_kind=kind,
                content_type=ct,
                http_status=status,
                note=note,
            )

            base_cache[base] = template_row

            for inp in base_to_inputs.get(base, [template_row.input_url]):
                rows_out.append(ResolvedRow(**{**template_row.__dict__, "input_url": inp}))

            if idx % AUTOSAVE_EVERY == 0:
                write_output_csv(PARTIAL_CSV, rows_out)
                context.storage_state(path=str(STORAGE_STATE))
                print(f"    [*] autosaved: {PARTIAL_CSV}")

        write_output_csv(OUT_CSV, rows_out)
        context.storage_state(path=str(STORAGE_STATE))

        context.close()
        browser.close()

    print(f"\nDone. Wrote: {OUT_CSV}")
    print(f"Session state: {STORAGE_STATE}")
    print("Tip: Once STORAGE_STATE works reliably, set HEADLESS=True for faster runs.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Script stopped manually by user. Progress was saved incrementally.")
