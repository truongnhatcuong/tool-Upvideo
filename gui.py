import os
import sys
import threading
import queue
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# Đảm bảo đường dẫn import đúng từ thư mục gốc
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

import config
import tiktok_extractor
import exporter
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


def open_file_or_folder(path: str):
    """Mở file hoặc thư mục trên Windows/macOS/Linux."""
    if not path or not os.path.exists(path):
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform.startswith("darwin"):
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
        return True
    except Exception as e:
        print(f"[!] Lỗi khi mở: {e}")
        return False


class TikTokLinkExtractorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TikTok Link Extractor -> Xuất Excel")
        self.geometry("920x820")
        self.minsize(800, 700)

        self.is_running = False
        self.should_stop = False
        self.last_exported_file = None
        self.log_queue = queue.Queue()

        self._build_ui()
        self.after(100, self._process_log_queue)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # 1. Header Frame
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#1E1E2E")
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_frame,
            text="📊 TIKTOK VIDEO LINK EXTRACTOR -> EXCEL",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#38BDF8"
        ).grid(row=0, column=0, padx=15, pady=(12, 2), sticky="w")

        ctk.CTkLabel(
            header_frame,
            text="Quét toàn bộ link video TikTok (Kênh, Profile, Video, Hashtag) và tự động xuất ra file Excel với định dạng cột |link|",
            font=ctk.CTkFont(size=12),
            text_color="#94A3B8"
        ).grid(row=1, column=0, padx=15, pady=(0, 12), sticky="w")

        # 2. Form Inputs Frame
        form_frame = ctk.CTkFrame(self, corner_radius=10)
        form_frame.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        form_frame.grid_columnconfigure(1, weight=1)

        # 2.1 TikTok URL
        ctk.CTkLabel(form_frame, text="Link TikTok (Kênh/Video):", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=15, pady=(15, 8), sticky="w"
        )
        self.url_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Ví dụ: https://www.tiktok.com/@vtv24news hoặc link video",
            height=38
        )
        self.url_entry.grid(row=0, column=1, columnspan=2, padx=(0, 15), pady=(15, 8), sticky="ew")

        # 2.2 Limit & Column name
        options_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        options_row.grid(row=1, column=0, columnspan=3, padx=15, pady=5, sticky="ew")
        options_row.grid_columnconfigure((0, 1), weight=1)

        limit_box = ctk.CTkFrame(options_row, fg_color="transparent")
        limit_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(limit_box, text="Số video tối đa:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.limit_entry = ctk.CTkEntry(limit_box, width=90, height=34)
        self.limit_entry.insert(0, "0")
        self.limit_entry.pack(side="left")
        ctk.CTkLabel(limit_box, text="(0 = Lấy tất cả)", text_color="#64748B", font=ctk.CTkFont(size=12)).pack(side="left", padx=(6, 0))

        col_box = ctk.CTkFrame(options_row, fg_color="transparent")
        col_box.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(col_box, text="Tên cột Excel:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.col_entry = ctk.CTkEntry(col_box, width=120, height=34)
        self.col_entry.insert(0, getattr(config, "EXCEL_COLUMN_NAME", "link"))
        self.col_entry.pack(side="left")

        # 2.3 Custom Output File (Optional)
        ctk.CTkLabel(form_frame, text="File Excel xuất ra:", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=15, pady=8, sticky="w"
        )
        self.output_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Mặc định: tự động lưu vào thư mục exports/ với ngày giờ",
            height=34
        )
        self.output_entry.grid(row=2, column=1, padx=(0, 8), pady=8, sticky="ew")
        self.btn_browse_out = ctk.CTkButton(
            form_frame,
            text="Chọn file...",
            width=95,
            height=34,
            fg_color="#334155",
            hover_color="#475569",
            command=self._browse_output_file
        )
        self.btn_browse_out.grid(row=2, column=2, padx=(0, 15), pady=8, sticky="e")

        # 2.4 Cookie File (Optional)
        ctk.CTkLabel(form_frame, text="Cookie TikTok (tuỳ chọn):", font=ctk.CTkFont(weight="bold")).grid(
            row=3, column=0, padx=15, pady=8, sticky="w"
        )
        self.cookie_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Chọn file cookies.txt nếu TikTok yêu cầu đăng nhập",
            height=34
        )
        default_cookie = getattr(config, "COOKIES_PATH", "data/cookies.txt")
        if os.path.exists(default_cookie):
            self.cookie_entry.insert(0, default_cookie)
        self.cookie_entry.grid(row=3, column=1, padx=(0, 8), pady=8, sticky="ew")
        self.btn_browse_cookie = ctk.CTkButton(
            form_frame,
            text="Chọn cookie...",
            width=95,
            height=34,
            fg_color="#334155",
            hover_color="#475569",
            command=self._browse_cookie_file
        )
        self.btn_browse_cookie.grid(row=3, column=2, padx=(0, 15), pady=8, sticky="e")

        # 2.5 Checkboxes
        check_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        check_frame.grid(row=4, column=0, columnspan=3, padx=15, pady=(5, 15), sticky="ew")

        self.auto_open_var = ctk.BooleanVar(value=True)
        self.auto_open_cb = ctk.CTkCheckBox(
            check_frame,
            text="Tự động mở file Excel sau khi quét xong",
            variable=self.auto_open_var,
            font=ctk.CTkFont(size=12)
        )
        self.auto_open_cb.pack(side="left", padx=(0, 20))

        self.headless_var = ctk.BooleanVar(value=getattr(config, "HEADLESS", False))
        self.headless_cb = ctk.CTkCheckBox(
            check_frame,
            text="Chạy ẩn trình duyệt (Headless)",
            variable=self.headless_var,
            font=ctk.CTkFont(size=12)
        )
        self.headless_cb.pack(side="left")

        # 3. Action Buttons & Status Summary Frame
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=2, column=0, padx=15, pady=5, sticky="ew")
        action_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.start_btn = ctk.CTkButton(
            action_frame,
            text="🚀 BẮT ĐẦU QUÉT & XUẤT EXCEL",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            fg_color="#10B981",
            hover_color="#059669",
            command=self._start_scan
        )
        self.start_btn.grid(row=0, column=0, columnspan=2, padx=4, sticky="ew")

        self.stop_btn = ctk.CTkButton(
            action_frame,
            text="⏹ DỪNG",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=42,
            fg_color="#EF4444",
            hover_color="#DC2626",
            state="disabled",
            command=self._stop_scan
        )
        self.stop_btn.grid(row=0, column=2, padx=4, sticky="ew")

        self.open_exports_btn = ctk.CTkButton(
            action_frame,
            text="📂 MỞ THƯ MỤC EXPORTS",
            font=ctk.CTkFont(size=12),
            height=42,
            fg_color="#3B82F6",
            hover_color="#2563EB",
            command=self._open_exports_dir
        )
        self.open_exports_btn.grid(row=0, column=3, padx=4, sticky="ew")

        # 4. Console Log Frame
        console_frame = ctk.CTkFrame(self, corner_radius=10)
        console_frame.grid(row=3, column=0, padx=15, pady=(5, 15), sticky="nsew")
        console_frame.grid_columnconfigure(0, weight=1)
        console_frame.grid_rowconfigure(1, weight=1)

        console_header = ctk.CTkFrame(console_frame, fg_color="transparent")
        console_header.grid(row=0, column=0, padx=10, pady=(8, 4), sticky="ew")
        console_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            console_header,
            text="📋 Nhật Ký Hoạt Động (Console Logs):",
            font=ctk.CTkFont(weight="bold")
        ).grid(row=0, column=0, sticky="w")

        self.status_badge = ctk.CTkLabel(
            console_header,
            text="🟢 Sẵn sàng",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#10B981"
        )
        self.status_badge.grid(row=0, column=1, sticky="e")

        self.log_textbox = ctk.CTkTextbox(
            console_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#0F172A",
            text_color="#E2E8F0"
        )
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

    def _process_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_textbox.insert(tk.END, msg)
            self.log_textbox.see(tk.END)
        self.after(100, self._process_log_queue)

    def write_log(self, msg: str):
        self.log_queue.put(msg + "\n")

    def _browse_output_file(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook", "*.xlsx"), ("CSV UTF-8", "*.csv"), ("All files", "*.*")],
            title="Chọn nơi lưu file Excel"
        )
        if filename:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, filename)

    def _browse_cookie_file(self):
        filename = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Chọn file cookies.txt (Netscape format)"
        )
        if filename:
            self.cookie_entry.delete(0, tk.END)
            self.cookie_entry.insert(0, filename)

    def _open_exports_dir(self):
        export_dir = os.path.abspath(getattr(config, "DEFAULT_EXPORT_DIR", "exports"))
        os.makedirs(export_dir, exist_ok=True)
        open_file_or_folder(export_dir)

    def _stop_scan(self):
        if self.is_running:
            self.should_stop = True
            self.write_log("[!] Đang yêu cầu dừng quét...")
            self.stop_btn.configure(state="disabled", text="Đang dừng...")

    def _start_scan(self):
        if self.is_running:
            return

        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Thiếu URL", "Vui lòng nhập đường dẫn TikTok cần quét!")
            return

        try:
            limit = int(self.limit_entry.get().strip())
        except ValueError:
            limit = 0

        col_name = self.col_entry.get().strip() or "link"
        output_path = self.output_entry.get().strip() or None
        cookies_path = self.cookie_entry.get().strip() or None
        headless = self.headless_var.get()
        auto_open = self.auto_open_var.get()

        self.is_running = True
        self.should_stop = False

        self.start_btn.configure(state="disabled", text="⏳ ĐANG QUÉT LINK...", fg_color="#64748B")
        self.stop_btn.configure(state="normal", text="⏹ DỪNG")
        self.status_badge.configure(text="🟡 Đang quét...", text_color="#F59E0B")
        self.log_textbox.delete("1.0", tk.END)

        threading.Thread(
            target=self._run_scan_thread,
            args=(url, limit, col_name, output_path, cookies_path, headless, auto_open),
            daemon=True
        ).start()

    def _run_scan_thread(
        self,
        url: str,
        limit: int,
        col_name: str,
        output_path: str,
        cookies_path: str,
        headless: bool,
        auto_open: bool
    ):
        old_stdout = sys.stdout
        sys.stdout = TextRedirector(self.log_queue)

        try:
            print("==================================================")
            print("   BẮT ĐẦU QUÉT LINK TIKTOK & XUẤT EXCEL")
            print("==================================================")
            print(f"[+] Mục tiêu URL: {url}")
            print(f"[+] Giới hạn: {limit if limit > 0 else 'Tất cả'}")
            print(f"[+] Cột Excel: |{col_name}|")

            def stop_checker():
                return self.should_stop

            def on_progress(count, total_limit, current_link):
                # Callback báo tiến độ
                pass

            with sync_playwright() as p:
                links = tiktok_extractor.extract_tiktok_links(
                    p,
                    url=url,
                    limit=limit,
                    headless=headless,
                    cookies_path=cookies_path,
                    progress_callback=on_progress,
                    stop_check=stop_checker
                )

            if not links:
                print("\n❌ Không tìm thấy video nào từ đường dẫn đã cung cấp.")
                return

            print(f"\n[+] Tổng cộng thu thập được: {len(links)} link video.")
            print("[+] Đang xuất dữ liệu ra file Excel...")

            saved_path = exporter.export_to_excel(
                links=links,
                output_path=output_path,
                column_name=col_name,
                export_dir=getattr(config, "DEFAULT_EXPORT_DIR", "exports")
            )

            self.last_exported_file = saved_path
            print(f"🎉 XUẤT THÀNH CÔNG!")
            print(f"📁 Đường dẫn file Excel: {saved_path}")

            if auto_open and os.path.exists(saved_path):
                print("[+] Đang tự động mở file Excel...")
                open_file_or_folder(saved_path)

            self.after(0, lambda: messagebox.showinfo(
                "Thành công",
                f"Đã quét và xuất thành công {len(links)} link video ra file Excel:\n{saved_path}"
            ))

        except Exception as e:
            print(f"\n[ERROR] Có lỗi xảy ra trong quá trình quét: {e}")
            self.after(0, lambda: messagebox.showerror("Lỗi", f"Có lỗi xảy ra: {e}"))
        finally:
            sys.stdout = old_stdout
            self.is_running = False
            self.after(0, self._on_scan_finished)

    def _on_scan_finished(self):
        self.start_btn.configure(state="normal", text="🚀 BẮT ĐẦU QUÉT & XUẤT EXCEL", fg_color="#10B981")
        self.stop_btn.configure(state="disabled", text="⏹ DỪNG")
        self.status_badge.configure(text="🟢 Hoàn tất!", text_color="#10B981")


if __name__ == "__main__":
    app = TikTokLinkExtractorApp()
    app.mainloop()
