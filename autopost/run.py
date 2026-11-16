"""Günlük çalıştırıcı: sıradaki şarkıyı seç, klip üret, TikTok'a yayınla, durumu kaydet.

Kullanım:  python -m autopost.run [--dry-run] [--track ID]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

from . import clip, tiktok

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog.json"
STATE = ROOT / "state" / "posted.json"
OUT = ROOT / "out"
CACHE = ROOT / "media" / "cache"

DEFAULT_TAGS = ["#phonk", "#brazilianphonk", "#phonkbrasileiro", "#driftphonk", "#cynoraphonk", "#fyp"]


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def pick_track(catalog: list[dict], state: list[dict], forced: str | None) -> dict:
    if forced:
        return next(t for t in catalog if t["id"] == forced)
    posted = {p["id"] for p in state}
    fresh = [t for t in catalog if t["id"] not in posted]
    if fresh:
        return fresh[0]
    # hepsi paylaşıldıysa en eski paylaşılanı yeni bir kesitle tekrar kullan
    last: dict[str, str] = {}
    for p in state:
        last[p["id"]] = p["at"]
    return min(catalog, key=lambda t: last.get(t["id"], ""))


def resolve_source(track: dict) -> Path:
    if "file" in track:
        path = ROOT / track["file"]
        if not path.exists():
            raise FileNotFoundError(f"Kaynak dosya yok: {path}")
        return path
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"{track['id']}.mp4"
    if not target.exists():
        cmd = ["yt-dlp", "-f", "bv*[height<=1080]+ba/b", "--merge-output-format", "mp4",
               "-o", str(target), track["youtube"]]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not target.exists():
            raise RuntimeError("yt-dlp indiremedi (GitHub sunucularında YouTube bot doğrulaması "
                               f"isteyebilir). Orijinal dosyayı media/ altına koyup catalog'da 'file' kullanın.\n"
                               f"{r.stderr[-600:]}")
    return target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Klibi üret ama TikTok'a gönderme")
    ap.add_argument("--track")
    ap.add_argument("--length", type=int, default=int(os.getenv("CLIP_SECONDS", "30")))
    args = ap.parse_args()

    catalog = load_json(CATALOG, [])
    if not catalog:
        print("catalog.json boş: en az bir şarkı ekleyin.", file=sys.stderr)
        return 2
    state = load_json(STATE, [])
    track = pick_track(catalog, state, args.track)
    print(f"Seçilen şarkı: {track['id']} - {track['title']}")

    src = resolve_source(track)
    duration, _, _ = clip.probe(src)
    length = int(min(args.length, duration))
    used = [tuple(p["window"]) for p in state if p["id"] == track["id"] and p.get("window")]
    start, length = clip.best_window(clip.energy_per_second(src), length, exclude=used)
    out = clip.make_clip(src, OUT / f"{track['id']}.mp4", start, length)
    print(f"Klip hazır: {out} ({out.stat().st_size / 1e6:.1f} MB, {start}s'den {length}s)")

    tags = track.get("hashtags", DEFAULT_TAGS)
    caption = f"{track['title']} 🔥 {' '.join(tags)}"
    print("Caption:", caption)
    if args.dry_run:
        print("Dry-run: TikTok'a gönderilmedi.")
        return 0

    key, secret, rt = (os.environ[k] for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"))
    tok = tiktok.refresh_access_token(key, secret, rt)
    if tok.get("refresh_token") and tok["refresh_token"] != rt:
        # Workflow, SECRETS_PAT varsa bunu secret olarak günceller.
        Path(os.getenv("RUNNER_TEMP", "/tmp"), "new_refresh_token").write_text(tok["refresh_token"])
        print("Uyarı: refresh token değişti; secret güncellenmeli.")

    privacy = os.getenv("TIKTOK_PRIVACY", "SELF_ONLY")
    result = tiktok.post_video(tok["access_token"], out, caption, privacy)
    print("Yayınlandı:", result)

    state.append({"id": track["id"], "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                  "publish_id": result["publish_id"], "privacy": privacy, "window": [start, start + length]})
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
