"""Take screenshots of all frontend pages for README.md."""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:5173"
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def shoot(page, url: str, filename: str, wait_selector: str | None = None):
    print(f"  → {filename}  ({url})")
    page.goto(url, wait_until="networkidle")
    if wait_selector:
        try:
            page.wait_for_selector(wait_selector, timeout=8000)
        except Exception as e:
            print(f"    ! selector wait failed: {wait_selector} ({e})")
    page.wait_for_timeout(800)
    out_path = OUT_DIR / filename
    page.screenshot(path=str(out_path), full_page=True)
    print(f"    saved: {out_path} ({out_path.stat().st_size} bytes)")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()

        # 1. Login page
        shoot(page, f"{BASE_URL}/login", "login.png", ".login-container, .el-form, .el-input")

        # Perform login via API to get token, then inject into localStorage
        # The auth store uses 'token' key in localStorage
        import json
        import urllib.request

        req_data = json.dumps({"username": "admin", "password": "admin"}).encode()
        req = urllib.request.Request(
            f"{BASE_URL.replace('5173', '8000')}/api/auth/login",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                login_resp = json.loads(resp.read().decode())
            token = login_resp["token"]
            print(f"  ✓ login token: {token[:20]}...")
        except Exception as e:
            print(f"  ! login API failed: {e}")
            token = None

        # Inject token into localStorage before navigating to protected pages
        if token:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            page.evaluate(f"""localStorage.setItem('token', '{token}'); localStorage.setItem('user', JSON.stringify({{username:'admin', role:'admin'}}))""")
            page.reload(wait_until="networkidle")

        # 2. Chat
        shoot(page, f"{BASE_URL}/chat", "chat.png", ".chat-container, .el-main, .chat-input")

        # 3. Knowledge Base - text mode (default)
        shoot(page, f"{BASE_URL}/kb", "knowledge-base-text.png", ".stats-row, .upload-panel")

        # Switch to file upload tab
        try:
            # el-tabs has tab labels; click the "文件上传" label
            page.get_by_text("文件上传", exact=True).click(timeout=5000)
            page.wait_for_selector(".file-upload-dragger", timeout=5000)
            page.wait_for_timeout(500)
        except Exception as e:
            print(f"  ! failed to switch to file tab: {e}")
        shoot(page, f"{BASE_URL}/kb", "knowledge-base-file.png", ".file-upload-dragger")

        # 4. Inspect
        shoot(page, f"{BASE_URL}/inspect", "inspect.png", ".el-main, .el-card, body")

        # 5. Users
        shoot(page, f"{BASE_URL}/users", "users.png")

        browser.close()

    print("\n=== Screenshots saved ===")
    for f in sorted(OUT_DIR.glob("*.png")):
        print(f"  {f.name}  ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
