# -*- coding: utf-8 -*-
import os
import sys
import shutil
import threading
import queue
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config
import uploader
import scraper
import dedupe
import identity_manager
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
        self.title("TikTok -> UCircle Auto Pipeline (1 TikTok = 1 UCircle)")
        self.geometry("1220x960")
        self.minsize(1050, 850)
        self.is_running = False
        self.log_queue = queue.Queue()
        self.headless_var = ctk.BooleanVar(value=getattr(config, "HEADLESS", False))
        self.identity_checkbox_vars = {}
        self.source_rows = []

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._load_settings()
        self._prevent_mac_sleep()

        self.after(100, self._process_log_queue)
        self.lift()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def _prevent_mac_sleep(self):
        """Trên macOS: Ngăn máy vào chế độ ngủ (System Sleep) khi màn hình tắt để tool chạy liên tục."""
        if sys.platform == "darwin":
            try:
                import subprocess
                subprocess.Popen(
                    ["caffeinate", "-i", "-s", "-w", str(os.getpid())],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#1E1E2E")
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        header_left = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_left.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        ctk.CTkLabel(
            header_left, text="🚀 TikTok -> UCircle Auto Pipeline (1 TikTok = 1 UCircle)",
            font=ctk.CTkFont(size=20, weight="bold"), text_color="#38BDF8"
        ).pack(anchor="w")
        ctk.CTkLabel(
            header_left, text="Mỗi kênh TikTok có ô input riêng và gán đúng Kênh UCircle • Tự động ghi nhớ cấu hình & kênh.",
            font=ctk.CTkFont(size=12), text_color="#94A3B8"
        ).pack(anchor="w", pady=(2, 0))

        header_right = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_right.grid(row=0, column=1, padx=15, pady=10, sticky="e")

        self.headless_checkbox = ctk.CTkCheckBox(
            header_right, text="👁️ Ẩn màn hình (Headless)",
            variable=self.headless_var, font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_headless_toggle
        )
        self.headless_checkbox.pack(side="left", padx=(0, 12))

        self.save_cfg_btn = ctk.CTkButton(
            header_right, text="💾 Lưu Cài Đặt", width=110, height=32,
            fg_color="#3B82F6", hover_color="#2563EB", font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._save_settings(verbose=True)
        )
        self.save_cfg_btn.pack(side="left")

        # Tabview
        self.tabview = ctk.CTkTabview(self, corner_radius=10, command=self._on_tab_changed)
        self.tabview.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        tab_scan = self.tabview.add("🔍 1. Quét TikTok -> Excel (Từng Ô Input Riêng)")
        tab_upload = self.tabview.add("📤 2. Đăng Excel -> UCircle")

        self._build_scan_tab(tab_scan)
        self._build_upload_tab(tab_upload)

        # Console Logs
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

        # Chế độ quét mặc định
        ctk.CTkLabel(form_frame, text="Chế độ quét mặc định:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        self.mode_var = tk.StringVar(value="profile")
        mode_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        mode_box.grid(row=0, column=1, padx=(0, 15), pady=(15, 5), sticky="w")
        ctk.CTkRadioButton(mode_box, text="Theo Profile (kênh TikTok)", variable=self.mode_var, value="profile").pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(mode_box, text="Theo Từ khoá tìm kiếm", variable=self.mode_var, value="keyword").pack(side="left")

        # ---- DANH SÁCH Ô INPUT TIKTOK RIÊNG BIỆT (1 TIKTOK ➡️ 1 UCIRCLE) ----
        sources_header = ctk.CTkFrame(form_frame, fg_color="transparent")
        sources_header.grid(row=1, column=0, columnspan=2, padx=15, pady=(12, 2), sticky="ew")
        sources_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            sources_header, text="📋 Danh Sách Kênh TikTok (Mỗi kênh 1 ô input riêng ➡️ 1 Kênh UCircle tương ứng):",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#38BDF8"
        ).grid(row=0, column=0, sticky="w")

        sources_tools = ctk.CTkFrame(sources_header, fg_color="transparent")
        sources_tools.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            sources_tools, text="➕ Thêm Ô TikTok", width=130, height=28,
            fg_color="#0EA5E9", hover_color="#0284C7", font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._add_source_row()
        ).pack(side="left", padx=3)

        ctk.CTkButton(
            sources_tools, text="🧹 Xoá Hết", width=80, height=28,
            fg_color="#475569", hover_color="#334155", font=ctk.CTkFont(size=11),
            command=self._clear_all_source_rows
        ).pack(side="left", padx=3)

        # Khung cuộn chứa từng ô input riêng biệt cho mỗi kênh TikTok
        self.sources_scroll_frame = ctk.CTkScrollableFrame(form_frame, height=240, corner_radius=8, fg_color="#181825")
        self.sources_scroll_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=(2, 8), sticky="ew")
        self.sources_scroll_frame.grid_columnconfigure(0, weight=1)

        self.source_rows = []
        # Tạo sẵn 1 ô input trống đầu tiên để người dùng điền
        self._add_source_row("", "")

        # Limit + cookie
        options_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        options_frame.grid(row=3, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        options_frame.grid_columnconfigure((0, 1), weight=1)

        limit_box = ctk.CTkFrame(options_frame, fg_color="transparent")
        limit_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(limit_box, text="Số video tối đa mỗi nguồn:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))
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
        self.cookie_entry = ctk.CTkEntry(cookie_box, width=220, height=34, placeholder_text="Chưa chọn file cookie")
        self.cookie_entry.pack(side="left", padx=(0, 5))
        ctk.CTkButton(cookie_box, text="📂 Chọn file...", width=110, height=34,
                      command=lambda: self._browse_cookie_file(self.cookie_entry)).pack(side="left")

        # Ngưỡng lọc chất lượng
        quality_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        quality_box.grid(row=4, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        ctk.CTkLabel(quality_box, text="Lọc chất lượng — Views tối thiểu:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.min_views_entry = ctk.CTkEntry(quality_box, width=90, height=34)
        self.min_views_entry.insert(0, str(config.MIN_VIEWS))
        self.min_views_entry.pack(side="left", padx=(0, 15))

        ctk.CTkLabel(quality_box, text="Likes tối thiểu:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.min_likes_entry = ctk.CTkEntry(quality_box, width=90, height=34)
        self.min_likes_entry.insert(0, str(config.MIN_LIKES))
        self.min_likes_entry.pack(side="left", padx=(0, 15))

        ctk.CTkLabel(quality_box, text="Độ phân giải tối thiểu (px):", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.min_res_entry = ctk.CTkEntry(quality_box, width=70, height=34)
        self.min_res_entry.insert(0, str(config.MIN_RESOLUTION_HEIGHT))
        self.min_res_entry.pack(side="left", padx=(0, 15))

        ctk.CTkLabel(quality_box, text="Thời lượng tối đa:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.max_duration_entry = ctk.CTkEntry(quality_box, width=65, height=34)
        self.max_duration_entry.insert(0, str(getattr(config, "MAX_DURATION_SEC", 180)))
        self.max_duration_entry.pack(side="left", padx=(0, 4))
        ctk.CTkLabel(quality_box, text="giây (<3p)", text_color="#94A3B8").pack(side="left")

        # Tuỳ chọn chống trùng lịch sử & Công cụ phiên TikTok
        dedupe_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        dedupe_box.grid(row=5, column=0, columnspan=2, padx=15, pady=3, sticky="ew")
        self.dedupe_history_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            dedupe_box, text="🛡️ Tự động né video cũ",
            variable=self.dedupe_history_var, font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")

        ctk.CTkButton(
            dedupe_box, text="🌐 Mở TikTok / Đăng Nhập", width=180, height=28,
            fg_color="#6366F1", hover_color="#4F46E5", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._open_tiktok_browser
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            dedupe_box, text="🧹 Xoá lịch sử quét", width=130, height=28,
            fg_color="#475569", hover_color="#334155", font=ctk.CTkFont(size=11),
            command=self._clear_scanned_history
        ).pack(side="right")

        # Số luồng quét
        MAX_THREADS = 8
        scrape_slider_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        scrape_slider_box.grid(row=6, column=0, columnspan=2, padx=15, pady=(5, 15), sticky="ew")
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

        # Action Buttons (tab quét)
        action_frame = ctk.CTkFrame(parent, fg_color="transparent")
        action_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        action_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.scan_btn = ctk.CTkButton(
            action_frame, text="🔍 QUÉT & LỌC -> EXCEL", font=ctk.CTkFont(size=14, weight="bold"),
            height=42, fg_color="#0EA5E9", hover_color="#0284C7", command=self._start_scan
        )
        self.scan_btn.grid(row=0, column=0, padx=4, sticky="ew")

        self.stop_scan_btn = ctk.CTkButton(
            action_frame, text="🛑 DỪNG QUÉT", font=ctk.CTkFont(size=13, weight="bold"),
            height=42, fg_color="#475569", hover_color="#DC2626", state="disabled", command=self._stop_process
        )
        self.stop_scan_btn.grid(row=0, column=1, padx=4, sticky="ew")

        self.download_excel_btn = ctk.CTkButton(
            action_frame, text="📥 Tải file Excel", font=ctk.CTkFont(size=13),
            height=42, fg_color="#F59E0B", hover_color="#D97706", command=self._download_excel
        )
        self.download_excel_btn.grid(row=0, column=2, padx=4, sticky="ew")

    def _update_all_dropdown_options(self):
        """Cập nhật lại danh sách lựa chọn trong dropdown của tất cả các ô TikTok:
        - Circle đã được chọn ở ô khác sẽ tự động bị ẨN ĐI để tránh chọn trùng lặp.
        - Mỗi ô chỉ hiển thị Circle hiện tại của chính nó + các Circle chưa bị ô nào khác gán."""
        identities = identity_manager.load_identities()
        channel_names = [item["name"] for item in identities] or ["Tôi (Trang cá nhân)"]

        if not hasattr(self, "source_rows") or not self.source_rows:
            return

        for r in self.source_rows:
            my_circle = r["dropdown"].get().strip()
            # Danh sách các Circle đã bị những ô KHÁC chọn
            other_chosen = {
                other_r["dropdown"].get().strip()
                for other_r in self.source_rows
                if other_r is not r and other_r["dropdown"].get().strip()
            }
            # Lựa chọn cho ô này: Circle hiện tại của chính nó + các Circle chưa có ai chọn
            available = [c for c in channel_names if c == my_circle or c not in other_chosen]
            if not available:
                available = channel_names

            r["dropdown"].configure(values=available)
            if my_circle not in available and available:
                r["dropdown"].set(available[0])

    def _add_source_row(self, initial_url: str = "", initial_circle: str = None):
        """Thêm 1 hàng ô input TikTok riêng biệt.
        Nếu Circle đầu tiên đã có ô chọn thì ô mới sẽ tự động chọn Circle tiếp theo và ẩn Circle đã chọn."""
        identities = identity_manager.load_identities()
        channel_names = [item["name"] for item in identities] or ["Tôi (Trang cá nhân)"]

        # Các Circle đã được chọn ở các hàng hiện có
        chosen_so_far = {r["dropdown"].get().strip() for r in getattr(self, "source_rows", []) if r.get("dropdown")}
        available_for_new = [c for c in channel_names if c not in chosen_so_far]
        if not available_for_new:
            available_for_new = channel_names

        if initial_circle and initial_circle in channel_names:
            selected_circle = initial_circle
        else:
            selected_circle = available_for_new[0]

        row_frame = ctk.CTkFrame(self.sources_scroll_frame, fg_color="#1E1E2E", corner_radius=6)
        row_frame.pack(fill="x", padx=4, pady=3)
        row_frame.grid_columnconfigure(1, weight=1)

        idx_label = ctk.CTkLabel(row_frame, text=f"#{len(self.source_rows) + 1}", width=36,
                                 font=ctk.CTkFont(size=13, weight="bold"), text_color="#38BDF8")
        idx_label.grid(row=0, column=0, padx=(8, 4), pady=5)

        entry = ctk.CTkEntry(row_frame, placeholder_text="Nhập link kênh TikTok (@username, URL, hoặc từ khoá)...", height=36)
        if initial_url:
            entry.insert(0, initial_url)
        entry.grid(row=0, column=1, padx=4, pady=5, sticky="ew")
        entry.bind("<FocusOut>", lambda _: self._save_settings(verbose=False))

        arrow_lbl = ctk.CTkLabel(row_frame, text="➡️ Đăng vào:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#10B981")
        arrow_lbl.grid(row=0, column=2, padx=(8, 4), pady=5)

        def on_dropdown_changed(_):
            self._update_all_dropdown_options()
            self._sync_tab1_to_tab2_checkboxes()
            self._save_settings(verbose=False)

        dropdown = ctk.CTkOptionMenu(
            row_frame, values=channel_names, width=205, height=36,
            command=on_dropdown_changed
        )
        dropdown.set(selected_circle)
        dropdown.grid(row=0, column=3, padx=4, pady=5)

        status_lbl = ctk.CTkLabel(row_frame, text="⚪ Chờ", width=100, font=ctk.CTkFont(size=12, weight="bold"), text_color="#94A3B8")
        status_lbl.grid(row=0, column=4, padx=4, pady=5)

        row_data = {
            "frame": row_frame,
            "idx_label": idx_label,
            "entry": entry,
            "dropdown": dropdown,
            "status_lbl": status_lbl,
        }

        rescan_btn = ctk.CTkButton(
            row_frame, text="🔄 Quét lại", width=90, height=34,
            fg_color="#3B82F6", hover_color="#2563EB", font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._rescan_single_row(row_data)
        )
        rescan_btn.grid(row=0, column=5, padx=4, pady=5)
        row_data["rescan_btn"] = rescan_btn

        def delete_row():
            if len(self.source_rows) <= 1:
                entry.delete(0, tk.END)
                status_lbl.configure(text="⚪ Chờ", text_color="#94A3B8")
                self._update_all_dropdown_options()
                self._sync_tab1_to_tab2_checkboxes()
                self._save_settings(verbose=False)
                return
            row_frame.destroy()
            if row_data in self.source_rows:
                self.source_rows.remove(row_data)
            self._renumber_source_rows()
            self._update_all_dropdown_options()
            self._sync_tab1_to_tab2_checkboxes()
            self._save_settings(verbose=False)

        del_btn = ctk.CTkButton(row_frame, text="✕", width=34, height=34, fg_color="#EF4444", hover_color="#DC2626", font=ctk.CTkFont(size=13, weight="bold"), command=delete_row)
        del_btn.grid(row=0, column=6, padx=(4, 8), pady=5)

        self.source_rows.append(row_data)
        self._update_all_dropdown_options()
        self._sync_tab1_to_tab2_checkboxes()

    def _renumber_source_rows(self):
        """Cập nhật lại số thứ tự #1, #2, #3... cho các hàng input."""
        for i, r in enumerate(self.source_rows, 1):
            r["idx_label"].configure(text=f"#{i}")

    def _clear_all_source_rows(self):
        """Xoá toàn bộ hàng và chỉ giữ lại 1 ô input trống."""
        for r in list(self.source_rows):
            r["frame"].destroy()
        self.source_rows.clear()
        self._add_source_row()
        self._update_all_dropdown_options()
        self._sync_tab1_to_tab2_checkboxes()
        self._save_settings(verbose=False)

    def _rescan_single_row(self, row_data):
        """Quét lại riêng duy nhất 1 hàng TikTok đã chọn và lưu nối tiếp vào Excel."""
        if self.is_running:
            messagebox.showinfo("Đang bận", "Hệ thống đang thực hiện một tác vụ khác. Vui lòng chờ hoàn tất!")
            return

        url = row_data["entry"].get().strip()
        target_circle = row_data["dropdown"].get().strip()
        if not url:
            messagebox.showwarning("Chưa nhập link", "Vui lòng nhập link kênh TikTok vào ô input trước khi quét lại!")
            return

        self._save_settings(verbose=False)
        config.STOP_REQUESTED = False
        config.HEADLESS = self.headless_var.get()

        is_keyword = self.mode_var.get() == "keyword"
        limit = self._int_or(self.limit_entry, 0)
        scrape_threads = int(self.scrape_threads_slider.get())
        min_views = self._int_or(self.min_views_entry, config.MIN_VIEWS)
        min_likes = self._int_or(self.min_likes_entry, config.MIN_LIKES)
        min_res = self._int_or(self.min_res_entry, config.MIN_RESOLUTION_HEIGHT)
        max_dur = self._int_or(self.max_duration_entry, getattr(config, "MAX_DURATION_SEC", 180))
        cookies_path = self.cookie_entry.get().strip() or None
        browser_cookie = self.browser_menu.get()
        if browser_cookie == "Không dùng":
            browser_cookie = None
        exclude_history = self.dedupe_history_var.get()

        row_data["status_lbl"].configure(text="🟡 Đang quét...", text_color="#F59E0B")
        self._set_busy(True, f"🟡 Đang quét lại {url}...", "#F59E0B")

        def task():
            old_stdout = sys.stdout
            sys.stdout = TextRedirector(self.log_queue)
            try:
                with sync_playwright() as p:
                    res = scraper.scrape_single_source(
                        p, url, target_circle=target_circle, is_keyword=is_keyword,
                        limit=limit, scrape_threads=scrape_threads,
                        min_views=min_views, min_likes=min_likes, min_resolution=min_res,
                        max_duration=max_dur,
                        cookies_path=cookies_path, browser_cookie=browser_cookie,
                        exclude_history=exclude_history,
                    )
                passed = res.get("passed", 0)
                found = res.get("found", 0)
                issue = res.get("issue")

                def update_ui():
                    if passed > 0:
                        row_data["status_lbl"].configure(text=f"✅ {passed} video", text_color="#10B981")
                        messagebox.showinfo(
                            "Quét lại thành công",
                            f"🎉 Kênh: {url}\n\nĐã thu thập và lưu thêm {passed} video mới vào Excel!"
                        )
                    elif found == 0:
                        row_data["status_lbl"].configure(text="❌ 0 video", text_color="#EF4444")
                        messagebox.showwarning(
                            "Quét lại thất bại (0 video)",
                            f"⚠️ Không tìm thấy video nào từ kênh:\n{url}\n\n"
                            f"Lý do: {issue or 'Trang trống, sai link hoặc vướng Captcha'}\n\n"
                            f"👉 Vui lòng kiểm tra lại link kênh hoặc mở trình duyệt xem có bị Captcha không!"
                        )
                    else:
                        row_data["status_lbl"].configure(text=f"⚠️ 0/{found} đạt", text_color="#F59E0B")
                        messagebox.showwarning(
                            "Chưa đạt chuẩn",
                            f"⚠️ Thu thập được {found} video nhưng không có video nào đạt ngưỡng views/likes.\n"
                            f"Bạn có thể giảm mức lọc views/likes để lấy video."
                        )

                self.after(0, update_ui)
                self.after(0, self._sync_tab1_to_tab2_checkboxes)
            except Exception as e:
                print(f"[ERROR] Lỗi khi quét lại {url}: {e}")
                self.after(0, lambda: row_data["status_lbl"].configure(text="❌ Lỗi", text_color="#EF4444"))
            finally:
                sys.stdout = old_stdout
                self.after(0, lambda: self._set_busy(False, "🟢 Sẵn sàng", "#10B981"))

        threading.Thread(target=task, daemon=True).start()

    def _build_upload_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        form_frame = ctk.CTkFrame(parent, corner_radius=10)
        form_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        form_frame.grid_columnconfigure(1, weight=1)

        # ---- KHU VỰC QUẢN LÝ VÀ CHỌN KÊNH UCIRCLE (ID + TÊN) ----
        id_header = ctk.CTkFrame(form_frame, fg_color="transparent")
        id_header.grid(row=0, column=0, columnspan=2, padx=15, pady=(12, 2), sticky="ew")
        id_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            id_header, text="🏷️ Danh Sách Kênh/Fanpage UCircle Đăng Video (Tên + ID):",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#38BDF8"
        ).grid(row=0, column=0, sticky="w")

        id_tools = ctk.CTkFrame(id_header, fg_color="transparent")
        id_tools.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(id_tools, text="➕ Thêm Kênh", width=95, height=28, fg_color="#0284C7", hover_color="#0369A1",
                      command=self._show_add_identity_dialog).pack(side="left", padx=3)
        ctk.CTkButton(id_tools, text="🔄 Quét từ UCircle", width=125, height=28, fg_color="#8B5CF6", hover_color="#7C3AED",
                      command=self._sync_identities_ucircle).pack(side="left", padx=3)
        ctk.CTkButton(id_tools, text="🎯 Tích theo Tab Quét", width=135, height=28, fg_color="#10B981", hover_color="#059669",
                      font=ctk.CTkFont(size=11, weight="bold"),
                      command=self._sync_tab1_to_tab2_checkboxes).pack(side="left", padx=3)
        ctk.CTkButton(id_tools, text="☑️ Chọn/Bỏ hết", width=95, height=28, fg_color="#475569", hover_color="#334155",
                      command=self._toggle_all_identities).pack(side="left", padx=3)
        ctk.CTkButton(id_tools, text="🗑️ Xoá", width=65, height=28, fg_color="#DC2626", hover_color="#B91C1C",
                      command=self._delete_selected_identities).pack(side="left", padx=3)

        # Scrollable Frame chứa danh sách Checkbox Kênh
        self.identities_frame = ctk.CTkScrollableFrame(form_frame, height=200, corner_radius=8, fg_color="#181825")
        self.identities_frame.grid(row=1, column=0, columnspan=2, padx=15, pady=(2, 6), sticky="ew")
        self.identities_frame.grid_columnconfigure(0, weight=1)
        self._reload_identity_checkboxes()

        # Chế độ đăng lên UCircle
        dist_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        dist_box.grid(row=2, column=0, columnspan=2, padx=15, pady=4, sticky="w")
        ctk.CTkLabel(dist_box, text="Chế độ đăng:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 15))
        self.dist_mode_var = tk.StringVar(value=getattr(config, "DISTRIBUTION_MODE", "round_robin"))
        ctk.CTkRadioButton(
            dist_box, text="🎯 Đúng Circle đã chọn (Video kênh nào CHỈ đăng vào Circle đó - Khuyên dùng)",
            variable=self.dist_mode_var, value="round_robin"
        ).pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(
            dist_box, text="📢 Đăng chéo (1 video đăng lên TẤT CẢ các Circle đang tích)",
            variable=self.dist_mode_var, value="all"
        ).pack(side="left")

        # Cookie TikTok
        cookie_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        cookie_box.grid(row=3, column=0, columnspan=2, padx=15, pady=5, sticky="w")
        ctk.CTkLabel(cookie_box, text="Cookie TikTok (để tải video khi đăng):", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))
        self.upload_browser_menu = ctk.CTkOptionMenu(cookie_box, values=["chrome", "edge", "firefox", "brave", "Không dùng"], width=100, height=34)
        self.upload_browser_menu.set("Không dùng")
        self.upload_browser_menu.pack(side="left", padx=(0, 5))
        self.upload_cookie_entry = ctk.CTkEntry(cookie_box, width=220, height=34, placeholder_text="Chưa chọn file cookie")
        self.upload_cookie_entry.pack(side="left", padx=(0, 5))
        ctk.CTkButton(cookie_box, text="📂 Chọn file...", width=110, height=34,
                      command=lambda: self._browse_cookie_file(self.upload_cookie_entry)).pack(side="left")

        # Delay giữa các lần đăng (Min - Max)
        delay_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        delay_box.grid(row=4, column=0, columnspan=2, padx=15, pady=5, sticky="w")
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
        crosspost_box.grid(row=5, column=0, columnspan=2, padx=15, pady=5, sticky="w")
        self.crosspost_var = ctk.BooleanVar(value=getattr(config, "CROSSPOST_TO_FEED", True))
        ctk.CTkCheckBox(
            crosspost_box, text="📣 Lên bảng tin (Bật/tắt nút đăng lên bảng tin UCircle)",
            variable=self.crosspost_var, font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left")

        # Số luồng đăng
        MAX_THREADS = 8
        upload_slider_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        upload_slider_box.grid(row=6, column=0, columnspan=2, padx=15, pady=(5, 15), sticky="ew")
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

        # Action Buttons (tab đăng)
        action_frame = ctk.CTkFrame(parent, fg_color="transparent")
        action_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        action_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.upload_btn = ctk.CTkButton(
            action_frame, text="📤 ĐĂNG EXCEL LÊN UCIRCLE", font=ctk.CTkFont(size=14, weight="bold"),
            height=42, fg_color="#10B981", hover_color="#059669", command=self._start_upload
        )
        self.upload_btn.grid(row=0, column=0, padx=4, sticky="ew")

        self.stop_upload_btn = ctk.CTkButton(
            action_frame, text="🛑 DỪNG ĐĂNG", font=ctk.CTkFont(size=13, weight="bold"),
            height=42, fg_color="#475569", hover_color="#DC2626", state="disabled", command=self._stop_process
        )
        self.stop_upload_btn.grid(row=0, column=1, padx=4, sticky="ew")

        self.login_btn = ctk.CTkButton(
            action_frame, text="🔐 Đăng Nhập UCircle", font=ctk.CTkFont(size=13),
            height=42, fg_color="#6366F1", hover_color="#4F46E5", command=self._login_ucircle
        )
        self.login_btn.grid(row=0, column=2, padx=4, sticky="ew")
        self._sync_tab1_to_tab2_checkboxes()

    def _reload_identity_checkboxes(self):
        """Xoá và nạp lại danh sách Checkbox Kênh từ identity_manager."""
        for widget in self.identities_frame.winfo_children():
            widget.destroy()

        identities = identity_manager.load_identities()
        prev_states = {k: v.get() for k, v in self.identity_checkbox_vars.items()}
        self.identity_checkbox_vars = {}

        if not identities:
            ctk.CTkLabel(self.identities_frame, text="Chưa có kênh nào. Bấm '+ Thêm Kênh' hoặc 'Quét từ UCircle' để thêm.",
                         text_color="#94A3B8").pack(pady=10)
            return

        for idx, item in enumerate(identities):
            id_val = item["id"]
            name = item["name"]

            init_val = prev_states.get(id_val, False)
            var = ctk.BooleanVar(value=init_val)
            self.identity_checkbox_vars[id_val] = var

            display_text = f"📌 {name}   [ID: {id_val[:8]}...]" if len(id_val) > 15 else f"📌 {name}   [ID: {id_val}]"
            cb = ctk.CTkCheckBox(
                self.identities_frame, text=display_text, variable=var,
                font=ctk.CTkFont(size=12), text_color="#E2E8F0"
            )
            cb.pack(anchor="w", padx=10, pady=3)

        # Cập nhật lại dropdown trong các ô input TikTok ở Tab 1 (ẩn các circle đã bị ô khác chọn)
        self._update_all_dropdown_options()

        # Tự động tích chọn theo các Circle đã chọn ở Tab 1
        self._sync_tab1_to_tab2_checkboxes()

    def _on_tab_changed(self):
        """Khi người dùng bấm chuyển qua lại giữa các Tab."""
        try:
            cur_tab = self.tabview.get()
            if "Đăng" in cur_tab:
                self._sync_tab1_to_tab2_checkboxes()
        except Exception:
            pass

    def _sync_tab1_to_tab2_checkboxes(self):
        """Tự động tích chọn các Circle bên Tab Đăng (Tab 2) khớp chính xác với các Circle đang có ở Tab Quét (Tab 1)."""
        if not hasattr(self, "identity_checkbox_vars") or not self.identity_checkbox_vars:
            return

        try:
            identities = identity_manager.load_identities()
            name_to_id = {item["name"].strip(): item["id"] for item in identities}
            id_set = {item["id"] for item in identities}

            target_names_or_ids = set()

            # Chỉ thu thập Circle từ các hàng ô input hiện đang có ở Tab 1
            for r in getattr(self, "source_rows", []):
                try:
                    chosen = r["dropdown"].get().strip()
                    if chosen:
                        target_names_or_ids.add(chosen)
                except Exception:
                    pass

            selected_ids = set()
            for item in target_names_or_ids:
                if item in name_to_id:
                    selected_ids.add(name_to_id[item])
                elif item in id_set:
                    selected_ids.add(item)

            # Cập nhật TOÀN BỘ checkbox ở Tab 2:
            # - Chỉ tích True nếu kênh đó đang có mặt ở Tab 1
            # - Khi người dùng xoá hàng nào ở Tab 1, kênh đó sẽ lập tức bị BỎ TÍCH ở Tab 2!
            # - Nếu xoá hết: toàn bộ checkbox Tab 2 sẽ là False.
            for id_val, var in self.identity_checkbox_vars.items():
                var.set(id_val in selected_ids)
        except Exception:
            pass

    def _get_selected_identity_ids(self) -> list:
        chosen = [id_val for id_val, var in self.identity_checkbox_vars.items() if var.get()]
        if not chosen:
            identities = identity_manager.load_identities()
            if identities:
                return [identities[0]["id"]]
            return ["me"]
        return chosen

    def _show_add_identity_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Thêm Kênh / Fanpage UCircle")
        dialog.geometry("600x260")
        dialog.grab_set()
        dialog.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dialog, text="Tên Kênh / Fanpage:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=15, pady=(20, 5), sticky="w"
        )
        name_entry = ctk.CTkEntry(dialog, placeholder_text="Ví dụ: Gái Xinh, Xe Độ, Game Hay...")
        name_entry.grid(row=0, column=1, padx=15, pady=(20, 5), sticky="ew")

        ctk.CTkLabel(dialog, text="Mã ID hoặc Link UCircle:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=15, pady=10, sticky="w"
        )
        id_entry = ctk.CTkEntry(dialog, placeholder_text="Mã UUID, hoặc dán link https://ucircle.net/app/c/..., hoặc 'me'")
        id_entry.grid(row=1, column=1, padx=15, pady=10, sticky="ew")

        status_lbl = ctk.CTkLabel(dialog, text="", text_color="#EF4444")
        status_lbl.grid(row=2, column=0, columnspan=2, padx=15, pady=2)

        def save():
            name = name_entry.get().strip()
            raw_id = id_entry.get().strip()
            if not raw_id:
                status_lbl.configure(text="Vui lòng nhập ID hoặc Link trang UCircle!")
                return
            try:
                item = identity_manager.add_identity(name, raw_id)
                self._reload_identity_checkboxes()
                if item["id"] in self.identity_checkbox_vars:
                    self.identity_checkbox_vars[item["id"]].set(True)
                dialog.destroy()
                self.write_log(f"✅ Đã thêm kênh: {item['name']} [ID: {item['id']}]")
            except Exception as e:
                status_lbl.configure(text=str(e))

        ctk.CTkButton(
            dialog, text="💾 Lưu Kênh", font=ctk.CTkFont(weight="bold"),
            height=36, fg_color="#10B981", hover_color="#059669", command=save
        ).grid(row=3, column=0, columnspan=2, padx=15, pady=(10, 15), sticky="ew")

    def _delete_selected_identities(self):
        selected = [id_val for id_val, var in self.identity_checkbox_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo("Thông báo", "Hãy tích chọn kênh bạn muốn xoá trước.")
            return

        to_delete = [id_val for id_val in selected if id_val != "me"]
        if not to_delete:
            messagebox.showwarning("Cảnh báo", "Không thể xoá 'Tôi (Trang cá nhân)'.")
            return

        if messagebox.askyesno("Xác nhận", f"Bạn có chắc muốn xoá {len(to_delete)} kênh đã chọn khỏi danh bạ?"):
            for id_val in to_delete:
                identity_manager.remove_identity(id_val)
            self._reload_identity_checkboxes()
            self.write_log(f"🧹 Đã xoá {len(to_delete)} kênh khỏi danh bạ.")

    def _toggle_all_identities(self):
        all_checked = all(var.get() for var in self.identity_checkbox_vars.values()) if self.identity_checkbox_vars else False
        new_val = not all_checked
        for var in self.identity_checkbox_vars.values():
            var.set(new_val)

    def _sync_identities_ucircle(self):
        if self.is_running:
            return
        if not os.path.exists(config.STORAGE_STATE_PATH):
            messagebox.showwarning("Lỗi", "Chưa có session UCircle. Vui lòng bấm 'Đăng Nhập UCircle (Lần đầu)' trước!")
            return

        self._set_busy(True, "🟡 Đang quét Circle...", "#8B5CF6")
        self.write_log("[*] Đang mở UCircle -> Circle -> Sở hữu / Quản trị để lấy toàn bộ danh sách Kênh...")

        def task():
            old_stdout = sys.stdout
            sys.stdout = TextRedirector(self.log_queue)
            try:
                with sync_playwright() as p:
                    new_list = identity_manager.sync_identities_from_ucircle(p)
                print(f"[+] Đồng bộ thành công! Tìm thấy {len(new_list)} Kênh/Fanpage trên UCircle.")
                self.after(0, self._reload_identity_checkboxes)
                self.after(0, lambda: messagebox.showinfo(
                    "Đồng bộ thành công",
                    f"🎉 Đã tìm thấy và cập nhật {len(new_list)} Kênh/Circle vào hệ thống!\n"
                    f"Danh sách đã được tự động nạp vào Tab 1 và Tab 2."
                ))
            except Exception as e:
                print(f"[ERROR] Lỗi đồng bộ Kênh UCircle: {e}")
                self.after(0, lambda: messagebox.showerror("Lỗi", f"Không thể đồng bộ Kênh UCircle: {e}"))
            finally:
                sys.stdout = old_stdout
                self.after(0, lambda: self._set_busy(False, "🟢 Sẵn sàng", "#10B981"))

        threading.Thread(target=task, daemon=True).start()

    # ---- CÁC HÀM XỬ LÝ TIẾN TRÌNH CHUNG ----
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

    def _on_headless_toggle(self):
        val = self.headless_var.get()
        config.HEADLESS = val
        mode_str = "ẩn màn hình (chạy ngầm)" if val else "hiện màn hình trình duyệt"
        self.write_log(f"⚙️ [CHẾ ĐỘ TRÌNH DUYỆT] Đã chuyển sang: {mode_str}")
        self._save_settings(verbose=False)

    def _stop_process(self):
        if not self.is_running:
            return
        config.STOP_REQUESTED = True
        self.write_log("\n🛑 [DỪNG TIẾN TRÌNH] Đang gửi yêu cầu dừng... Vui lòng đợi trong giây lát để hệ thống thoát an toàn!")
        self.status_badge.configure(text="🛑 Đang dừng...", text_color="#EF4444")
        if hasattr(self, "stop_scan_btn"):
            self.stop_scan_btn.configure(state="disabled", fg_color="#991B1B")
        if hasattr(self, "stop_upload_btn"):
            self.stop_upload_btn.configure(state="disabled", fg_color="#991B1B")

    def _set_busy(self, busy: bool, status_text: str, status_color: str):
        self.is_running = busy
        state = "disabled" if busy else "normal"
        self.scan_btn.configure(state=state)
        self.upload_btn.configure(state=state)
        self.login_btn.configure(state=state)
        self.download_excel_btn.configure(state=state)
        self.status_badge.configure(text=status_text, text_color=status_color)

        if busy:
            if hasattr(self, "stop_scan_btn"):
                self.stop_scan_btn.configure(state="normal", fg_color="#DC2626")
            if hasattr(self, "stop_upload_btn"):
                self.stop_upload_btn.configure(state="normal", fg_color="#DC2626")
        else:
            config.STOP_REQUESTED = False
            if hasattr(self, "stop_scan_btn"):
                self.stop_scan_btn.configure(state="disabled", fg_color="#475569")
            if hasattr(self, "stop_upload_btn"):
                self.stop_upload_btn.configure(state="disabled", fg_color="#475569")

    def _on_closing(self):
        try:
            self._save_settings(verbose=False)
        except Exception:
            pass
        self.destroy()

    def _save_settings(self, verbose: bool = False):
        """Lưu toàn bộ cấu hình form và danh sách kênh TikTok vào file data/gui_settings.json."""
        try:
            os.makedirs(os.path.dirname(config.GUI_SETTINGS_PATH), exist_ok=True)
            sources_data = []
            for r in getattr(self, "source_rows", []):
                u = r["entry"].get().strip()
                c = r["dropdown"].get().strip()
                sources_data.append({"url": u, "circle": c})

            import json
            settings = {
                "headless": bool(self.headless_var.get()),
                "mode": self.mode_var.get(),
                "sources": sources_data,
                "limit": self.limit_entry.get().strip(),
                "browser_cookie": self.browser_menu.get(),
                "cookie_path": self.cookie_entry.get().strip(),
                "min_views": self.min_views_entry.get().strip(),
                "min_likes": self.min_likes_entry.get().strip(),
                "min_res": self.min_res_entry.get().strip(),
                "max_duration": self.max_duration_entry.get().strip(),
                "dedupe_history": bool(self.dedupe_history_var.get()),
                "scrape_threads": int(self.scrape_threads_slider.get()),
                "dist_mode": self.dist_mode_var.get(),
                "upload_browser_cookie": self.upload_browser_menu.get(),
                "upload_cookie_path": self.upload_cookie_entry.get().strip(),
                "min_delay": self.min_delay_entry.get().strip(),
                "max_delay": self.max_delay_entry.get().strip(),
                "crosspost": bool(self.crosspost_var.get()),
                "upload_threads": int(self.upload_threads_slider.get()),
            }

            with open(config.GUI_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)

            if verbose:
                self.write_log("💾 [CẤU HÌNH] Đã lưu thành công toàn bộ cài đặt & danh sách kênh TikTok!")
                messagebox.showinfo("Đã lưu cài đặt", "✅ Toàn bộ cấu hình và danh sách kênh đã được ghi nhớ!\nLần sau mở app sẽ tự động nạp lại.")
        except Exception as e:
            if verbose:
                self.write_log(f"❌ [LỖI] Không thể lưu cấu hình: {e}")

    def _load_settings(self):
        """Nạp lại cấu hình đã lưu từ file data/gui_settings.json."""
        if not os.path.exists(config.GUI_SETTINGS_PATH):
            return

        import json
        try:
            with open(config.GUI_SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[!] Không thể đọc gui_settings.json: {e}")
            return

        try:
            # 1. Headless
            if "headless" in data:
                h_val = bool(data["headless"])
                self.headless_var.set(h_val)
                config.HEADLESS = h_val

            # 2. Mode
            if "mode" in data and data["mode"] in ["profile", "keyword"]:
                self.mode_var.set(data["mode"])

            # 3. Sources (Kênh TikTok & Circle)
            saved_sources = data.get("sources", [])
            if saved_sources and isinstance(saved_sources, list):
                for r in list(self.source_rows):
                    r["frame"].destroy()
                self.source_rows.clear()
                for item in saved_sources:
                    u = item.get("url", "")
                    c = item.get("circle", "")
                    self._add_source_row(initial_url=u, initial_circle=c)

            # 4. Limit & Cookies
            if "limit" in data:
                self.limit_entry.delete(0, tk.END)
                self.limit_entry.insert(0, str(data["limit"]))
            if "browser_cookie" in data:
                self.browser_menu.set(data["browser_cookie"])
            if "cookie_path" in data and data["cookie_path"]:
                self.cookie_entry.delete(0, tk.END)
                self.cookie_entry.insert(0, data["cookie_path"])

            # 5. Quality filters
            if "min_views" in data:
                self.min_views_entry.delete(0, tk.END)
                self.min_views_entry.insert(0, str(data["min_views"]))
            if "min_likes" in data:
                self.min_likes_entry.delete(0, tk.END)
                self.min_likes_entry.insert(0, str(data["min_likes"]))
            if "min_res" in data:
                self.min_res_entry.delete(0, tk.END)
                self.min_res_entry.insert(0, str(data["min_res"]))
            if "max_duration" in data:
                self.max_duration_entry.delete(0, tk.END)
                self.max_duration_entry.insert(0, str(data["max_duration"]))

            # 6. Dedupe & Scrape Threads
            if "dedupe_history" in data:
                self.dedupe_history_var.set(bool(data["dedupe_history"]))
            if "scrape_threads" in data:
                val = int(data["scrape_threads"])
                self.scrape_threads_slider.set(val)
                self.scrape_threads_value_label.configure(text=str(val))

            # 7. Distribution Mode
            if "dist_mode" in data and data["dist_mode"] in ["round_robin", "all"]:
                self.dist_mode_var.set(data["dist_mode"])

            # 8. Upload Cookie
            if "upload_browser_cookie" in data:
                self.upload_browser_menu.set(data["upload_browser_cookie"])
            if "upload_cookie_path" in data and data["upload_cookie_path"]:
                self.upload_cookie_entry.delete(0, tk.END)
                self.upload_cookie_entry.insert(0, data["upload_cookie_path"])

            # 9. Delay Min / Max
            if "min_delay" in data:
                self.min_delay_entry.delete(0, tk.END)
                self.min_delay_entry.insert(0, str(data["min_delay"]))
            if "max_delay" in data:
                self.max_delay_entry.delete(0, tk.END)
                self.max_delay_entry.insert(0, str(data["max_delay"]))

            # 10. Crosspost & Upload Threads
            if "crosspost" in data:
                self.crosspost_var.set(bool(data["crosspost"]))
            if "upload_threads" in data:
                val = int(data["upload_threads"])
                self.upload_threads_slider.set(val)
                self.upload_threads_value_label.configure(text=str(val))

            # Đồng bộ lại dropdown (ẩn các circle đã chọn) và checkbox Tab 2
            self._update_all_dropdown_options()
            self._sync_tab1_to_tab2_checkboxes()
        except Exception as e:
            print(f"[!] Lỗi khi khôi phục cấu hình: {e}")


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

    def _open_tiktok_browser(self):
        """Mở trình duyệt TikTok tương tác để người dùng đăng nhập hoặc giải trước Captcha."""
        if self.is_running:
            messagebox.showwarning("Thông báo", "Tool đang thực hiện tác vụ khác, vui lòng đợi xong!")
            return

        def task():
            old_stdout = sys.stdout
            sys.stdout = TextRedirector(self.log_queue)
            self._set_busy(True, "🌐 Đang mở trình duyệt TikTok...", "#6366F1")
            try:
                import tiktok_extractor
                tiktok_extractor.open_tiktok_interactive_session()
                self.after(0, lambda: messagebox.showinfo(
                    "TikTok Session",
                    "✅ Đã lưu hồ sơ phiên TikTok thành công!\n"
                    "Các cookie và trạng thái xác minh đã được lưu vào data/tiktok_profile.\n"
                    "Khi bạn quét video, tool sẽ sử dụng hồ sơ này để không bị vướng Captcha nữa."
                ))
            except Exception as e:
                print(f"[ERROR] Lỗi mở trình duyệt TikTok: {e}")
                self.after(0, lambda: messagebox.showerror("Lỗi", f"Không thể mở trình duyệt TikTok: {e}"))
            finally:
                sys.stdout = old_stdout
                self.after(0, lambda: self._set_busy(False, "🟢 Sẵn sàng", "#10B981"))

        threading.Thread(target=task, daemon=True).start()

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

                    # TỰ ĐỘNG QUÉT VÀ NHẬN DẠNG TOÀN BỘ CIRCLE NGAY SAU KHI LOGIN!
                    self.write_log("🔄 Đang tự động nhận diện tất cả Circle bạn sở hữu / quản trị...")
                    try:
                        synced = identity_manager.sync_identities_from_ucircle(p)
                        self.write_log(f"🎉 Tự động nhận diện thành công {len(synced)} Kênh/Circle và lưu vào identities.json!")
                        self.after(0, self._reload_identity_checkboxes)
                        self.after(0, lambda: messagebox.showinfo(
                            "Đăng nhập & Nhận dạng thành công",
                            f"🎉 Đã lưu phiên đăng nhập và tự động nhận diện {len(synced)} Kênh/Circle của bạn!\n\n"
                            f"Danh sách đã được tự động nạp vào Tab 1 và Tab 2 mà bạn không cần phải nhập tay bất kỳ ID nào."
                        ))
                    except Exception as e_sync:
                        self.write_log(f"[!] Không thể tự động quét Circle: {e_sync}")
                        self.after(0, lambda: messagebox.showinfo(
                            "Đăng nhập thành công",
                            "Đã lưu phiên đăng nhập UCircle. Bạn có thể bấm nút '🔄 Quét từ UCircle' để nạp danh sách kênh."
                        ))
            except Exception as e:
                self.write_log(f"[ERROR] Lỗi khi login: {e}")
            finally:
                self.after(0, lambda: self._set_busy(False, "🟢 Sẵn sàng", "#10B981"))

        threading.Thread(target=run_login, daemon=True).start()

    def _start_scan(self):
        if self.is_running:
            return

        # Thu thập dữ liệu từ tất cả các ô input TikTok riêng biệt
        sources = []
        for r in self.source_rows:
            url = r["entry"].get().strip()
            target_circle = r["dropdown"].get().strip()
            if url:
                sources.append(f"{url} | {target_circle}")
                r["status_lbl"].configure(text="⚪ Chờ...", text_color="#94A3B8")

        if not sources:
            messagebox.showwarning("Lỗi", "Vui lòng nhập ít nhất một link kênh TikTok vào ô input!")
            return

        self._save_settings(verbose=False)
        config.STOP_REQUESTED = False
        config.HEADLESS = self.headless_var.get()

        is_keyword = self.mode_var.get() == "keyword"
        limit = self._int_or(self.limit_entry, 0)
        scrape_threads = int(self.scrape_threads_slider.get())
        min_views = self._int_or(self.min_views_entry, config.MIN_VIEWS)
        min_likes = self._int_or(self.min_likes_entry, config.MIN_LIKES)
        min_res = self._int_or(self.min_res_entry, config.MIN_RESOLUTION_HEIGHT)
        max_dur = self._int_or(self.max_duration_entry, getattr(config, "MAX_DURATION_SEC", 180))
        cookies_path = self.cookie_entry.get().strip() or None
        browser_cookie = self.browser_menu.get()
        if browser_cookie == "Không dùng":
            browser_cookie = None
        exclude_history = self.dedupe_history_var.get()

        self._set_busy(True, "🟡 Đang quét...", "#F59E0B")
        self.log_textbox.delete("1.0", tk.END)

        def on_source_start(idx, src, circle):
            def ui_update():
                if 1 <= idx <= len(self.source_rows):
                    self.source_rows[idx - 1]["status_lbl"].configure(text="🟡 Đang quét...", text_color="#F59E0B")
            self.after(0, ui_update)

        def on_source_done(idx, src, circle, stats):
            def ui_update():
                if 1 <= idx <= len(self.source_rows):
                    passed = stats.get("passed", 0)
                    found = stats.get("found", 0)
                    err = stats.get("error")
                    lbl = self.source_rows[idx - 1]["status_lbl"]
                    if err or found == 0:
                        lbl.configure(text="❌ 0 video", text_color="#EF4444")
                    elif passed == 0:
                        lbl.configure(text=f"⚠️ 0/{found} đạt", text_color="#F59E0B")
                    else:
                        lbl.configure(text=f"✅ {passed} video", text_color="#10B981")
            self.after(0, ui_update)

        def task():
            old_stdout = sys.stdout
            sys.stdout = TextRedirector(self.log_queue)
            try:
                if os.path.exists(config.EXCEL_PATH):
                    os.remove(config.EXCEL_PATH)
                    print("[!] Đã dọn dẹp file nháp cũ. Bắt đầu lưu danh sách mới tinh.")

                with sync_playwright() as p:
                    result = scraper.scrape_and_filter(
                        p, sources, is_keyword=is_keyword, limit=limit,
                        scrape_threads=scrape_threads, min_views=min_views,
                        min_likes=min_likes, min_resolution=min_res,
                        max_duration=max_dur,
                        cookies_path=cookies_path, browser_cookie=browser_cookie,
                        exclude_history=exclude_history,
                        on_source_start=on_source_start,
                        on_source_done=on_source_done,
                    )

                passed_total = result.get("passed", 0)
                scanned_total = result.get("scanned", 0)
                failed_sources = result.get("failed_sources", [])

                print(f"\n[+] Hoàn tất: Đã quét {scanned_total} video từ {len(sources)} nguồn. Đạt chuẩn {passed_total} video.")

                is_stopped = getattr(config, "STOP_REQUESTED", False)

                def notify_result():
                    if is_stopped:
                        self._set_busy(False, "🛑 Đã dừng quét", "#EF4444")
                        messagebox.showinfo(
                            "Đã dừng tiến trình",
                            f"🛑 Tiến trình quét video đã dừng theo yêu cầu của bạn!\n\n"
                            f"📊 Đã thu thập được {passed_total} video đạt chuẩn trước khi dừng."
                        )
                    elif failed_sources:
                        lines = []
                        for f in failed_sources:
                            lines.append(f"• [Hàng #{f['idx']}] {f['source']}\n  ➡️ UCircle: [{f['target_circle']}]\n  ⚠️ Lý do: {f['reason']}")
                        msg = (
                            f"⚠️ PHÁT HIỆN {len(failed_sources)} KÊNH KHÔNG CÓ VIDEO HỢP LỆ:\n\n"
                            + "\n\n".join(lines)
                            + "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            + "👉 ĐỂ XỬ LÝ:\n"
                            + "1. Xem chi tiết tab Console Log để biết rõ nguyên nhân.\n"
                            + "2. Bấm nút [🔄 Quét lại] ngay cạnh từng hàng bị lỗi để quét bổ sung mà không làm mất video các kênh khác!"
                        )
                        messagebox.showwarning("Cảnh báo: Kênh chưa có video", msg)
                    else:
                        messagebox.showinfo(
                            "Quét hoàn tất thành công",
                            f"🎉 Quét thành công toàn bộ {len(sources)} kênh TikTok!\n"
                            f"Tổng cộng {passed_total} video mới đã sẵn sàng để đăng lên UCircle."
                        )
                self.after(0, notify_result)
                self.after(0, self._sync_tab1_to_tab2_checkboxes)

            except Exception as e:
                print(f"[ERROR] Lỗi nghiêm trọng khi quét: {e}")
            finally:
                sys.stdout = old_stdout
                if not getattr(config, "STOP_REQUESTED", False):
                    self.after(0, lambda: self._set_busy(False, "🟢 Sẵn sàng", "#10B981"))

        threading.Thread(target=task, daemon=True).start()

    def _start_upload(self):
        """Bấm nút 'Đăng lên UCircle' -> mở form xác nhận file Excel -> bấm 'Bắt đầu đăng'."""
        if self.is_running:
            return

        if not os.path.exists(config.STORAGE_STATE_PATH):
            messagebox.showwarning("Lỗi", "Chưa có session UCircle. Vui lòng bấm 'Đăng Nhập UCircle (Lần đầu)' trước!")
            return

        selected_ids = self._get_selected_identity_ids()
        if not selected_ids:
            messagebox.showwarning("Lỗi", "Vui lòng chọn ít nhất một Kênh/Fanpage UCircle để đăng!")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Đăng lên UCircle từ Excel")
        dialog.geometry("700x260")
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dialog, text="Xác nhận file Excel và Kênh UCircle sẽ đăng:",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#10B981"
        ).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="w")

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
                update_detection()

        ctk.CTkButton(dialog, text="📂 Chọn file...", width=110, command=browse).grid(row=1, column=1, padx=(5, 15), pady=5)

        detection_label = ctk.CTkLabel(dialog, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#38BDF8")
        detection_label.grid(row=2, column=0, columnspan=2, padx=15, pady=(2, 5), sticky="w")

        def update_detection():
            ep = path_var.get().strip()
            if os.path.exists(ep):
                try:
                    df = pd.read_excel(ep)
                    if "target_circle" in df.columns and any(df["target_circle"].astype(str).str.strip()):
                        detection_label.configure(
                            text="🎯 ĐÃ BẬT: Chế độ 1 TikTok = 1 UCircle (Tự động đăng đúng Kênh theo từng video trong Excel)",
                            text_color="#38BDF8"
                        )
                        return
                except Exception:
                    pass
            mode_text = "Xoay vòng (Round-Robin)" if self.dist_mode_var.get() == "round_robin" else "Đăng Lên TẤT CẢ Các Kênh"
            detection_label.configure(
                text=f"⚙️ Chế độ dự phòng: {mode_text} (Kênh chọn: {len(selected_ids)} kênh)",
                text_color="#94A3B8"
            )

        update_detection()

        status_label = ctk.CTkLabel(dialog, text="", text_color="#EF4444")
        status_label.grid(row=3, column=0, columnspan=2, padx=15, pady=(0, 5), sticky="w")

        def confirm():
            excel_path = path_var.get().strip()
            if not excel_path or not os.path.exists(excel_path):
                status_label.configure(text="⚠️ File không tồn tại, hãy chọn lại.")
                return
            dialog.destroy()
            self._run_upload_from_excel(excel_path)

        ctk.CTkButton(
            dialog, text="🚀 Bắt đầu đăng", font=ctk.CTkFont(size=14, weight="bold"),
            height=40, fg_color="#10B981", hover_color="#059669", command=confirm
        ).grid(row=4, column=0, columnspan=2, padx=15, pady=(5, 15), sticky="ew")

    def _run_upload_from_excel(self, excel_path: str):
        self._save_settings(verbose=False)
        config.STOP_REQUESTED = False
        config.HEADLESS = self.headless_var.get()

        upload_threads = int(self.upload_threads_slider.get())
        selected_ids = self._get_selected_identity_ids()
        dist_mode = self.dist_mode_var.get()

        config.SELECTED_IDENTITIES = selected_ids
        config.DISTRIBUTION_MODE = dist_mode
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
            result = None
            try:
                result = uploader.run_uploads(
                    threads=upload_threads,
                    cookies_path=cookies_path,
                    browser_cookie=browser_cookie,
                    excel_path=excel_path,
                    identities=selected_ids,
                    distribution_mode=dist_mode,
                )
            except Exception as e:
                print(f"[ERROR] Lỗi nghiêm trọng khi đăng: {e}")
            finally:
                sys.stdout = old_stdout

                def show_completion():
                    if not result:
                        self._set_busy(False, "❌ Lỗi đăng", "#EF4444")
                        return

                    is_stopped = result.get("stopped") or getattr(config, "STOP_REQUESTED", False)
                    if is_stopped:
                        self._set_busy(False, "🛑 Đã dừng đăng", "#EF4444")
                        c_lines = []
                        for cid, st in result.get("circle_stats", {}).items():
                            c_name = st["name"]
                            c_succ = st["success"]
                            c_tot = st["total"]
                            c_rem = c_tot - c_succ - st.get("failed", 0)
                            c_lines.append(f"• 🏷️ [{c_name}]: Đã đăng {c_succ}/{c_tot} video (còn lại {c_rem})")

                        detail_str = "\n".join(c_lines) if c_lines else ""
                        msg = (
                            f"🛑 Tiến trình đăng đã DỪNG THEO YÊU CẦU CỦA BẠN!\n\n"
                            f"📊 Tổng kết trước khi dừng: {result['success']}/{result['total']} video đã đăng thành công.\n\n"
                            f"📋 Tình trạng từng Circle:\n{detail_str}\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"💡 Các video còn lại vẫn được lưu đầy đủ trong Excel.\n"
                            f"Lần sau bạn bấm 'Bắt đầu đăng', tool sẽ tiếp tục đăng nối tiếp!"
                        )
                        messagebox.showinfo("Đã dừng tiến trình", msg)
                    else:
                        self._set_busy(False, "🟢 Hoàn tất đăng!", "#10B981")
                        messagebox.showinfo(
                            "Đăng hoàn tất",
                            f"🎉 Đã hoàn thành tất cả các lượt đăng lên UCircle!\n\n"
                            f"📊 Kết quả: {result['success']}/{result['total']} lượt đăng thành công."
                        )

                self.after(0, show_completion)

        threading.Thread(target=task, daemon=True).start()


if __name__ == "__main__":
    print("[+] Đang mở giao diện Tool... Vui lòng đợi trong giây lát.")
    app = UCirclePipelineApp()
    print("[+] Giao diện đã mở thành công!")
    app.mainloop()
