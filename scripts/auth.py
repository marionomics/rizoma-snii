"""
auth.py — shared authentication helper for all rizoma scripts.

Tries the saved session first. If expired (401), re-authenticates
using credentials from .env via Playwright and saves the new session.

Usage:
    from auth import get_headers
    hdrs = get_headers()   # always returns valid headers or raises SystemExit
"""

import json
import ssl
import sys
import os
import urllib.request
import urllib.error
from pathlib import Path

ROOT         = Path(__file__).parent.parent
SESSION_FILE = ROOT / "session" / "session_state.json"
ENV_FILE     = ROOT / ".env"
BASE         = "https://rizoma.conahcyt.mx"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode    = ssl.CERT_NONE


# ── .env loader ────────────────────────────────────────────────────────────────

def load_env() -> dict:
    """Read KEY=VALUE pairs from .env file."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    # Also allow actual environment variables to override
    for key in ("RIZOMA_USER", "RIZOMA_PASSWORD"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


# ── Session helpers ────────────────────────────────────────────────────────────

def _build_headers(cookies: dict) -> dict:
    keep = {k: cookies[k] for k in
            ("SESSION", "XSRF-TOKEN", "_TRAEFIK_BACKEND",
             "visid_incap_2926100", "incap_ses_1705_2926100")
            if k in cookies}
    return {
        "Cookie":       "; ".join(f"{k}={v}" for k, v in keep.items()),
        "X-XSRF-TOKEN": cookies.get("XSRF-TOKEN", ""),
        "Content-Type": "application/json",
        "Accept":       "application/json, text/plain, */*",
        "Origin":       BASE,
        "Referer":      f"{BASE}/trayectoria-profesional",
    }

def _load_session() -> dict | None:
    """Load cookies from saved session file. Returns None if file missing."""
    if not SESSION_FILE.exists():
        return None
    state = json.loads(SESSION_FILE.read_text())
    return {c["name"]: c["value"] for c in state.get("cookies", [])}

def _is_valid(headers: dict) -> bool:
    """Probe a lightweight endpoint to check if the session is still alive."""
    try:
        req = urllib.request.Request(
            f"{BASE}/services/msperfil/api/perfil/cambiopassword",
            headers=headers
        )
        with urllib.request.urlopen(req, context=_CTX, timeout=8) as r:
            return r.status == 200
    except Exception:
        return False


# ── Playwright login ───────────────────────────────────────────────────────────

def _login(username: str, password: str) -> dict:
    """Run a headless Playwright login and return the fresh cookies dict."""
    try:
        import asyncio
        from playwright.async_api import async_playwright
    except ImportError:
        print("  ✗ playwright not installed — run: pip3 install playwright --break-system-packages")
        print("                                      python3 -m playwright install chromium")
        sys.exit(1)

    async def _do_login():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page    = await context.new_page()

            print("  → Navigating to Rizoma...")
            await page.goto(BASE, wait_until="networkidle", timeout=30000)

            # Click login button
            for sel in ['a:has-text("Iniciar sesión")', 'button:has-text("Iniciar sesión")',
                        'a[href*="login"]', 'a[href*="oauth"]']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1500):
                        async with page.expect_navigation(wait_until="networkidle", timeout=15000):
                            await el.click()
                        break
                except Exception:
                    continue

            # Fill Keycloak form
            print("  → Filling credentials...")
            for sel in ['input[name="username"]', 'input[id="username"]', 'input[type="email"]']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.fill(username)
                        break
                except Exception:
                    continue

            for sel in ['input[name="password"]', 'input[id="password"]', 'input[type="password"]']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.fill(password)
                        break
                except Exception:
                    continue

            # Submit
            for sel in ['input[type="submit"]', 'button[type="submit"]',
                        'button:has-text("Acceder")', 'button:has-text("Iniciar")']:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1000):
                        await el.click()
                        break
                except Exception:
                    continue

            # Wait for redirect back to Rizoma
            try:
                await page.wait_for_url("*rizoma.conahcyt.mx*", timeout=20000)
            except Exception:
                pass
            await page.wait_for_timeout(3000)

            # Save session
            SESSION_FILE.parent.mkdir(exist_ok=True)
            await context.storage_state(path=str(SESSION_FILE))
            await browser.close()

            state   = json.loads(SESSION_FILE.read_text())
            cookies = {c["name"]: c["value"] for c in state.get("cookies", [])}
            return cookies

    return asyncio.run(_do_login())


# ── Public API ─────────────────────────────────────────────────────────────────

def get_headers() -> dict:
    """
    Return valid HTTP headers for Rizoma API calls.
    Automatically re-authenticates from .env if session is missing or expired.
    """
    # 1. Try existing session
    cookies = _load_session()
    if cookies and "SESSION" in cookies:
        hdrs = _build_headers(cookies)
        if _is_valid(hdrs):
            return hdrs
        print("  ⚠ Session expired — re-authenticating...")
    else:
        print("  ⚠ No session found — authenticating...")

    # 2. Load credentials
    env = load_env()
    username = env.get("RIZOMA_USER", "").strip()
    password = env.get("RIZOMA_PASSWORD", "").strip()

    if not username or not password:
        print("  ✗ RIZOMA_USER / RIZOMA_PASSWORD not set in .env")
        sys.exit(1)

    # 3. Login via Playwright
    print(f"  → Logging in as {username}...")
    cookies = _login(username, password)

    if "SESSION" not in cookies:
        print("  ✗ Login failed — SESSION cookie not found after auth")
        print("    Check credentials in .env")
        sys.exit(1)

    print("  ✓ Authenticated\n")
    return _build_headers(cookies)
