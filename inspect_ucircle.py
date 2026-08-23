import os
import sys
from playwright.sync_api import sync_playwright
import config

sys.stdout.reconfigure(encoding='utf-8')

def inspect_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=config.STORAGE_STATE_PATH)
        page = context.new_page()
        
        page.goto(config.UPLOAD_URL)
        sel = config.SELECTORS
        
        try:
            if "create_button" in sel:
                page.click(sel["create_button"], timeout=5000)
                page.wait_for_timeout(1000)
            
            if "tab_file" in sel:
                page.click(sel["tab_file"], timeout=3000)
                page.wait_for_timeout(1000)
                
            page.set_input_files(sel["file_input"], "dummy.mp4")
            page.wait_for_timeout(3000)
            
            elements = page.locator('button[role="radio"]').all()
            with open("identities.txt", "w", encoding="utf-8") as f:
                if elements:
                    for i, el in enumerate(elements):
                        try:
                            text = el.inner_text().strip()
                            html = el.evaluate("el => el.outerHTML")
                            f.write(f"\n--- Identity Button {i+1}: {text} ---\n")
                            f.write(f"HTML: {html}\n")
                        except Exception as e:
                            pass
                else:
                    f.write("No button[role='radio'] found.")
        except Exception as e:
            print("Error during inspection:", e)
            
        browser.close()

if __name__ == "__main__":
    inspect_page()
