"""TikTok Content Posting API (Direct Post, FILE_UPLOAD) için küçük, bağımsız istemci."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://open.tiktokapis.com"
MAX_SINGLE_CHUNK = 64 * 1024 * 1024  # tek parça yükleme üst sınırı


class TikTokError(RuntimeError):
    pass


def _http(method: str, url: str, headers: dict, body: bytes | None = None, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        raise TikTokError(f"HTTP {e.code} {url}: {raw[:500].decode(errors='replace')}") from e
    return json.loads(raw) if raw else {}


def _check(resp: dict, what: str) -> dict:
    err = resp.get("error") or {}
    if err.get("code", "ok") != "ok":
        raise TikTokError(f"{what} başarısız: {err.get('code')}: {err.get('message')} (log_id={err.get('log_id')})")
    return resp.get("data", {})


def refresh_access_token(client_key: str, client_secret: str, refresh_token: str) -> dict:
    body = urllib.parse.urlencode({
        "client_key": client_key, "client_secret": client_secret,
        "grant_type": "refresh_token", "refresh_token": refresh_token,
    }).encode()
    resp = _http("POST", f"{API}/v2/oauth/token/",
                 {"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"}, body)
    if "access_token" not in resp:
        raise TikTokError(f"Token yenilenemedi: {resp}")
    return resp  # access_token, refresh_token, expires_in, open_id, scope ...


def _auth(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"}


def creator_info(access_token: str) -> dict:
    resp = _http("POST", f"{API}/v2/post/publish/creator_info/query/", _auth(access_token), b"")
    return _check(resp, "creator_info")


def post_video(access_token: str, video: str | Path, title: str, privacy: str,
               disable_comment: bool = False, poll_timeout: int = 300) -> dict:
    """Videoyu yükleyip yayınlar. Dönen sözlükte publish_id ve son durum bulunur."""
    info = creator_info(access_token)
    options = info.get("privacy_level_options", [])
    if privacy not in options:
        raise TikTokError(f"'{privacy}' bu hesapta kullanılamıyor. Seçenekler: {options}. "
                          "Onaylanmamış (denetimden geçmemiş) uygulamalar yalnızca SELF_ONLY kullanabilir.")
    video = Path(video)
    size = video.stat().st_size
    if size > MAX_SINGLE_CHUNK:
        raise TikTokError(f"Klip {size / 1e6:.0f} MB; tek parça sınırı 64 MB. Klibi kısaltın.")

    payload = {
        "post_info": {"title": title[:2200], "privacy_level": privacy,
                      "disable_duet": False, "disable_stitch": False, "disable_comment": disable_comment},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1},
    }
    data = _check(_http("POST", f"{API}/v2/post/publish/video/init/", _auth(access_token),
                        json.dumps(payload).encode()), "init")
    publish_id, upload_url = data["publish_id"], data["upload_url"]

    _http("PUT", upload_url, {"Content-Type": "video/mp4", "Content-Length": str(size),
                              "Content-Range": f"bytes 0-{size - 1}/{size}"}, video.read_bytes(), timeout=600)

    deadline = time.time() + poll_timeout
    status = {}
    while time.time() < deadline:
        status = _check(_http("POST", f"{API}/v2/post/publish/status/fetch/", _auth(access_token),
                              json.dumps({"publish_id": publish_id}).encode()), "status")
        state = status.get("status")
        if state == "PUBLISH_COMPLETE":
            break
        if state == "FAILED":
            raise TikTokError(f"Yayın başarısız: {status.get('fail_reason')}")
        time.sleep(5)
    else:
        raise TikTokError(f"Zaman aşımı, son durum: {status}")
    return {"publish_id": publish_id, "status": status}


# ---- İlk kurulum yardımcıları (bir kez yerelde çalıştırılır) ----

def authorize_url(client_key: str, redirect_uri: str, state: str = "autopost") -> str:
    q = urllib.parse.urlencode({"client_key": client_key, "scope": "user.info.basic,video.publish",
                                "response_type": "code", "redirect_uri": redirect_uri, "state": state})
    return f"https://www.tiktok.com/v2/auth/authorize/?{q}"


def exchange_code(client_key: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    body = urllib.parse.urlencode({
        "client_key": client_key, "client_secret": client_secret, "code": urllib.parse.unquote(code),
        "grant_type": "authorization_code", "redirect_uri": redirect_uri}).encode()
    return _http("POST", f"{API}/v2/oauth/token/",
                 {"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"}, body)


if __name__ == "__main__":  # python -m autopost.tiktok  -> yetkilendirme yardımcısı
    key = os.environ["TIKTOK_CLIENT_KEY"]
    secret = os.environ["TIKTOK_CLIENT_SECRET"]
    redirect = os.environ["TIKTOK_REDIRECT_URI"]
    print("1) Bu adresi tarayıcıda aç, CYNORAPHONK hesabıyla izin ver:\n\n", authorize_url(key, redirect), "\n")
    code = input("2) Yönlendirilen adresteki code= değerini yapıştır: ").strip()
    tok = exchange_code(key, secret, code, redirect)
    print("\nrefresh_token (GitHub secret TIKTOK_REFRESH_TOKEN olarak kaydet):\n", tok.get("refresh_token"))
    print("scope:", tok.get("scope"), "| open_id:", tok.get("open_id"))
