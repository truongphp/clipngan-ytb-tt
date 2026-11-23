import os
from pathlib import Path
import requests


def _gh_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "clipngan-bot",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_or_create_release(repo: str, tag: str) -> dict | None:
    api_base = f"https://api.github.com/repos/{repo}/releases"
    resp = requests.get(f"{api_base}/tags/{tag}", headers=_gh_headers(), timeout=20)
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 404:
        create = requests.post(
            api_base,
            headers=_gh_headers(),
            json={
                "tag_name": tag,
                "name": tag,
                "body": f"Kho lưu trữ tự động cho {tag}",
                "draft": False,
                "prerelease": False,
            },
            timeout=20,
        )
        if create.status_code in (200, 201):
            return create.json()
        print(f"[ReleaseStore] Không tạo được Release '{tag}': {create.status_code} {create.text}")
        return None
    print(f"[ReleaseStore] Lỗi đọc Release '{tag}': {resp.status_code}")
    return None


def upload_release_asset(tag: str, file_path: Path) -> bool:
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not repo or not file_path.exists():
        return False

    release = _get_or_create_release(repo, tag)
    if not release:
        return False

    # Xóa file trùng tên cũ trên Release trước khi up lại (tránh lỗi 422 Unprocessable Entity)
    for asset in release.get("assets", []):
        if asset.get("name") == file_path.name:
            del_url = f"https://api.github.com/repos/{repo}/releases/assets/{asset['id']}"
            requests.delete(del_url, headers=_gh_headers(), timeout=20)

    upload_url = release["upload_url"].split("{")[0]
    headers = _gh_headers()
    headers["Content-Type"] = "application/octet-stream"

    print(f"[ReleaseStore] Đang lưu '{file_path.name}' vào Release '{tag}'...")
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{upload_url}?name={file_path.name}",
            headers=headers,
            data=f,
            timeout=180,
        )
    resp.raise_for_status()
    print(f"[ReleaseStore] Đã lưu '{file_path.name}' thành công.")
    return True


def download_release_assets(tag: str, dest_dir: Path, allowed_exts: set[str] | None = None) -> list[Path]:
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not repo:
        return []
    dest_dir.mkdir(parents=True, exist_ok=True)

    resp = requests.get(
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        headers=_gh_headers(),
        timeout=20,
    )
    if resp.status_code != 200:
        return []

    saved = []
    for asset in resp.json().get("assets", []):
        name = asset.get("name", "")
        if allowed_exts and Path(name).suffix.lower() not in allowed_exts:
            continue
        out_path = dest_dir / name
        dl = requests.get(
            asset["url"],
            headers={**_gh_headers(), "Accept": "application/octet-stream"},
            stream=True,
            timeout=180,
        )
        if dl.status_code == 200:
            with open(out_path, "wb") as f:
                for chunk in dl.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            saved.append(out_path)
    return saved
