# -*- coding: utf-8 -*-
import os
import json
import re
from typing import List, Dict

import config

_UUID_PATTERN = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

DEFAULT_IDENTITIES: List[Dict[str, str]] = [
    {"name": "Tôi (Trang cá nhân)", "id": "me"},
    {"name": "Game Hay", "id": "6f41a4fc-4573-47bf-a27f-5420fe28f1de"},
    {"name": "xe độ chiến", "id": "7b944633-043c-445b-b516-aeeddb7bb7f9"},
    {"name": "Gái Xinh", "id": "dea448a6-b8e5-40e0-9cd7-68ea12abaac5"},
    {"name": "xe hay", "id": "f798d40c-de5f-4ba7-abfa-870afe234863"},
]


def _get_file_path() -> str:
    return getattr(config, "IDENTITIES_PATH", os.path.join(config.BASE_DIR, "data", "identities.json"))


def load_identities() -> List[Dict[str, str]]:
    """Tải danh sách Fanpage/Kênh UCircle từ file JSON.
    Nếu chưa có file, khởi tạo danh sách mặc định."""
    path = _get_file_path()
    if not os.path.exists(path):
        save_identities(DEFAULT_IDENTITIES)
        return list(DEFAULT_IDENTITIES)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                return data
    except Exception as e:
        print(f"[!] Lỗi đọc {path}: {e}")

    return list(DEFAULT_IDENTITIES)


def save_identities(identities: List[Dict[str, str]]) -> None:
    """Lưu danh sách Fanpage/Kênh UCircle vào file JSON."""
    path = _get_file_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(identities, f, ensure_ascii=False, indent=2)


def extract_identity_id(raw_input: str) -> str:
    """Bóc tách ID từ UUID thẳng, link (vd: https://ucircle.net/app/c/uuid), hoặc 'me'."""
    raw_input = (raw_input or "").strip()
    if raw_input.lower() in ("me", "tôi", "toi"):
        return "me"
    match = _UUID_PATTERN.search(raw_input)
    if match:
        return match.group(0)
    return raw_input


def get_identity_name(raw_id_or_name: str) -> str:
    """Trả về tên hiển thị dễ đọc của Circle/Kênh dựa trên ID, UUID hoặc Tên."""
    if not raw_id_or_name:
        return "Cá nhân (Tôi)"
    clean = str(raw_id_or_name).strip()
    if clean.lower() in ("me", "tôi", "toi"):
        return "Tôi (Trang cá nhân)"
    identities = load_identities()
    for item in identities:
        if item["id"].lower() == clean.lower() or item["name"].lower() == clean.lower():
            return item["name"]
    return clean


def add_identity(name: str, raw_id_or_url: str) -> Dict[str, str]:
    """Thêm một Kênh/Fanpage mới vào danh bạ."""
    name = (name or "").strip()
    extracted_id = extract_identity_id(raw_id_or_url)
    if not extracted_id:
        raise ValueError("ID hoặc Link UCircle không hợp lệ (cần là 'me' hoặc chứa mã UUID).")

    if not name:
        name = "Kênh " + (extracted_id[:8] if extracted_id != "me" else "Cá nhân")

    identities = load_identities()
    # Kiểm tra nếu đã tồn tại thì cập nhật tên
    for item in identities:
        if item["id"].lower() == extracted_id.lower():
            item["name"] = name
            save_identities(identities)
            return item

    new_item = {"name": name, "id": extracted_id}
    identities.append(new_item)
    save_identities(identities)
    return new_item


def remove_identity(identity_id: str) -> bool:
    """Xoá một Kênh/Fanpage khỏi danh bạ."""
    identities = load_identities()
    new_list = [item for item in identities if item["id"] != identity_id]
    if len(new_list) != len(identities):
        save_identities(new_list)
        return True
    return False


def resolve_identity_info(identifier: str) -> Dict[str, str]:
    """Tìm thông tin kênh từ tên (vd: 'xe độ chiến', 'Gái Xinh'), ID/UUID, hoặc 'me'."""
    identifier = (identifier or "").strip()
    if not identifier:
        return {"name": "Tôi (Trang cá nhân)", "id": "me"}

    identities = load_identities()

    # 1. Khớp chính xác ID hoặc Tên
    for item in identities:
        if item["id"].lower() == identifier.lower() or item["name"].lower() == identifier.lower():
            return item

    # 2. Khớp một phần tên
    for item in identities:
        if identifier.lower() in item["name"].lower() or item["name"].lower() in identifier.lower():
            return item

    # 3. Tự bóc tách ID nếu là link hoặc UUID
    extracted_id = extract_identity_id(identifier)
    return {"name": identifier, "id": extracted_id}


def sync_identities_from_ucircle(playwright, on_log=None) -> List[Dict[str, str]]:
    """Tự động mở trình duyệt dựa trên session đã login, điều hướng vào mục Circle -> Sở hữu và Quản trị
    để trích xuất toàn bộ danh sách Circle người dùng sở hữu/quản lý và lưu vào identities.json."""
    if not os.path.exists(config.STORAGE_STATE_PATH):
        raise FileNotFoundError("Chưa có phiên đăng nhập UCircle. Vui lòng bấm 'Đăng Nhập UCircle' trước.")

    def log(msg):
        print(msg)
        if on_log:
            on_log(msg)

    log("[*] Khởi động trình duyệt để quét danh sách Circle từ tài khoản UCircle...")
    browser = playwright.chromium.launch(headless=True)
    try:
        context = browser.new_context(viewport={"width": 1280, "height": 800}, storage_state=config.STORAGE_STATE_PATH)
        page = context.new_page()
        page.goto("https://ucircle.net/app", timeout=30_000)
        page.wait_for_timeout(2500)

        # 1. Bấm vào nút "Circle" trên thanh menu
        log("[*] Đang mở mục Circle...")
        circle_btn = page.locator('button[title="Circle"], button:has-text("Circle")')
        if circle_btn.count() == 0:
            raise RuntimeError("Không tìm thấy nút 'Circle' trên giao diện UCircle. Hãy kiểm tra lại phiên đăng nhập.")
        circle_btn.first.click()
        page.wait_for_timeout(2000)

        discovered = []
        seen_ids = set()

        # Luôn có "Tôi (Trang cá nhân)"
        discovered.append({"name": "Tôi (Trang cá nhân)", "id": "me"})
        seen_ids.add("me")

        def collect_from_tab(tab_name: str, label_type: str):
            btn = page.locator(f'button:has-text("{tab_name}")')
            if btn.count() == 0:
                return
            log(f"[*] Đang quét danh sách Circle [{tab_name}]...")
            btn.first.click()
            page.wait_for_timeout(1500)

            # Cuộn lặp từng đoạn ngắn để thu thập toàn bộ card ngay cả khi UCircle dùng virtualized list
            for _ in range(6):
                cards = page.locator('li[data-circle-card="true"], [data-circle-id]').all()
                new_in_step = 0
                for c in cards:
                    try:
                        cid = c.get_attribute("data-circle-id")
                        cname = c.get_attribute("aria-label")
                        if not cname:
                            h3 = c.locator("h3")
                            if h3.count() > 0:
                                cname = h3.first.inner_text().strip()
                        if cid and cname and cid not in seen_ids:
                            seen_ids.add(cid)
                            discovered.append({"name": cname, "id": cid})
                            new_in_step += 1
                            log(f"   ➕ Tìm thấy Circle {label_type}: {cname} (ID: {cid})")
                    except Exception:
                        continue
                if new_in_step == 0:
                    break
                page.mouse.wheel(0, 600)
                page.wait_for_timeout(400)

        # 2. Quét tab "Sở hữu"
        collect_from_tab("Sở hữu", "sở hữu")

        # 3. Quét tab "Quản trị"
        collect_from_tab("Quản trị", "quản trị")

        log(f"[+] Tổng cộng tìm thấy {len(discovered)} Kênh/Circle hợp lệ!")
        save_identities(discovered)
        return discovered
    finally:
        try:
            browser.close()
        except Exception:
            pass
