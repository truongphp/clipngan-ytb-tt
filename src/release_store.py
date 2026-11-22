import os
from pathlib import Path
import requests


def _headers(accept: str = "application/vnd.github+json") -> dict:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    h = {"Accept": accept, "User-Agent": "clipngan-bot"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _repo() -> str:
    return os.getenv("GITHUB_REPOSITORY", "").strip()


def get_or_create_release(tag: str, title: str | None = None) -> dict | None:
    repo = _repo()
    if not repo or not os.getenv("GITHUB_TOKEN"):
        return None

    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    resp = requests.get(url, headers=_headers(), timeout=30)
    if resp.status_code == 200:
        return resp.json()

    create_url = f"https://api.github.com/repos/{repo}/releases"
    create_resp = requests.post(
        create_url,
        headers=_headers(),
        json={
            "tag_name": tag,
            "name": title or f"Archive {tag}",
            "draft": False,
            "prerelease": False,
        },
        timeout=30,
    )
    create_resp.raise_for_status()
    return create_resp.json()


def download_release_assets(tag: str, dest_dir: Path, allowed_exts: set[str] | None = None) -> list[Path]:
    repo = _repo()
    if not repo:
        return []

    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    resp = requests.get(url, headers=_headers(), timeout=30)
    if resp.status_code != 200:
        print(f"[ReleaseStore] Không tìm thấy Release tag '{tag}' (HTTP {resp.status_code}).")
        return []

    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for asset in resp.json().get("assets", []):
        name = asset["name"]
        if allowed_exts and Path(name).suffix.lower() not in allowed_exts:
            continue
        target = dest_dir / name
        print(f"[ReleaseStore] Đang tải '{name}' từ Release '{tag}'...")
        with requests.get(
            asset["url"],
            headers=_headers("application/octet-stream"),
            stream=True,
            timeout=180,
        ) as dl:
            dl.raise_for_status()
            with open(target, "wb") as f:
                for chunk in dl.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        downloaded.append(target)
    return sorted(downloaded)


def upload_release_asset(tag: str, file_path: Path) -> None:
    repo = _repo()
    if not repo or not os.getenv("GITHUB_TOKEN") or not file_path.exists():
        return

    rel = get_or_create_release(tag)
    if not rel:
        return

    # Xóa asset trùng tên cũ nếu chạy lại cùng tập
    for asset in rel.get("assets", []):
        if asset["name"] == file_path.name:
            requests.delete(
                f"https://api.github.com/repos/{repo}/releases/assets/{asset['id']}",
                headers=_headers(),
                timeout=30,
            )

    upload_url = f"https://uploads.github.com/repos/{repo}/releases/{rel['id']}/assets"
    print(f"[ReleaseStore] Đang lưu '{file_path.name}' vào Release '{tag}'...")
    with open(file_path, "rb") as f:
        resp = requests.post(
            upload_url,
            headers={**_headers(), "Content-Type": "application/octet-stream"},
            params={"name": file_path.name},
            data=f,
            timeout=180,
        )
    resp.raise_for_status()
