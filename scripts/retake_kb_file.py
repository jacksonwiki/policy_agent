"""Re-shoot the knowledge base file upload tab screenshot."""
import sys
import time
import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:5173"
API_URL = "http://localhost:8000"
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def main():
    # Get token
    req_data = json.dumps({"username": "admin", "password": "admin"}).encode()
    req = urllib.request.Request(
        f"{API_URL}/api/auth/login",
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        login_resp = json.loads(resp.read().decode())
    token = login_resp["token"]
    print(f"  ✓ token: {token[:20]}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()

        # Preload token into localStorage
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.evaluate(
            f"""localStorage.setItem('token', '{token}'); localStorage.setItem('user', JSON.stringify({{username:'admin', role:'admin'}}))"""
        )

        # Navigate to KB
        page.goto(f"{BASE_URL}/kb", wait_until="networkidle")
        page.wait_for_selector(".upload-panel", timeout=8000)
        page.wait_for_timeout(500)

        # Confirm currently on text tab
        text_dragger_exists = page.query_selector(".file-upload-dragger")
        print(f"  before switch: .file-upload-dragger exists = {bool(text_dragger_exists)}")
        if text_dragger_exists:
            is_visible = page.is_visible(".file-upload-dragger")
            print(f"  before switch: .file-upload-dragger visible = {is_visible}")

        # Click the "文件上传" tab using el-tabs label selector
        # el-tabs renders labels in .el-tabs__item — use CSS selector with text matching
        try:
            # Try CSS :has-text pseudo
            file_tab = page.locator('.el-tabs__item:has-text("文件上传")').first
            count = file_tab.count()
            print(f"  found {count} tab(s) matching '文件上传'")
            if count > 0:
                file_tab.click()
                page.wait_for_timeout(800)
            else:
                # Fallback: click by exact text
                page.get_by_role("tab", name="文件上传").click(timeout=3000)
                page.wait_for_timeout(800)
        except Exception as e:
            print(f"  ! tab click error: {e}")

        # Verify file-upload-dragger is now visible
        try:
            page.wait_for_selector(".file-upload-dragger", state="visible", timeout=5000)
            print("  ✓ .file-upload-dragger is now VISIBLE")
        except Exception as e:
            print(f"  ! dragger not visible: {e}")
            # Try clicking by text again as fallback
            try:
                page.locator("text=文件上传").first.click(timeout=3000)
                page.wait_for_timeout(800)
                page.wait_for_selector(".file-upload-dragger", state="visible", timeout=5000)
                print("  ✓ dragger visible after fallback click")
            except Exception as e2:
                print(f"  ! fallback failed: {e2}")

        # Take screenshot
        out_path = OUT_DIR / "knowledge-base-file.png"
        page.screenshot(path=str(out_path), full_page=True)
        print(f"  saved: {out_path} ({out_path.stat().st_size} bytes)")

        browser.close()


if __name__ == "__main__":
    main()
