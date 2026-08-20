import os
import sys
import threading
import queue
import time
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

# Ensure correct path so config and main are loaded from ucircle-py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config
import main as ucircle_backend
import tiktok_extractor
from playwright.sync_api import sync_playwright

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class TextRedirector:
    def __init__(self, log_queue):
        self.log_queue = log_queue

    def write(self, str_val):
        if str_val.strip():
            self.log_queue.put(str_val + "\n")

    def flush(self):
        pass

class UCirclePipelineApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TikTok -> UCircle Auto Pipeline")
        self.geometry("900x850")
        self.minsize(800, 750)
        self.is_running = False
        self.log_queue = queue.Queue()
        self._build_ui()
        self.after(100, self._process_log_queue)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header Frame
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#1E1E2E")
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header_frame, text="🚀 TikTok -> UCircle Auto Pipeline", font=ctk.CTkFont(size=22, weight="bold"), text_color="#38BDF8").grid(row=0, column=0, padx=15, pady=(12, 2), sticky="w")
        ctk.CTkLabel(header_frame, text="Tự động quét TikTok -> Tải tạm 1 video -> Đăng lên UCircle -> Xóa file tạm (Không đầy ổ cứng)", font=ctk.CTkFont(size=13), text_color="#94A3B8").grid(row=1, column=0, padx=15, pady=(0, 12), sticky="w")

        # Form Inputs Frame
        form_frame = ctk.CTkFrame(self, corner_radius=10)
        form_frame.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        form_frame.grid_columnconfigure(1, weight=1)

        # 1. TikTok URL
        ctk.CTkLabel(form_frame, text="Link TikTok (Kênh/Video):", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        self.url_entry = ctk.CTkEntry(form_frame, placeholder_text="https://www.tiktok.com/@username", height=38)
        self.url_entry.grid(row=0, column=1, padx=(0, 15), pady=(15, 5), sticky="ew")

        # 2. UCircle Identity (Tư cách đăng)
        ctk.CTkLabel(form_frame, text="Tên Fanpage/Cá nhân UCircle:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=15, pady=5, sticky="w")
        self.identity_entry = ctk.CTkEntry(form_frame, height=38)
        self.identity_entry.insert(0, getattr(config, "IDENTITY_NAME", "Tôi"))
        self.identity_entry.grid(row=1, column=1, padx=(0, 15), pady=5, sticky="ew")

        # 3. Limit Entry
        options_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        options_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=(5, 15), sticky="ew")
        options_frame.grid_columnconfigure((0, 1), weight=1)

        limit_box = ctk.CTkFrame(options_frame, fg_color="transparent")
        limit_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(limit_box, text="Số lượng video tối đa:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))
        self.limit_entry = ctk.CTkEntry(limit_box, width=80, height=34)
        self.limit_entry.insert(0, "10")
        self.limit_entry.pack(side="left")
        ctk.CTkLabel(limit_box, text="(0 = Tải tất cả)", text_color="#64748B").pack(side="left", padx=(8, 0))
        
        # 4. TikTok Cookies options
        cookie_box = ctk.CTkFrame(options_frame, fg_color="transparent")
        cookie_box.grid(row=0, column=1, sticky="e")
        
        ctk.CTkLabel(cookie_box, text="Cookie TikTok:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))
        
        self.browser_menu = ctk.CTkOptionMenu(
            cookie_box,
            values=["chrome", "edge", "firefox", "brave", "Không dùng"],
            width=100, height=34
        )
        self.browser_menu.set("Không dùng")
        self.browser_menu.pack(side="left", padx=(0, 5))

        self.cookie_entry = ctk.CTkEntry(cookie_box, width=100, height=34, placeholder_text="Hoặc file.txt")
        if os.path.exists("../TikTokLinkExtractor/cookies.txt"):
            self.cookie_entry.insert(0, "../TikTokLinkExtractor/cookies.txt")
        self.cookie_entry.pack(side="left")

        # 5. Hashtags
        ctk.CTkLabel(form_frame, text="Hashtags (cách bằng dấu phẩy):", font=ctk.CTkFont(weight="bold")).grid(row=3, column=0, padx=15, pady=5, sticky="nw")
        self.hashtags_entry = ctk.CTkEntry(form_frame, height=38)
        self.hashtags_entry.insert(0, ", ".join(config.HASHTAG_POOL))
        self.hashtags_entry.grid(row=3, column=1, padx=(0, 15), pady=5, sticky="ew")

        # 6. Captions
        ctk.CTkLabel(form_frame, text="Mẫu Caption (mỗi dòng 1 mẫu):", font=ctk.CTkFont(weight="bold")).grid(row=4, column=0, padx=15, pady=5, sticky="nw")
        self.captions_textbox = ctk.CTkTextbox(form_frame, height=80)
        self.captions_textbox.insert("1.0", "\n".join(config.CAPTION_TEMPLATES))
        self.captions_textbox.grid(row=4, column=1, padx=(0, 15), pady=(5, 15), sticky="ew")

        # Action Buttons
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=2, column=0, padx=15, pady=5, sticky="ew")
        action_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_btn = ctk.CTkButton(action_frame, text="🚀 BẮT ĐẦU CHẠY TỰ ĐỘNG", font=ctk.CTkFont(size=15, weight="bold"), height=42, fg_color="#10B981", hover_color="#059669", command=self._start_process)
        self.start_btn.grid(row=0, column=0, padx=5, sticky="ew")

        self.login_btn = ctk.CTkButton(action_frame, text="🔐 Đăng Nhập UCircle (Lần đầu)", font=ctk.CTkFont(size=13), height=42, fg_color="#6366F1", hover_color="#4F46E5", command=self._login_ucircle)
        self.login_btn.grid(row=0, column=1, padx=5, sticky="ew")

        # Console
        console_frame = ctk.CTkFrame(self, corner_radius=10)
        console_frame.grid(row=3, column=0, padx=15, pady=(5, 15), sticky="nsew")
        console_frame.grid_columnconfigure(0, weight=1)
        console_frame.grid_rowconfigure(1, weight=1)

        console_header = ctk.CTkFrame(console_frame, fg_color="transparent")
        console_header.grid(row=0, column=0, padx=10, pady=(8, 2), sticky="ew")
        console_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(console_header, text="📋 Nhật Ký Hoạt Động (Console Logs):", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        
        self.status_badge = ctk.CTkLabel(console_header, text="🟢 Sẵn sàng", font=ctk.CTkFont(size=12, weight="bold"), text_color="#10B981")
        self.status_badge.grid(row=0, column=1, sticky="e")

        self.log_textbox = ctk.CTkTextbox(console_frame, font=ctk.CTkFont(family="Consolas", size=13), fg_color="#0F172A", text_color="#E2E8F0")
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

    def _process_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_textbox.insert(tk.END, msg)
            self.log_textbox.see(tk.END)
        self.after(100, self._process_log_queue)
        
    def write_log(self, msg: str):
        self.log_queue.put(msg + "\n")

    def _login_ucircle(self):
        if self.is_running: return
        self.is_running = True
        self.login_btn.configure(state="disabled")
        
        def run_login():
            try:
                self.write_log("Đang mở trình duyệt để bạn đăng nhập UCircle...")
                with sync_playwright() as p:
                    os.makedirs(os.path.dirname(config.STORAGE_STATE_PATH), exist_ok=True)
                    browser = p.chromium.launch(headless=False)
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto(config.LOGIN_URL)
                    self.write_log("👉 Vui lòng đăng nhập trên trình duyệt UCircle đang mở.")
                    self.write_log("👉 Sau khi đăng nhập thành công, hãy tự ĐÓNG CỬA SỔ trình duyệt đó lại.")
                    
                    page.wait_for_event("close", timeout=0)  # Wait until user closes page/browser
                    
                    context.storage_state(path=config.STORAGE_STATE_PATH)
                    self.write_log(f"✅ Đã lưu phiên đăng nhập vào {config.STORAGE_STATE_PATH}")
                    browser.close()
            except Exception as e:
                self.write_log(f"[ERROR] Lỗi khi login: {e}")
            finally:
                self.is_running = False
                self.login_btn.configure(state="normal")
                
        threading.Thread(target=run_login, daemon=True).start()

    def _start_process(self):
        if self.is_running: return
        
        url = self.url_entry.get().strip()
        if not url or "tiktok.com" not in url:
            messagebox.showwarning("Lỗi", "Vui lòng nhập link TikTok hợp lệ!")
            return
            
        if not os.path.exists(config.STORAGE_STATE_PATH):
            messagebox.showwarning("Lỗi", "Chưa có session UCircle. Vui lòng bấm 'Đăng Nhập UCircle (Lần đầu)' trước!")
            return

        try:
            limit = int(self.limit_entry.get().strip())
        except ValueError:
            limit = 0

        config.IDENTITY_NAME = self.identity_entry.get().strip()
        
        raw_tags = self.hashtags_entry.get().strip()
        config.HASHTAG_POOL = [t.strip() for t in raw_tags.split(",") if t.strip()]
        
        raw_captions = self.captions_textbox.get("1.0", "end-1c").strip()
        config.CAPTION_TEMPLATES = [c.strip() for c in raw_captions.split("\n") if c.strip()]
        
        cookies_path = self.cookie_entry.get().strip()
        browser_cookie = self.browser_menu.get()
        if browser_cookie == "Không dùng":
            browser_cookie = None

        self.is_running = True
        self.start_btn.configure(state="disabled", text="⏳ ĐANG XỬ LÝ...", fg_color="#64748B")
        self.status_badge.configure(text="🟡 Đang chạy...", text_color="#F59E0B")
        self.log_textbox.delete("1.0", tk.END)
        
        threading.Thread(target=self._run_pipeline, args=(url, limit, cookies_path, browser_cookie), daemon=True).start()

    def _run_pipeline(self, url: str, limit: int, cookies_path: str, browser_cookie: str):
        old_stdout = sys.stdout
        sys.stdout = TextRedirector(self.log_queue)
        
        try:
            print("========================================")
            print(" BẮT ĐẦU PIPELINE: TIKTOK -> UCIRCLE")
            print("========================================")
            
            # 1. Lấy links TikTok
            with sync_playwright() as p:
                links = tiktok_extractor.extract_tiktok_links(p, url, limit)
                
            if not links:
                print("[!] Không tìm thấy video TikTok nào.")
                return
                
            print(f"\n[+] Tổng cộng {len(links)} video cần xử lý.\n")
            
            # 2. Khởi tạo UCircle Playwright
            os.makedirs(config.VIDEO_FOLDER, exist_ok=True)
            temp_video_path = os.path.join(config.VIDEO_FOLDER, "temp_video.mp4")
            
            with sync_playwright() as p:
                print("[+] Đang mở trình duyệt UCircle (Hiển thị màn hình để theo dõi)...")
                browser = p.chromium.launch(headless=False)
                context = browser.new_context(storage_state=config.STORAGE_STATE_PATH)
                page = context.new_page()
                
                posted_set = ucircle_backend.load_posted_set()
                
                for idx, link in enumerate(links, 1):
                    if link in posted_set:
                        print(f"[{idx}/{len(links)}] Đã từng đăng video này, bỏ qua: {link}")
                        continue
                        
                    print(f"\n----------------------------------------")
                    print(f"[{idx}/{len(links)}] Bước A: Tải file tạm cho video: {link}")
                    
                    success_dl = tiktok_extractor.download_single_video(link, temp_video_path, cookies_path, browser_cookie)
                    if not success_dl:
                        print(f"❌ Không tải được video này, bỏ qua.")
                        continue
                        
                    print(f"[{idx}/{len(links)}] Bước B: Tải lên UCircle...")
                    try:
                        ucircle_backend.upload_one_video(page, temp_video_path)
                        posted_set.add(link)
                        # Save the updated set
                        import json
                        with open(config.POSTED_HASH_DB_PATH, "w", encoding="utf-8") as f:
                            json.dump(list(posted_set), f, ensure_ascii=False, indent=2)
                        print(f"✅ Đăng thành công!")
                    except Exception as e:
                        print(f"❌ Lỗi khi đăng video lên UCircle: {e}")
                        
                    print(f"[{idx}/{len(links)}] Bước C: Xóa file tạm.")
                    if os.path.exists(temp_video_path):
                        os.remove(temp_video_path)
                        
                    if idx < len(links):
                        delay = ucircle_backend.random_delay_sec()
                        print(f"⏳ Đang nghỉ {delay} giây trước video tiếp theo...")
                        time.sleep(delay)
                        
                browser.close()
                print("\n========================================")
                print(" HOÀN TẤT TOÀN BỘ QUÁ TRÌNH PIPELINE")
                print("========================================")

        except Exception as e:
            print(f"\n[ERROR] Lỗi nghiêm trọng: {e}")
        finally:
            sys.stdout = old_stdout
            self.is_running = False
            self.after(0, self._on_task_finished)

    def _on_task_finished(self):
        self.start_btn.configure(state="normal", text="🚀 BẮT ĐẦU CHẠY TỰ ĐỘNG", fg_color="#10B981")
        self.status_badge.configure(text="🟢 Hoàn tất!", text_color="#10B981")
        messagebox.showinfo("Thành công", "Tiến trình quét và đăng tự động đã hoàn tất!")

if __name__ == "__main__":
    app = UCirclePipelineApp()
    app.mainloop()
