import os
import sys
import shutil
import threading
import queue
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config
import uploader
import scraper
import dedupe
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
        self.geometry("950x900")
        self.minsize(850, 780)
        self.is_running = False
        self.log_queue = queue.Queue()
        self._build_ui()
        self.after(100, self._process_log_queue)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#1E1E2E")
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header_frame, text="🚀 TikTok -> UCircle Auto Pipeline", font=ctk.CTkFont(size=22, weight="bold"), text_color="#38BDF8").grid(row=0, column=0, padx=15, pady=(12, 2), sticky="w")
        ctk.CTkLabel(header_frame, text="Tab 1: Quét TikTok -> Excel.  Tab 2: Đăng Excel lên UCircle.", font=ctk.CTkFont(size=13), text_color="#94A3B8").grid(row=1, column=0, padx=15, pady=(0, 12), sticky="w")

        # ---- Tabview: tách 2 khu vực riêng biệt để tránh nhầm lẫn ----
        tabview = ctk.CTkTabview(self, corner_radius=10)
        tabview.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        tab_scan = tabview.add("🔍 1. Quét TikTok -> Excel")
        tab_upload = tabview.add("📤 2. Đăng Excel -> UCircle")

        self._build_scan_tab(tab_scan)
        self._build_upload_tab(tab_upload)

        # Console
        console_frame = ctk.CTkFrame(self, corner_radius=10)
        console_frame.grid(row=2, column=0, padx=15, pady=(5, 15), sticky="nsew")
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

    def _build_scan_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        form_frame = ctk.CTkFrame(parent, corner_radius=10)
        form_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        form_frame.grid_columnconfigure(1, weight=1)

        # Chế độ quét
        ctk.CTkLabel(form_frame, text="Chế độ quét:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        self.mode_var = tk.StringVar(value="profile")
        mode_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        mode_box.grid(row=0, column=1, padx=(0, 15), pady=(15, 5), sticky="w")
        ctk.CTkRadioButton(mode_box, text="Theo Profile (kênh)", variable=self.mode_var, value="profile").pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(mode_box, text="Theo Từ khoá", variable=self.mode_var, value="keyword").pack(side="left")

        # Nguồn (URL hoặc từ khoá)
        ctk.CTkLabel(form_frame, text="Link kênh TikTok / Từ khoá:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=15, pady=5, sticky="w")
        self.source_entry = ctk.CTkEntry(form_frame, placeholder_text="https://www.tiktok.com/@username  hoặc  gái xinh trend", height=38)
        self.source_entry.grid(row=1, column=1, padx=(0, 15), pady=5, sticky="ew")

        # Limit + cookie
        options_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        options_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        options_frame.grid_columnconfigure((0, 1), weight=1)

        limit_box = ctk.CTkFrame(options_frame, fg_color="transparent")
        limit_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(limit_box, text="Số lượng video tối đa:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))
        self.limit_entry = ctk.CTkEntry(limit_box, width=80, height=34)
        self.limit_entry.insert(0, "10")
        self.limit_entry.pack(side="left")
        ctk.CTkLabel(limit_box, text="(0 = tất cả)", text_color="#64748B").pack(side="left", padx=(8, 0))

        cookie_box = ctk.CTkFrame(options_frame, fg_color="transparent")
        cookie_box.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(cookie_box, text="Cookie TikTok:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))
        self.browser_menu = ctk.CTkOptionMenu(cookie_box, values=["chrome", "edge", "firefox", "brave", "Không dùng"], width=100, height=34)
        self.browser_menu.set("Không dùng")
        self.browser_menu.pack(side="left", padx=(0, 5))
        self.cookie_entry = ctk.CTkEntry(cookie_box, width=160, height=34, placeholder_text="Chưa chọn file cookie")
        self.cookie_entry.pack(side="left", padx=(0, 5))
        ctk.CTkButton(cookie_box, text="📂 Chọn file cookie...", width=140, height=34,
                      command=lambda: self._browse_cookie_file(self.cookie_entry)).pack(side="left")

        # Ngưỡng lọc chất lượng
        quality_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        quality_box.grid(row=3, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        ctk.CTkLabel(quality_box, text="Lọc chất lượng — Views tối thiểu:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.min_views_entry = ctk.CTkEntry(quality_box, width=90, height=34)
        self.min_views_entry.insert(0, str(config.MIN_VIEWS))
        self.min_views_entry.pack(side="left", padx=(0, 15))

        ctk.CTkLabel(quality_box, text="Likes tối thiểu:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.min_likes_entry = ctk.CTkEntry(quality_box, width=90, height=34)
        self.min_likes_entry.insert(0, str(config.MIN_LIKES))
        self.min_likes_entry.pack(side="left", padx=(0, 15))

        ctk.CTkLabel(quality_box, text="Độ phân giải tối thiểu (px):", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.min_res_entry = ctk.CTkEntry(quality_box, width=90, height=34)
        self.min_res_entry.insert(0, str(config.MIN_RESOLUTION_HEIGHT))
        self.min_res_entry.pack(side="left")

        # Tuỳ chọn chống trùng lịch sử
        dedupe_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        dedupe_box.grid(row=4, column=0, columnspan=2, padx=15, pady=3, sticky="ew")
        self.dedupe_history_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            dedupe_box, text="🛡️ Tự động né (bỏ qua) video đã từng quét / đăng trong lịch sử",
            variable=self.dedupe_history_var, font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")

        ctk.CTkButton(
            dedupe_box, text="🧹 Xoá lịch sử quét", width=130, height=28,
            fg_color="#475569", hover_color="#334155", font=ctk.CTkFont(size=11),
            command=self._clear_scanned_history
        ).pack(side="right")

        # Số luồng quét
        MAX_THREADS = 8
        scrape_slider_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        scrape_slider_box.grid(row=5, column=0, columnspan=2, padx=15, pady=(5, 15), sticky="ew")
        scrape_slider_box.grid_columnconfigure(0, weight=1)
        scrape_label_row = ctk.CTkFrame(scrape_slider_box, fg_color="transparent")
        scrape_label_row.grid(row=0, column=0, sticky="ew")
        scrape_label_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(scrape_label_row, text="Số luồng quét:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        self.scrape_threads_value_label = ctk.CTkLabel(scrape_label_row, text=str(config.SCRAPE_THREADS_DEFAULT), font=ctk.CTkFont(weight="bold"), text_color="#0EA5E9")
        self.scrape_threads_value_label.grid(row=0, column=1, sticky="e")
        self.scrape_threads_slider = ctk.CTkSlider(
            scrape_slider_box, from_=1, to=MAX_THREADS, number_of_steps=MAX_THREADS - 1,
            command=lambda v: self.scrape_threads_value_label.configure(text=str(int(v))),
        )
        self.scrape_threads_slider.set(config.SCRAPE_THREADS_DEFAULT)
        self.scrape_threads_slider.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        # ---- Action Buttons (tab quét) ----
        action_frame = ctk.CTkFrame(parent, fg_color="transparent")
        action_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        action_frame.grid_columnconfigure((0, 1), weight=1)

        self.scan_btn = ctk.CTkButton(action_frame, text="🔍 QUÉT & LỌC -> EXCEL", font=ctk.CTkFont(size=14, weight="bold"), height=42, fg_color="#0EA5E9", hover_color="#0284C7", command=self._start_scan)
        self.scan_btn.grid(row=0, column=0, padx=5, sticky="ew")

        self.download_excel_btn = ctk.CTkButton(action_frame, text="📥 Tải file Excel", font=ctk.CTkFont(size=13), height=42, fg_color="#F59E0B", hover_color="#D97706", command=self._download_excel)
        self.download_excel_btn.grid(row=0, column=1, padx=5, sticky="ew")

    def _build_upload_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        form_frame = ctk.CTkFrame(parent, corner_radius=10)
        form_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        form_frame.grid_columnconfigure(1, weight=1)

        # UCircle Identity
        ctk.CTkLabel(form_frame, text="Fanpage/Cá nhân UCircle\n(tên, ID, hoặc dán nguyên link):", font=ctk.CTkFont(weight="bold"), justify="left").grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        self.identity_entry = ctk.CTkEntry(form_frame, height=38, placeholder_text="Tôi  |  6f41a4fc-...  |  https://ucircle.net/app/c/6f41a4fc-...")
        self.identity_entry.insert(0, getattr(config, "IDENTITY_NAME", "Tôi"))
        self.identity_entry.grid(row=0, column=1, padx=(0, 15), pady=(15, 5), sticky="ew")

        # Cookie TikTok (dùng khi tải video từ link trong lúc đăng)
        cookie_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        cookie_box.grid(row=1, column=0, columnspan=2, padx=15, pady=5, sticky="w")
        ctk.CTkLabel(cookie_box, text="Cookie TikTok (để tải video khi đăng):", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))
        self.upload_browser_menu = ctk.CTkOptionMenu(cookie_box, values=["chrome", "edge", "firefox", "brave", "Không dùng"], width=100, height=34)
        self.upload_browser_menu.set("Không dùng")
        self.upload_browser_menu.pack(side="left", padx=(0, 5))
        self.upload_cookie_entry = ctk.CTkEntry(cookie_box, width=160, height=34, placeholder_text="Chưa chọn file cookie")
        self.upload_cookie_entry.pack(side="left", padx=(0, 5))
        ctk.CTkButton(cookie_box, text="📂 Chọn file cookie...", width=140, height=34,
                      command=lambda: self._browse_cookie_file(self.upload_cookie_entry)).pack(side="left")

        # Delay giữa các lần đăng (Min - Max)
        delay_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        delay_box.grid(row=2, column=0, columnspan=2, padx=15, pady=5, sticky="w")
        ctk.CTkLabel(delay_box, text="Thời gian chờ (delay) giữa 2 lần đăng:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(delay_box, text="Tối thiểu:").pack(side="left", padx=(0, 5))
        self.min_delay_entry = ctk.CTkEntry(delay_box, width=70, height=34)
        self.min_delay_entry.insert(0, str(getattr(config, "MIN_DELAY_SEC", 60)))
        self.min_delay_entry.pack(side="left", padx=(0, 5))
        ctk.CTkLabel(delay_box, text="giây", text_color="#94A3B8").pack(side="left", padx=(0, 15))

        ctk.CTkLabel(delay_box, text="Tối đa:").pack(side="left", padx=(0, 5))
        self.max_delay_entry = ctk.CTkEntry(delay_box, width=70, height=34)
        self.max_delay_entry.insert(0, str(getattr(config, "MAX_DELAY_SEC", 70)))
        self.max_delay_entry.pack(side="left", padx=(0, 5))
        ctk.CTkLabel(delay_box, text="giây", text_color="#94A3B8").pack(side="left", padx=(0, 10))

        # Tùy chọn Crosspost (Lên bảng tin)
        crosspost_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        crosspost_box.grid(row=3, column=0, columnspan=2, padx=15, pady=5, sticky="w")
        self.crosspost_var = ctk.BooleanVar(value=getattr(config, "CROSSPOST_TO_FEED", True))
        ctk.CTkCheckBox(
            crosspost_box, text="📣 Lên bảng tin (Bật/tắt nút đăng lên bảng tin)",
            variable=self.crosspost_var, font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left")

        # Số luồng đăng
        MAX_THREADS = 8
        upload_slider_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        upload_slider_box.grid(row=4, column=0, columnspan=2, padx=15, pady=(5, 15), sticky="ew")
        upload_slider_box.grid_columnconfigure(0, weight=1)
        upload_label_row = ctk.CTkFrame(upload_slider_box, fg_color="transparent")
        upload_label_row.grid(row=0, column=0, sticky="ew")
        upload_label_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(upload_label_row, text="Số luồng đăng UCircle:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        self.upload_threads_value_label = ctk.CTkLabel(upload_label_row, text=str(config.UPLOAD_THREADS_DEFAULT), font=ctk.CTkFont(weight="bold"), text_color="#10B981")
        self.upload_threads_value_label.grid(row=0, column=1, sticky="e")
        self.upload_threads_slider = ctk.CTkSlider(
            upload_slider_box, from_=1, to=MAX_THREADS, number_of_steps=MAX_THREADS - 1,
            command=lambda v: self.upload_threads_value_label.configure(text=str(int(v))),
        )
        self.upload_threads_slider.set(config.UPLOAD_THREADS_DEFAULT)
        self.upload_threads_slider.grid(row=1, column=0, sticky="ew", pady=(4, 0))


        # ---- Action Buttons (tab đăng) ----
        action_frame = ctk.CTkFrame(parent, fg_color="transparent")
        action_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        action_frame.grid_columnconfigure((0, 1), weight=1)

        self.upload_btn = ctk.CTkButton(action_frame, text="📤 ĐĂNG EXCEL LÊN UCIRCLE", font=ctk.CTkFont(size=14, weight="bold"), height=42, fg_color="#10B981", hover_color="#059669", command=self._start_upload)
        self.upload_btn.grid(row=0, column=0, padx=5, sticky="ew")

        self.login_btn = ctk.CTkButton(action_frame, text="🔐 Đăng Nhập UCircle (Lần đầu)", font=ctk.CTkFont(size=13), height=42, fg_color="#6366F1", hover_color="#4F46E5", command=self._login_ucircle)
        self.login_btn.grid(row=0, column=1, padx=5, sticky="ew")

    def _process_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_textbox.insert(tk.END, msg)
            self.log_textbox.see(tk.END)
        self.after(100, self._process_log_queue)

    def write_log(self, msg: str):
        self.log_queue.put(msg + "\n")

    def _int_or(self, entry, default):
        try:
            return int(entry.get().strip())
        except ValueError:
            return default

    def _set_busy(self, busy: bool, status_text: str, status_color: str):
        self.is_running = busy
        state = "disabled" if busy else "normal"
        self.scan_btn.configure(state=state)
        self.upload_btn.configure(state=state)
        self.login_btn.configure(state=state)
        self.download_excel_btn.configure(state=state)
        self.status_badge.configure(text=status_text, text_color=status_color)

    def _browse_cookie_file(self, target_entry):
        chosen = filedialog.askopenfilename(
            title="Chọn file cookie TikTok (.txt)",
            filetypes=[("Cookie/Text files", "*.txt"), ("Tất cả file", "*.*")],
        )
        if chosen:
            target_entry.delete(0, tk.END)
            target_entry.insert(0, chosen)

    def _download_excel(self):
        if not os.path.exists(config.EXCEL_PATH):
            messagebox.showwarning("Chưa có dữ liệu", "Chưa có file Excel nào. Hãy bấm 'Quét & Lọc -> Excel' trước.")
            return

        dest = filedialog.asksaveasfilename(
            title="Lưu file Excel về máy",
            defaultextension=".xlsx",
            initialfile=os.path.basename(config.EXCEL_PATH),
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not dest:
            return

        try:
            shutil.copyfile(config.EXCEL_PATH, dest)
            self.write_log(f"✅ Đã tải file Excel về: {dest}")
            messagebox.showinfo("Thành công", f"Đã lưu file Excel vào:\n{dest}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu file: {e}")

    def _clear_scanned_history(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn xoá toàn bộ lịch sử các video đã quét?\n(Sau khi xoá, tool có thể quét lại các video cũ từ đầu)."):
            dedupe.save_scanned_set(set())
            self.write_log("🧹 Đã làm sạch lịch sử video đã quét.")
            messagebox.showinfo("Thành công", "Đã xoá bộ nhớ lịch sử quét!")

    def _login_ucircle(self):
        if self.is_running:
            return
        self._set_busy(True, "🟡 Đang login...", "#F59E0B")

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
                    page.wait_for_event("close", timeout=0)
                    context.storage_state(path=config.STORAGE_STATE_PATH)
                    self.write_log(f"✅ Đã lưu phiên đăng nhập vào {config.STORAGE_STATE_PATH}")
                    browser.close()
            except Exception as e:
                self.write_log(f"[ERROR] Lỗi khi login: {e}")
            finally:
                self.after(0, lambda: self._set_busy(False, "🟢 Sẵn sàng", "#10B981"))

        threading.Thread(target=run_login, daemon=True).start()

    def _start_scan(self):
        if self.is_running:
            return

        source = self.source_entry.get().strip()
        if not source:
            messagebox.showwarning("Lỗi", "Vui lòng nhập link kênh TikTok hoặc từ khoá tìm kiếm!")
            return

        is_keyword = self.mode_var.get() == "keyword"
        limit = self._int_or(self.limit_entry, 0)
        scrape_threads = int(self.scrape_threads_slider.get())
        min_views = self._int_or(self.min_views_entry, config.MIN_VIEWS)
        min_likes = self._int_or(self.min_likes_entry, config.MIN_LIKES)
        min_res = self._int_or(self.min_res_entry, config.MIN_RESOLUTION_HEIGHT)
        cookies_path = self.cookie_entry.get().strip() or None
        browser_cookie = self.browser_menu.get()
        if browser_cookie == "Không dùng":
            browser_cookie = None
        exclude_history = self.dedupe_history_var.get()

        self._set_busy(True, "🟡 Đang quét...", "#F59E0B")
        self.log_textbox.delete("1.0", tk.END)

        def task():
            old_stdout = sys.stdout
            sys.stdout = TextRedirector(self.log_queue)
            try:
                # Xoá file cũ để đảm bảo danh sách luôn mới tinh, không bị dính video từ lần quét trước
                if os.path.exists(config.EXCEL_PATH):
                    os.remove(config.EXCEL_PATH)
                    print("[!] Đã dọn dẹp file nháp cũ. Bắt đầu lưu danh sách mới tinh.")

                with sync_playwright() as p:
                    result = scraper.scrape_and_filter(
                        p, source, is_keyword=is_keyword, limit=limit,
                        scrape_threads=scrape_threads, min_views=min_views,
                        min_likes=min_likes, min_resolution=min_res,
                        cookies_path=cookies_path, browser_cookie=browser_cookie,
                        exclude_history=exclude_history,
                    )
                print(f"\n[+] Xong: quét {result['scanned']}, đạt {result['passed']}, loại {result['rejected']}.")
            except Exception as e:
                print(f"[ERROR] Lỗi nghiêm trọng khi quét: {e}")
            finally:
                sys.stdout = old_stdout
                self.after(0, lambda: self._set_busy(False, "🟢 Hoàn tất quét!", "#10B981"))

        threading.Thread(target=task, daemon=True).start()

    def _start_upload(self):
        """Bấm nút 'Đăng lên UCircle' -> mở form chọn file Excel -> bấm 'Bắt đầu đăng' trong form đó."""
        if self.is_running:
            return

        if not os.path.exists(config.STORAGE_STATE_PATH):
            messagebox.showwarning("Lỗi", "Chưa có session UCircle. Vui lòng bấm 'Đăng Nhập UCircle (Lần đầu)' trước!")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Đăng lên UCircle từ Excel")
        dialog.geometry("560x180")
        dialog.grab_set()  # modal
        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(dialog, text="Chọn file Excel chứa link video cần đăng (cột 'link', trạng thái 'pending'):",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="w")

        path_var = tk.StringVar(value=config.EXCEL_PATH)
        path_entry = ctk.CTkEntry(dialog, textvariable=path_var)
        path_entry.grid(row=1, column=0, padx=(15, 5), pady=5, sticky="ew")

        def browse():
            chosen = filedialog.askopenfilename(
                title="Chọn file Excel",
                filetypes=[("Excel files", "*.xlsx"), ("Tất cả file", "*.*")],
                initialdir=os.path.dirname(os.path.abspath(config.EXCEL_PATH)) or ".",
            )
            if chosen:
                path_var.set(chosen)

        ctk.CTkButton(dialog, text="📂 Chọn file...", width=110, command=browse).grid(row=1, column=1, padx=(5, 15), pady=5)

        status_label = ctk.CTkLabel(dialog, text="", text_color="#94A3B8")
        status_label.grid(row=2, column=0, columnspan=2, padx=15, pady=(0, 5), sticky="w")

        def confirm():
            excel_path = path_var.get().strip()
            if not excel_path or not os.path.exists(excel_path):
                status_label.configure(text="⚠️ File không tồn tại, hãy chọn lại.", text_color="#F59E0B")
                return
            dialog.destroy()
            self._run_upload_from_excel(excel_path)

        ctk.CTkButton(dialog, text="🚀 Bắt đầu đăng", font=ctk.CTkFont(size=14, weight="bold"),
                      height=40, fg_color="#10B981", hover_color="#059669", command=confirm).grid(
            row=3, column=0, columnspan=2, padx=15, pady=(10, 15), sticky="ew")

    def _run_upload_from_excel(self, excel_path: str):
        upload_threads = int(self.upload_threads_slider.get())
        config.IDENTITY_NAME = self.identity_entry.get().strip()
        config.CROSSPOST_TO_FEED = self.crosspost_var.get()
        config.MIN_DELAY_SEC = self._int_or(self.min_delay_entry, 60)
        config.MAX_DELAY_SEC = self._int_or(self.max_delay_entry, 70)
        if config.MIN_DELAY_SEC > config.MAX_DELAY_SEC:
            config.MIN_DELAY_SEC, config.MAX_DELAY_SEC = config.MAX_DELAY_SEC, config.MIN_DELAY_SEC


        cookies_path = self.upload_cookie_entry.get().strip() or None
        browser_cookie = self.upload_browser_menu.get()
        if browser_cookie == "Không dùng":
            browser_cookie = None

        self._set_busy(True, "🟡 Đang đăng...", "#F59E0B")
        self.log_textbox.delete("1.0", tk.END)

        def task():
            old_stdout = sys.stdout
            sys.stdout = TextRedirector(self.log_queue)
            try:
                result = uploader.run_uploads(threads=upload_threads, cookies_path=cookies_path, browser_cookie=browser_cookie, excel_path=excel_path)
                print(f"\n[+] Xong: {result['success']}/{result['total']} đăng thành công, {result['failed']} thất bại.")
            except Exception as e:
                print(f"[ERROR] Lỗi nghiêm trọng khi đăng: {e}")
            finally:
                sys.stdout = old_stdout
                self.after(0, lambda: self._set_busy(False, "🟢 Hoàn tất đăng!", "#10B981"))
                self.after(0, lambda: messagebox.showinfo("Thành công", "Đã đăng xong toàn bộ video pending!"))

        threading.Thread(target=task, daemon=True).start()


if __name__ == "__main__":
    app = UCirclePipelineApp()
    app.mainloop()
