"""
Core download engine: fetch album pages, resolve CDN URLs, and stream files to disk.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from math import floor
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed
from tqdm import tqdm

from .tracking import DownloadTracker

BUNKR_VS_API_URL = "https://bunkr.cr/api/vs"
BUNKR_SIGN_API_URL = "https://glb-apisign.cdn.cr/sign"
SECRET_KEY_BASE = "SECRET_KEY_"
MAX_RETRIES = 10

# Serialises the existence-check + filename assignment so concurrent workers
# cannot both observe the same path as absent and write to it simultaneously.
_path_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class DownloadResult:
    success: bool
    folder_name: str | None = None
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def download_all(
    urls: list[str],
    extensions: str | None = None,
    output_dir: str = "downloads",
    export_urls: bool = False,
    date_before: datetime | None = None,
    date_after: datetime | None = None,
    workers: int = 4,
) -> list[DownloadResult]:
    """Download multiple album URLs, sharing one HTTP session."""
    session = create_session(workers=workers)
    results = []
    for url in urls:
        print(f"\t[-] Processing {url!r}...")
        try:
            folder_path = _get_items_list(
                session, url, extensions, export_urls, output_dir,
                date_before=date_before, date_after=date_after, workers=workers,
            )
            folder_name = os.path.basename(folder_path) if folder_path else None
            results.append(DownloadResult(success=True, folder_name=folder_name))
        except Exception as exc:
            results.append(DownloadResult(success=False, errors=[str(exc)]))
    return results


def download_album(
    url: str,
    extensions: str | None = None,
    output_dir: str = "downloads",
    export_urls: bool = False,
    date_before: datetime | None = None,
    date_after: datetime | None = None,
    workers: int = 4,
) -> DownloadResult:
    """Download all files from a Bunkr or Cyberdrop album URL."""
    return download_all(
        [url],
        extensions=extensions,
        output_dir=output_dir,
        export_urls=export_urls,
        date_before=date_before,
        date_after=date_after,
        workers=workers,
    )[0]


# ---------------------------------------------------------------------------
# Filename sanitisation (used by parsers and by bookmarks_cmd)
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Remove characters illegal in filenames."""
    if name is None:
        return ""
    return re.sub(r'[<>:"/\\|?*\']|[\0-\x1f]', "-", name).strip()


# ---------------------------------------------------------------------------
# Album page fetching and item dispatch
# ---------------------------------------------------------------------------

def _parse_bunkr_album_page(
    soup: BeautifulSoup,
    url: str,
    date_before: datetime | None = None,
    date_after: datetime | None = None,
) -> tuple[list[dict], str, bool]:
    """Parse a Bunkr album or file page. Returns (items, album_name, is_direct_link)."""
    direct_link = (
        soup.find("span", {"class": "ic-videos"}) is not None
        or soup.find("div", {"class": "lightgallery"}) is not None
    )

    if direct_link:
        album_name_tag = soup.find("h1", {"class": "text-[20px]"}) or soup.find("h1", {"class": "truncate"})
        album_name = sanitize_filename(album_name_tag.text) if album_name_tag else ""
        items = []
        for a in soup.find_all("a", href=re.compile(r"/f/")):
            href = a.get("href")
            full_url = urljoin(url, href)
            title = a.get("title") or (a.text.strip() if a.text else None)
            items.append({"url": full_url, "size": -1, "name": sanitize_filename(title) if title else None})
        return items, album_name, True

    items = []
    for the_item in soup.find_all("div", {"class": "theItem"}):
        if date_before is not None or date_after is not None:
            date_span = the_item.find("span", {"class": "ic-clock"})
            if not _is_date_in_range(date_span.text, date_before, date_after):
                continue
        box = the_item.find("a", {"class": "after:absolute"})
        items.append({"url": box["href"], "size": -1, "name": the_item.find("p").text})
    album_name = sanitize_filename(soup.find("h1", {"class": "truncate"}).text)
    return items, album_name, False


def _parse_cyberdrop_album_page(soup: BeautifulSoup, url: str) -> tuple[list[dict], str]:
    """Parse a Cyberdrop album page. Returns (items, album_name)."""
    items = [
        {"url": f"https://cyberdrop.me{item_dom['href']}", "size": -1}
        for item_dom in soup.find_all("a", {"class": "image"})
    ]
    album_name = sanitize_filename(soup.find("h1", {"id": "title"}).text)
    return items, album_name


def _get_items_list(
    session: requests.Session,
    url: str,
    extensions: str | None,
    only_export: bool,
    custom_path: str | None = None,
    date_before: datetime | None = None,
    date_after: datetime | None = None,
    tracker: DownloadTracker | None = None,
    workers: int = 4,
) -> str | None:
    extensions_list = extensions.split(",") if extensions else []
    download_path: str | None = None
    is_bunkr: bool = False
    current_url = url
    pending: list[dict] = []

    while True:
        r = session.get(current_url)
        if r.status_code != 200:
            raise Exception(f"HTTP error {r.status_code} fetching {current_url}")

        soup = BeautifulSoup(r.content, "html.parser")
        is_bunkr = "| Bunkr" in soup.find("title").text

        if is_bunkr:
            items, album_name, direct_link = _parse_bunkr_album_page(soup, current_url, date_before, date_after)
            if direct_link and not items:
                single = _get_real_download_url(session, current_url, True)
                if single:
                    items.append(single)
        else:
            items, album_name = _parse_cyberdrop_album_page(soup, current_url)
            direct_link = False

        if download_path is None:
            download_path = _prepare_download_path(custom_path, album_name)
        if tracker is None:
            tracker = DownloadTracker(download_path)

        for item in items:
            if not direct_link:
                item = _get_real_download_url(session, item["url"], is_bunkr, item["name"], item["url"])
                if item is None:
                    print("\t\t[-] Unable to find a download link")
                    continue

            tracking_value = _get_tracking_value(item)
            extension = _url_data(item["url"])["extension"]
            if (extension in extensions_list or not extensions_list) and not tracker.is_downloaded(tracking_value):
                if only_export:
                    _write_url_to_list(item["url"], download_path)
                else:
                    pending.append(item)

        pagination = soup.find("nav", {"class": "pagination"})
        if pagination is None:
            break

        current_page = int(pagination.find("span", {"class": "active"}).text)
        page_links = [a for a in pagination.find_all("a") if a.text.strip().isdigit()]
        last_page = int(page_links[-1].text) if page_links else current_page

        if current_page >= last_page:
            break

        print(f"[!] Downloading page ({current_page + 1}/{last_page})")
        if re.search(r"([?&])page=\d+", current_url):
            current_url = re.sub(r"([?&])page=\d+", rf"\1page={current_page + 1}", current_url)
        else:
            sep = "&" if "?" in current_url else "?"
            current_url = f"{current_url}{sep}page={current_page + 1}"

    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(
                    _download_file,
                    session, item["url"], download_path, is_bunkr,
                    item["name"], _get_tracking_value(item), tracker,
                ): item
                for item in pending
            }
            for f in as_completed(futs):
                try:
                    f.result()
                except Exception as exc:
                    print(f"\t[-] Download error: {exc}")

    if only_export:
        print(f"\t[+] URL list exported to {os.path.join(download_path, 'url_list.txt')}")
    else:
        print("\t[+] Download completed")

    return download_path


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------

def _get_real_download_url(
    session: requests.Session,
    url: str,
    is_bunkr: bool = True,
    item_name: str | None = None,
    download_key: str | None = None,
) -> dict | None:
    if is_bunkr:
        url = url if url.startswith("https") else f"https://bunkr.cr{url}"
    else:
        url = url.replace("/f/", "/api/f/")

    r = session.get(url)
    if r.status_code != 200:
        print(f"\t[-] HTTP error {r.status_code} getting download URL for {url}")
        return None

    if is_bunkr:
        original_filename = extract_bunkr_filename(r.text)
        cdn_url = extract_bunkr_cdn_url(r.text)

        if cdn_url:
            sign_url = _get_signed_url(session, cdn_url, r.url)
            if sign_url:
                name = item_name or sanitize_filename(original_filename or _url_data(cdn_url)["file_name"])
                return {"url": sign_url, "size": -1, "name": name, "download_key": download_key or url}

        if original_filename:
            for path in (
                f"storage/media/{original_filename.replace(' ', '-')}",
                f"storage/media/{original_filename}",
            ):
                sign_url = _get_signed_url(session, path, r.url)
                if sign_url:
                    return {"url": sign_url, "size": -1, "name": item_name or sanitize_filename(original_filename), "download_key": download_key or url}

        # Legacy fallback: encrypted URL via /api/vs
        m = re.search(r'href="/f/([A-Za-z0-9_-]+)"', r.text)
        if m:
            enc_data = _get_encryption_data(session, m.group(1))
            if enc_data is not None:
                return {"url": _decrypt_url(enc_data), "size": -1, "name": item_name}

        print(f"\t\t[-] Unable to extract file info from {r.url}")
        return None
    else:
        data = json.loads(r.content)
        return {"url": data["url"], "size": -1, "name": data["name"], "download_key": download_key or url}


def _get_signed_url(session: requests.Session, file_path: str, page_url: str) -> str | None:
    """Get a time-limited signed CDN URL from the Bunkr sign API."""
    try:
        if re.match(r"^https?://", file_path):
            parsed = urlparse(file_path)
            base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            signed_path = unquote(parsed.path)
        else:
            signed_path = f"/{file_path.lstrip('/')}"
            base_url = f"https://glb-cdn.cdn.cr{signed_path}"

        r = session.get(
            BUNKR_SIGN_API_URL,
            params={"path": signed_path},
            headers={"Origin": "https://bunkr.cr", "Referer": page_url},
            timeout=10,
        )
        if r.status_code != 200:
            print(f"\t\t[-] HTTP {r.status_code} from sign API")
            return None

        data = json.loads(r.content)
        ex, token = data.get("ex"), data.get("token")
        if ex and token:
            return f"{base_url}?ex={ex}&token={token}"

        print(f"\t\t[-] Unexpected sign API response: {r.text[:200]}")
        return None
    except Exception as exc:
        print(f"\t\t[-] Exception in sign API call: {exc}")
        return None


def _get_encryption_data(session: requests.Session, slug: str) -> dict | None:
    """Fetch legacy encryption data for a file slug via /api/vs."""
    try:
        r = session.post(
            BUNKR_VS_API_URL,
            json={"slug": slug},
            headers={
                "Origin": "https://bunkr.cr",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://bunkr.cr/",
            },
            timeout=10,
        )
    except Exception as exc:
        print(f"\t\t[-] Exception calling {BUNKR_VS_API_URL}: {exc}")
        return None

    if r.status_code != 200:
        print(f"\t\t[-] HTTP {r.status_code} from encryption API")
        return None

    try:
        return json.loads(r.content)
    except Exception as exc:
        print(f"\t\t[-] Failed to parse encryption response: {exc}")
        return None


def _decrypt_url(encryption_data: dict) -> str:
    secret_key = f"{SECRET_KEY_BASE}{floor(encryption_data['timestamp'] / 3600)}"
    encrypted = list(b64decode(encryption_data["url"]))
    key_bytes = list(secret_key.encode("utf-8"))
    return "".join(chr(encrypted[i] ^ key_bytes[i % len(key_bytes)]) for i in range(len(encrypted)))


# ---------------------------------------------------------------------------
# Filename / CDN URL extraction (also used by tests)
# ---------------------------------------------------------------------------

def extract_bunkr_filename(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    the_item = soup.find("div", class_="theItem")
    if the_item:
        candidates.append(the_item.get("title"))
        p_name = the_item.find("p", class_="theName")
        if p_name:
            candidates.append(p_name.get_text(strip=True))
        hidden_p = the_item.find("p", style=re.compile(r"display:\s*none"))
        if hidden_p:
            candidates.append(hidden_p.get_text(strip=True))
        thumb = the_item.find("img", class_="grid-images_box-img")
        if thumb and thumb.get("src"):
            m = re.search(r"/thumbs/([^\"/ ]+)\.png", thumb["src"])
            if m:
                candidates.append(f"{m.group(1)}.mp4")

    h1 = soup.find("h1")
    if h1:
        candidates.append(h1.get_text(strip=True))

    og = soup.find("meta", property="og:title")
    if og:
        candidates.append(og.get("content"))

    title = soup.find("title")
    if title:
        candidates.append(re.sub(r"\s*\|\s*Bunkr\s*$", "", title.get_text(strip=True)))

    for c in candidates:
        name = _clean_filename(c)
        if name:
            return name
    return None


def extract_bunkr_cdn_url(html: str) -> str | None:
    m = re.search(r'var\s+jsCDN\s*=\s*"([^"]+)"', html)
    if m:
        return _decode_js_string(m.group(1))
    m = re.search(r"https://[^\"']+\.cdn\.cr/storage/media/[^\"']+", html)
    if m:
        return _decode_js_string(m.group(0))
    return None


def _clean_filename(value: str | None) -> str | None:
    if not value:
        return None
    filename = unquote(value).strip()
    if not filename or re.fullmatch(r"v?\d+(?:\.\d+){1,3}", filename, flags=re.IGNORECASE):
        return None
    if filename.lower() in ("bunkr", "version"):
        return None
    if not os.path.splitext(filename)[1]:
        return None
    return filename


def _decode_js_string(value: str) -> str:
    return json.loads(f'"{value}"')


# ---------------------------------------------------------------------------
# File download
# ---------------------------------------------------------------------------

def _reserve_final_path(download_path: str, file_name: str) -> tuple[str, str]:
    """Return (file_name, final_path), renaming with a timestamp if the path is taken."""
    with _path_lock:
        final_path = os.path.join(download_path, file_name)
        if os.path.exists(final_path):
            file_name = f"{int(time.time())}_{file_name}"
            final_path = os.path.join(download_path, file_name)
    return file_name, final_path


@retry(
    retry=retry_if_exception_type(requests.exceptions.ConnectionError),
    wait=wait_fixed(2),
    stop=stop_after_attempt(MAX_RETRIES),
)
def _download_file(
    session: requests.Session,
    item_url: str,
    download_path: str,
    is_bunkr: bool = False,
    file_name: str | None = None,
    download_key: str | None = None,
    tracker: DownloadTracker | None = None,
) -> None:
    file_name = file_name or _url_data(item_url)["file_name"]
    file_name, final_path = _reserve_final_path(download_path, file_name)

    with session.get(item_url, stream=True, timeout=(10, 60)) as r:
        print(f"\t[+] Downloading {item_url} ({file_name})")
        if r.status_code != 200:
            print(f"\t\t[-] Error {r.status_code} downloading {file_name!r}")
            return
        if r.url == "https://bnkr.b-cdn.net/maintenance.mp4":
            print(f"\t\t[-] Server is down for maintenance")
            return

        file_size = int(r.headers.get("content-length", -1))
        with open(final_path, "wb") as f:
            with tqdm(total=file_size, unit="iB", unit_scale=True, desc=file_name, leave=False) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

    if is_bunkr and file_size > -1:
        if os.stat(final_path).st_size != file_size:
            print(f"\t[-] {file_name}: size mismatch — file may be incomplete")
            return

    key = download_key or item_url
    if tracker is not None:
        tracker.mark_done(key)
    else:
        _mark_downloaded(key, download_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_session(workers: int = 4) -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=workers, pool_maxsize=workers)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
            ),
            "Referer": "https://bunkr.cr/",
        }
    )
    return s


def _url_data(url: str) -> dict:
    parsed = urlparse(url)
    return {
        "file_name": os.path.basename(parsed.path),
        "extension": os.path.splitext(parsed.path)[1],
        "hostname": parsed.hostname,
    }


def _get_tracking_value(item: dict) -> str:
    return item.get("download_key", item["url"])


# kept as a public alias so tests can import it by the old name
get_download_tracking_value = _get_tracking_value


def _prepare_download_path(custom_path: str | None, album_name: str | None) -> str:
    path = custom_path or "downloads"
    if album_name:
        path = os.path.join(path, album_name)
    path = path.replace("\n", "")
    os.makedirs(path, exist_ok=True)
    DownloadTracker(path).ensure_exists()
    return path


def _mark_downloaded(item_url: str, download_path: str) -> None:
    DownloadTracker(download_path).mark_done(item_url)


def _write_url_to_list(item_url: str, download_path: str) -> None:
    fp = os.path.join(download_path, "url_list.txt")
    with open(fp, "a", encoding="utf-8") as f:
        f.write(f"{item_url}\n")


def _is_date_in_range(date_string: str, date_before: datetime | None, date_after: datetime | None) -> bool:
    try:
        bunkr_date = datetime.strptime(date_string, "%H:%M:%S %d/%m/%Y")
        upper = date_before or datetime.max
        lower = date_after or datetime.min
        return lower <= bunkr_date <= upper
    except ValueError:
        print(f"\t[-] Invalid file date: {date_string!r}")
        return False


def _parse_date_arg(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        raise ValueError(f"Invalid date format {value!r} — use: YYYY-MM-DDTHH:MM:SS")
