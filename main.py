import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional, Tuple

import flet as ft


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

PIN_ID_RE = re.compile(r"/pin/(\d+)", re.IGNORECASE)
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def normalize_url(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    # remove fragments like trailing "#"
    s = s.split("#", 1)[0].strip()
    return s


def extract_pin_id(url: str) -> Optional[str]:
    m = PIN_ID_RE.search(url or "")
    if m:
        return m.group(1)
    # fallback: any long number in string (sometimes pasted without /pin/)
    m = re.search(r"(\d{10,})", url or "")
    if m:
        return m.group(1)
    return None


def _http_get_bytes(url: str, timeout: int = 20) -> Tuple[bytes, "urllib.response.addinfourl"]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Connection": "close",
        },
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.read(), resp


def fetch_pin_info(pin_id: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Uses Pinterest public pidgets API:
    https://api.pinterest.com/v3/pidgets/pins/info/?pin_ids=<ID>
    """
    api = f"https://api.pinterest.com/v3/pidgets/pins/info/?pin_ids={pin_id}"
    try:
        data, _ = _http_get_bytes(api, timeout=20)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return None, f"HTTP {e.code} {body[:200]}".strip()
    except Exception as e:
        return None, f"request error: {e}"

    try:
        j = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        return None, "bad JSON from API"

    if j.get("status") != "success":
        return None, f"API status={j.get('status')} message={j.get('message')}"

    payload = j.get("data")
    if not isinstance(payload, list) or not payload:
        return None, "API returned empty data"

    item = payload[0]
    if isinstance(item, dict) and item.get("error"):
        return None, str(item.get("error"))
    if not isinstance(item, dict):
        return None, "unexpected API response"

    return item, None


def pick_best_image_url(pin_item: dict) -> Optional[str]:
    images = pin_item.get("images")
    best_url: Optional[str] = None
    best_w = -1

    if isinstance(images, dict):
        for v in images.values():
            if not isinstance(v, dict):
                continue
            u = v.get("url")
            w = int(v.get("width") or 0)
            if u and w > best_w:
                best_url = u
                best_w = w

    # extra fallbacks (rare)
    if not best_url:
        for k in ("image_large_url", "image_url", "image_small_url"):
            u = pin_item.get(k)
            if isinstance(u, str) and u.startswith("http"):
                return u

    return best_url


class _OGImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.og_image: Optional[str] = None
        self.og_image_secure: Optional[str] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if (tag or "").lower() != "meta":
            return
        d = {str(k).lower(): v for k, v in (attrs or []) if k}
        prop = (d.get("property") or d.get("name") or "").lower()
        content = d.get("content")
        if not isinstance(content, str) or not content.startswith("http"):
            return
        if prop == "og:image:secure_url":
            self.og_image_secure = content
        elif prop in ("og:image", "og:image:url"):
            if not self.og_image:
                self.og_image = content


def fetch_og_image(pin_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Fallback: fetch pin page and extract og:image."""
    try:
        data, resp = _http_get_bytes(pin_url, timeout=25)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"request error: {e}"

    # If Pinterest redirects, keep final URL for debugging
    _ = getattr(resp, "geturl", lambda: pin_url)()

    try:
        html = data.decode("utf-8", "replace")
    except Exception:
        html = ""

    parser = _OGImageParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    img = parser.og_image_secure or parser.og_image
    if img:
        return img, None
    return None, "og:image not found"


def resolve_pin_image_url(pin_url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Returns (image_url, pin_id, error).
    Tries Pinterest pidgets API first, then falls back to HTML og:image.
    """
    url = normalize_url(pin_url)
    pid = extract_pin_id(url)
    if not pid:
        return None, None, "cannot extract pin id"

    info, err = fetch_pin_info(pid)
    if info and not err:
        img_url = pick_best_image_url(info)
        if img_url:
            return img_url, pid, None

    # fallback to HTML
    img_url, err2 = fetch_og_image(url)
    if img_url:
        return img_url, pid, None
    return None, pid, err or err2 or "unknown error"


def _guess_ext_from_url(url: str) -> str:
    try:
        p = urllib.parse.urlparse(url).path
        ext = Path(p).suffix.lower()
    except Exception:
        ext = ""
    if ext in IMG_EXTS:
        return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def _to_pinimg_originals(url: str) -> str:
    """
    Many Pinterest images have size URLs like:
    https://i.pinimg.com/564x/...jpg
    This tries to upgrade them to:
    https://i.pinimg.com/originals/...jpg
    """
    try:
        p = urllib.parse.urlparse(url)
        host = (p.netloc or "").lower()
        if "pinimg.com" not in host:
            return url
        parts = p.path.split("/")
        # ['', '564x', 'aa', 'bb', ...]
        if len(parts) > 2 and parts[1].endswith("x") and parts[1][:-1].isdigit():
            parts[1] = "originals"
            new_path = "/".join(parts)
            return urllib.parse.urlunparse(p._replace(path=new_path))
    except Exception:
        pass
    return url


def _safe_filename(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "pinterest"
    # keep simple ASCII-ish names
    s = re.sub(r"[^\w\-. ]+", "_", s, flags=re.UNICODE).strip()
    s = re.sub(r"\s+", " ", s).strip()
    return s[:120] if len(s) > 120 else s


def _unique_path(base_dir: Path, filename: str) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    p = base_dir / filename
    if not p.exists():
        return p
    stem = p.stem
    suffix = p.suffix
    for i in range(1, 10_000):
        cand = base_dir / f"{stem}_{i}{suffix}"
        if not cand.exists():
            return cand
    return base_dir / f"{stem}_{int(time.time())}{suffix}"


def download_image(url: str, out_dir: Path, filename_base: str, stop_event: threading.Event) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    try_urls = []
    orig = _to_pinimg_originals(url)
    if orig != url:
        try_urls.append(orig)
    try_urls.append(url)

    last_err: Optional[Exception] = None
    for u in try_urls:
        # "originals" can be slower / sometimes blocked; fail fast and fallback.
        base_timeout = 15 if (orig != url and u == orig) else 60
        max_tries = 3

        for attempt in range(1, max_tries + 1):
            if stop_event.is_set():
                raise RuntimeError("stopped")

            ext = _guess_ext_from_url(u)
            dest = _unique_path(out_dir, f"{_safe_filename(filename_base)}{ext}")
            tmp = dest.with_suffix(dest.suffix + ".part")

            try:
                req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "image/*,*/*;q=0.8"})
                timeout = base_timeout
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    with open(tmp, "wb") as f:
                        while True:
                            if stop_event.is_set():
                                raise RuntimeError("stopped")
                            chunk = resp.read(256 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)

                tmp.replace(dest)
                return dest

            except urllib.error.HTTPError as e:
                last_err = e
                # originals may be absent / blocked; try the size URL
                if orig != url and u == orig:
                    break
                raise

            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                # originals may be flaky; try size URL
                if orig != url and u == orig:
                    break
                if attempt < max_tries:
                    time.sleep(0.6 * attempt)
                    continue
                raise

            except Exception as e:
                last_err = e
                # originals weird failure -> fallback to size URL
                if orig != url and u == orig:
                    break
                if attempt < max_tries:
                    time.sleep(0.6 * attempt)
                    continue
                raise

            finally:
                # cleanup partial file on any error
                if tmp.exists() and not dest.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass

    raise RuntimeError(f"download failed: {last_err}")


def main(page: ft.Page) -> None:
    page.title = "Pinterest Saver"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 920
    page.window_height = 720
    page.padding = 12
    # Важно: не включаем scroll на всей странице, иначе лог будет "раздвигать" интерфейс,
    # вместо того чтобы прокручиваться внутри ListView.

    stop_event = threading.Event()

    default_out = Path.cwd() / "downloads"
    default_out.mkdir(parents=True, exist_ok=True)
    out_dir = {"path": default_out}

    # UI elements
    title = ft.Text("Pinterest Saver", size=20, weight=ft.FontWeight.BOLD)
    subtitle = ft.Text(
        "Вставь ссылки на пины (по одной в строке). Программа скачает фото по каждой ссылке.",
        size=12,
        color=ft.Colors.GREY_400,
    )

    out_text = ft.Text(str(out_dir["path"]), selectable=True)
    pick_btn = ft.OutlinedButton("Папка…")

    links = ft.TextField(
        label="Pinterest ссылки",
        hint_text="https://www.pinterest.com/pin/603763893837589979/",
        multiline=True,
        min_lines=10,
        max_lines=16,
        expand=True,
        autofocus=True,
    )

    progress = ft.ProgressBar(value=0)
    stats = ft.Text("Готово: 0 | Ошибок: 0", size=12, color=ft.Colors.GREY_400)

    log_view = ft.ListView(expand=True, spacing=2, auto_scroll=True)

    start_btn = ft.FilledButton("Скачать", icon=ft.Icons.DOWNLOAD)
    stop_btn = ft.OutlinedButton("Стоп", icon=ft.Icons.STOP, disabled=True)
    clear_btn = ft.TextButton("Очистить", icon=ft.Icons.DELETE_OUTLINE)

    def ui_log(msg: str) -> None:
        log_view.controls.append(ft.Text(msg, size=12))
        # keep UI snappy
        if len(log_view.controls) > 500:
            log_view.controls = log_view.controls[-500:]
        page.update()

    def set_running(running: bool) -> None:
        start_btn.disabled = running
        stop_btn.disabled = not running
        pick_btn.disabled = running
        clear_btn.disabled = running
        links.disabled = running
        page.update()

    def on_pick_result(e: ft.FilePickerResultEvent) -> None:
        if e.path:
            out_dir["path"] = Path(e.path)
            out_text.value = str(out_dir["path"])
            ui_log(f"📁 Папка сохранения: {out_dir['path']}")

    picker = ft.FilePicker(on_result=on_pick_result)
    page.overlay.append(picker)

    def on_pick_folder(_e) -> None:
        picker.get_directory_path(dialog_title="Куда сохранять картинки?")

    pick_btn.on_click = on_pick_folder

    def on_clear(_e) -> None:
        links.value = ""
        log_view.controls.clear()
        progress.value = 0
        stats.value = "Готово: 0 | Ошибок: 0"
        page.update()

    clear_btn.on_click = on_clear

    def on_stop(_e) -> None:
        stop_event.set()
        ui_log("⛔️ Остановлено пользователем. Дожидаюсь завершения текущей загрузки…")

    stop_btn.on_click = on_stop

    def worker(urls: list[str]) -> None:
        ok = 0
        bad = 0
        total = len(urls)

        for i, raw in enumerate(urls, start=1):
            if stop_event.is_set():
                break

            progress.value = (i - 1) / total if total else 0
            stats.value = f"Готово: {ok} | Ошибок: {bad} | {i}/{total}"
            page.update()

            url = normalize_url(raw)
            img_url, pin_id, err = resolve_pin_image_url(url)
            if err or not img_url or not pin_id:
                bad += 1
                ui_log(f"[{i}/{total}] ❌ {pin_id or 'PIN'}: {err or 'unknown error'} ({url})")
                continue

            ui_log(f"[{i}/{total}] 📌 Pin {pin_id} — скачиваю…")

            try:
                dest = download_image(img_url, out_dir["path"], f"pin_{pin_id}", stop_event)
                ok += 1
                ui_log(f"[{i}/{total}] ✅ Скачано: {dest.name}")
            except Exception as e:
                bad += 1
                ui_log(f"[{i}/{total}] ❌ Ошибка скачивания pin {pin_id}: {e}")

            # be nice to API
            time.sleep(0.15)

        progress.value = 1 if total and not stop_event.is_set() else progress.value
        stats.value = f"Готово: {ok} | Ошибок: {bad}"
        set_running(False)
        if stop_event.is_set():
            ui_log("⛔️ Готово (остановлено).")
        else:
            ui_log("✅ Готово.")

    def on_start(_e) -> None:
        raw_lines = (links.value or "").splitlines()
        urls = [normalize_url(x) for x in raw_lines]
        urls = [u for u in urls if u]

        # dedupe while keeping order (by pin id if possible)
        seen = set()
        uniq: list[str] = []
        for u in urls:
            key = extract_pin_id(u) or u
            if key in seen:
                continue
            seen.add(key)
            uniq.append(u)

        if not uniq:
            ui_log("⚠️ Вставь хотя бы одну ссылку.")
            return

        stop_event.clear()
        log_view.controls.clear()
        progress.value = 0
        stats.value = f"Готово: 0 | Ошибок: 0 | 0/{len(uniq)}"
        set_running(True)
        ui_log(f"▶️ Старт: {len(uniq)} ссылок")
        ui_log(f"📁 Папка: {out_dir['path']}")
        page.run_thread(worker, uniq)

    start_btn.on_click = on_start

    page.add(
        ft.Column(
            [
                title,
                subtitle,
                ft.Divider(height=16),
                ft.Row(
                    [
                        ft.Text("Папка:", size=12, color=ft.Colors.GREY_400),
                        out_text,
                        ft.Container(expand=True),
                        pick_btn,
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
                ft.Divider(height=8),
                ft.Row([start_btn, stop_btn, clear_btn], spacing=12),
                ft.Container(height=6),
                progress,
                stats,
                ft.Divider(height=12),
                ft.Row(
                    [
                        ft.Container(links, expand=True),
                        ft.Container(
                            ft.Column(
                                [
                                    ft.Text("Лог:", size=12, color=ft.Colors.GREY_400),
                                    ft.Container(log_view, expand=True, border=ft.border.all(1, ft.Colors.GREY_800), padding=8),
                                ],
                                expand=True,
                            ),
                            expand=True,
                        ),
                    ],
                    expand=True,
                ),
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)

