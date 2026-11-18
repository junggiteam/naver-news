"""Mirror metadata from the publisher-selected, public So What archive.

No subscriber data or Stibee API key is used. The archive determines publication;
the share page's og:image supplies the publisher-selected representative image.
Keep the last successful manifest on upstream errors or unexpected HTML changes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
ARCHIVE_URL = "https://page.stibee.com/archives/479387"
MANIFEST = ROOT / "data/sowhat_archive.json"
STATUS = ROOT / "data/sowhat_archive_status.json"
INTERVAL_SECONDS = 20 * 60
IMAGE_HOSTS = {"img.stibee.com", "img2.stibee.com", "cdn.stibee.com", "resource.stibee.com", "cdn.imweb.me"}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def session() -> requests.Session:
    client = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    client.mount("https://", HTTPAdapter(max_retries=retry))
    client.headers["User-Agent"] = "BestExit-SoWhatArchive/1.0 (+https://bestexit.co.kr/sowhat-archives)"
    return client


def get_html(url: str) -> str:
    with session() as client:
        response = client.get(url, timeout=(10, 25))
        response.raise_for_status()
        return response.content.decode("utf-8-sig")


def parse_archive(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for anchor in soup.find_all("a", href=True):
        url = anchor["href"]
        match = re.fullmatch(r"https://stib\.ee/([A-Za-z0-9_-]+)", url)
        if not match or url in seen:
            continue
        text = anchor.get_text(" ", strip=True)
        date = re.search(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.", text)
        if not date:
            continue
        published = f"{date[1]}-{int(date[2]):02d}-{int(date[3]):02d}"
        datetime.strptime(published, "%Y-%m-%d")
        title = text[:date.start()].strip()
        if not title:
            continue
        seen.add(url)
        items.append({"id": match[1], "url": url, "date": published, "title": title})
    if not items:
        raise ValueError("Public archive contains no recognizable published issues; retaining the last successful manifest.")
    return sorted(items, key=lambda x: x["date"], reverse=True)


def parse_letter(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", attrs={"property": "og:image"})
    image = meta.get("content", "").strip() if meta else ""
    parsed = urlparse(image)
    if parsed.scheme != "https" or parsed.hostname not in IMAGE_HOSTS:
        image = ""
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    volume = re.search(r"Vol\s*\.?\s*(\d+)", text, re.I)
    if len(text) < 50:
        raise ValueError("Share page has no readable newsletter content.")
    return {"image": image, "volume": int(volume[1]) if volume else None}


def synchronize(*, seed_dir: Path | None = None, force: bool = False) -> dict:
    previous = read_json(MANIFEST, {"items": []})
    old = {x["id"]: x for x in previous.get("items", [])}
    status = read_json(STATUS, {})
    if not force and not seed_dir and status.get("ok") and status.get("checkedAt"):
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(status["checkedAt"])).total_seconds()
        if elapsed < INTERVAL_SECONDS:
            return {"skipped": True, "count": len(old)}

    archive_html = ((seed_dir / "archive-source.html").read_text(encoding="utf-8-sig") if seed_dir else get_html(ARCHIVE_URL))
    published = parse_archive(archive_html)
    if old and len(published) < len(old) * 0.75:
        raise ValueError("Unexpected archive shrinkage; retaining the last successful manifest.")
    refreshed = {}
    required = [x for i, x in enumerate(published) if x["id"] not in old or i < 2 or seed_dir]

    def fetch(item):
        html = ((seed_dir / "letters" / (item["id"] + ".html")).read_text(encoding="utf-8-sig") if seed_dir else get_html(item["url"]))
        return item["id"], parse_letter(html)

    with ThreadPoolExecutor(max_workers=4) as executor:
        for future in as_completed([executor.submit(fetch, x) for x in required]):
            issue_id, metadata = future.result()
            refreshed[issue_id] = metadata

    items = []
    for item in published:
        metadata = refreshed.get(item["id"], old.get(item["id"], {}))
        image = metadata.get("image") or old.get(item["id"], {}).get("image", "")
        items.append({**item, "image": image, "volume": metadata.get("volume")})

    if items != previous.get("items"):
        write_json(MANIFEST, {"schemaVersion": 1, "source": ARCHIVE_URL, "updatedAt": timestamp(), "items": items})
    write_json(STATUS, {"ok": True, "checkedAt": timestamp(), "count": len(items), "mode": "seed" if seed_dir else "live"})
    return {"skipped": False, "count": len(items), "refreshed": len(refreshed), "changed": items != previous.get("items")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-dir", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(synchronize(seed_dir=args.seed_dir, force=args.force)))
        return 0
    except Exception as error:
        write_json(STATUS, {"ok": False, "checkedAt": timestamp(), "error": str(error)[:400]})
        print(f"So What archive update failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
