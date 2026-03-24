"""
rizoma-automation / 01_recon.py
================================
Phase 1: Authentication + API endpoint mapping.

What this script does:
  1. Opens a real Chromium browser (headed by default so you can watch + help if needed)
  2. Logs in to rizoma.conahcyt.mx with your credentials
  3. Intercepts EVERY network request/response made by the SPA
  4. Saves a full session log to logs/session_log.json
  5. Saves a clean API map to logs/api_map.json  (deduplicated endpoints + payload shapes)
  6. Saves cookies/storage to session/session_state.json for reuse by later scripts

Usage:
  cd rizoma-automation
  python scripts/01_recon.py

  The script will prompt for credentials interactively (never stored in files).
  If you want headless mode: python scripts/01_recon.py --headless
"""

import asyncio
import json
import re
import sys
import getpass
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Request, Response

BASE_URL = "https://rizoma.conahcyt.mx"
LOG_DIR = Path(__file__).parent.parent / "logs"
SESSION_DIR = Path(__file__).parent.parent / "session"
LOG_DIR.mkdir(exist_ok=True)
SESSION_DIR.mkdir(exist_ok=True)

HEADLESS = "--headless" in sys.argv

# ── Helpers ───────────────────────────────────────────────────────────────────

def sanitize_payload(data: dict) -> dict:
    """Redact password fields from logged payloads."""
    sensitive = {"password", "contrasena", "passwd", "secret", "token", "pass"}
    return {
        k: ("***REDACTED***" if k.lower() in sensitive else v)
        for k, v in data.items()
    }

def extract_payload_shape(body: str) -> dict:
    """Parse a request body and return its key structure (values replaced with types)."""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return {k: type(v).__name__ for k, v in parsed.items()}
        return {"_type": type(parsed).__name__}
    except Exception:
        return {"_raw": body[:200] if body else None}

# ── Core ──────────────────────────────────────────────────────────────────────

async def run():
    print("\n╔══════════════════════════════════════════╗")
    print("║   Rizoma Recon — Phase 1: Auth + Map     ║")
    print("╚══════════════════════════════════════════╝\n")

    username = input("  Usuario (email o CURP): ").strip()
    password = getpass.getpass("  Contraseña: ")

    all_requests: list[dict] = []
    api_calls: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, slow_mo=200)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # ── Intercept all requests ────────────────────────────────────────────
        async def on_request(request: Request):
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "method": request.method,
                "url": request.url,
                "resource_type": request.resource_type,
                "headers": dict(request.headers),
            }
            try:
                body = request.post_data
                if body:
                    entry["body"] = extract_payload_shape(body)
            except Exception:
                pass
            all_requests.append(entry)

            # Flag likely API calls
            parsed = urlparse(request.url)
            if any(seg in parsed.path for seg in ["/api/", "/v1/", "/v2/", "/graphql", "/rest/"]) \
               or request.resource_type in ("fetch", "xhr"):
                api_entry = {
                    "method": request.method,
                    "url": request.url,
                    "path": parsed.path,
                    "resource_type": request.resource_type,
                }
                try:
                    body = request.post_data
                    if body:
                        shape = extract_payload_shape(body)
                        api_entry["payload_shape"] = sanitize_payload(shape)
                except Exception:
                    pass
                api_calls.append(api_entry)
                print(f"  [API] {request.method:6s} {parsed.path}")

        async def on_response(response: Response):
            parsed = urlparse(response.url)
            if response.request.resource_type in ("fetch", "xhr"):
                for entry in api_calls:
                    if entry["url"] == response.url and "status" not in entry:
                        entry["status"] = response.status
                        try:
                            ct = response.headers.get("content-type", "")
                            if "json" in ct:
                                body = await response.json()
                                # Store shape only, not full data (can be large)
                                if isinstance(body, dict):
                                    entry["response_keys"] = list(body.keys())
                                elif isinstance(body, list) and body:
                                    entry["response_item_keys"] = list(body[0].keys()) if isinstance(body[0], dict) else []
                        except Exception:
                            pass
                        break

        page = await context.new_page()
        page.on("request", on_request)
        page.on("response", on_response)

        # ── Step 1: Load Rizoma homepage, click Login button ─────────────────
        print(f"\n  → Navigating to {BASE_URL} ...")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        await page.screenshot(path=str(LOG_DIR / "01_homepage.png"))
        print(f"  ✓ Page loaded: {await page.title()}")
        print(f"  ✓ Current URL: {page.url}")

        # ── Step 2: Click the Login button (triggers OAuth2 redirect) ─────────
        print("\n  → Looking for Login button on homepage...")
        await page.wait_for_timeout(2000)

        login_btn_selectors = [
            'a:has-text("Iniciar sesión")',
            'a:has-text("Login")',
            'button:has-text("Iniciar sesión")',
            'button:has-text("Login")',
            'a[href*="login"]',
            'a[href*="oauth"]',
            'a[href*="auth"]',
        ]
        clicked_login = False
        for sel in login_btn_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    print(f"  ✓ Found login button: {sel}")
                    async with page.expect_navigation(wait_until="networkidle", timeout=15000):
                        await el.click()
                    clicked_login = True
                    break
            except Exception:
                continue

        if not clicked_login:
            print("  ⚠ No login button found via selectors — checking page manually")
            print("    Saving page HTML for inspection...")
            html = await page.content()
            with open(LOG_DIR / "homepage.html", "w") as f:
                f.write(html)
            print("    Keeping browser open 20s for manual inspection...")
            await page.wait_for_timeout(20000)

        print(f"  ✓ After login click URL: {page.url}")
        await page.screenshot(path=str(LOG_DIR / "02_after_login_click.png"))

        # ── Step 3: We should now be on Keycloak (idm.conahcyt.mx) ───────────
        print(f"\n  → Current domain: {urlparse(page.url).netloc}")
        if "idm.conahcyt.mx" not in page.url and "openid" not in page.url:
            print("  ⚠ Not on expected Keycloak page. Inspect screenshot 02_after_login_click.png")
        
        print("  → Waiting for Keycloak login form...")
        await page.wait_for_timeout(2000)

        inputs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input')).map(el => ({
                name: el.name, id: el.id, type: el.type, placeholder: el.placeholder
            }));
        }""")
        print(f"  ✓ Input fields found: {inputs}")
        await page.screenshot(path=str(LOG_DIR / "03_keycloak_form.png"))

        # ── Step 4: Fill Keycloak form ────────────────────────────────────────
        print("\n  → Filling Keycloak credentials...")
        try:
            # Keycloak standard field names
            keycloak_user_selectors = [
                'input[name="username"]',
                'input[id="username"]',
                'input[type="email"]',
                'input[name="email"]',
            ]
            keycloak_pass_selectors = [
                'input[name="password"]',
                'input[id="password"]',
                'input[type="password"]',
            ]

            user_field = None
            for sel in keycloak_user_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1500):
                        user_field = sel
                        break
                except Exception:
                    continue

            pass_field = None
            for sel in keycloak_pass_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1500):
                        pass_field = sel
                        break
                except Exception:
                    continue

            if user_field and pass_field:
                print(f"  ✓ Username field: {user_field}")
                print(f"  ✓ Password field: {pass_field}")
                await page.fill(user_field, username)
                await page.fill(pass_field, password)
                await page.screenshot(path=str(LOG_DIR / "04_filled.png"))

                # Submit — Keycloak uses a standard submit button
                submit_selectors = [
                    'input[type="submit"]',
                    'button[type="submit"]',
                    'button:has-text("Iniciar")',
                    'button:has-text("Acceder")',
                    'button:has-text("Log In")',
                ]
                submitted = False
                for sel in submit_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=1000):
                            print(f"  ✓ Submit: {sel}")
                            await el.click()
                            submitted = True
                            break
                    except Exception:
                        continue

                if not submitted:
                    print("  ⚠ No submit button — pressing Enter")
                    await page.keyboard.press("Enter")

                print("  → Waiting for OAuth redirect back to Rizoma...")
                await page.wait_for_timeout(4000)
                # Wait for redirect back — URL should return to rizoma.conahcyt.mx
                try:
                    await page.wait_for_url("**/rizoma.conahcyt.mx/**", timeout=20000)
                except Exception:
                    pass
                await page.wait_for_load_state("networkidle", timeout=15000)
                await page.screenshot(path=str(LOG_DIR / "05_post_login.png"))
                print(f"  ✓ Post-login URL: {page.url}")

            else:
                print(f"  ✗ Could not find Keycloak form fields.")
                print(f"    user_field={user_field}, pass_field={pass_field}")
                print("    Check logs/03_keycloak_form.png")
                await page.wait_for_timeout(20000)

        except Exception as e:
            print(f"  ✗ Login error: {e}")
            await page.screenshot(path=str(LOG_DIR / "error_login.png"))

        # ── Step 4: Navigate the main sections to trigger API calls ──────────
        if BASE_URL not in page.url or "login" not in page.url:
            print("\n  → Exploring platform sections to map API calls...")
            await page.wait_for_timeout(2000)

            # Dump page structure
            nav_links = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a, button, [role="menuitem"]'))
                    .filter(el => el.offsetParent !== null)
                    .slice(0, 40)
                    .map(el => ({
                        tag: el.tagName,
                        text: el.innerText.trim().substring(0, 50),
                        href: el.href || null,
                        role: el.getAttribute('role')
                    }))
                    .filter(el => el.text.length > 0);
            }""")
            print(f"\n  ✓ Visible nav elements ({len(nav_links)}):")
            for link in nav_links:
                print(f"      [{link['tag']}] {link['text']!r:40s} → {(link.get('href') or '')[:60]}")

            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(LOG_DIR / "05_dashboard.png"))

        # ── Step 5: Save session state ────────────────────────────────────────
        print("\n  → Saving session state...")
        await context.storage_state(path=str(SESSION_DIR / "session_state.json"))
        print(f"  ✓ Session saved to session/session_state.json")

        await browser.close()

    # ── Step 6: Build outputs ─────────────────────────────────────────────────
    print("\n  → Building API map...")

    # Deduplicate by method + path
    seen = set()
    deduped = []
    for call in api_calls:
        key = f"{call['method']}:{call['path']}"
        if key not in seen:
            seen.add(key)
            deduped.append(call)

    api_map = {
        "generated_at": datetime.utcnow().isoformat(),
        "base_url": BASE_URL,
        "total_requests_captured": len(all_requests),
        "api_calls_total": len(api_calls),
        "api_calls_unique": len(deduped),
        "endpoints": deduped,
    }

    with open(LOG_DIR / "session_log.json", "w", encoding="utf-8") as f:
        json.dump(all_requests, f, indent=2, ensure_ascii=False, default=str)

    with open(LOG_DIR / "api_map.json", "w", encoding="utf-8") as f:
        json.dump(api_map, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n  ✓ session_log.json  ({len(all_requests)} requests)")
    print(f"  ✓ api_map.json      ({len(deduped)} unique endpoints)")
    print(f"\n  Screenshots saved to logs/")
    print("\n  Next step: review logs/api_map.json, then run 02_map_activities.py\n")


if __name__ == "__main__":
    asyncio.run(run())
