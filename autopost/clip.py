"""Müzikten dikey (9:16) TikTok klibi üretir. Sadece ffmpeg/ffprobe gerekir."""
from __future__ import annotations

import array
import json
import subprocess
from pathlib import Path

W, H = 1080, 1920


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"{cmd[0]} hata verdi: {e.stderr.decode(errors='replace')[-800:]}") from e


def probe(path: str | Path) -> tuple[float, bool, bool]:
    """(süre_sn, gerçek_video_var_mı, ses_var_mı). Kapak resmi video sayılmaz."""
    out = _run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]).stdout
    data = json.loads(out)
    has_video = has_audio = False
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic"):
            has_video = True
        elif s.get("codec_type") == "audio":
            has_audio = True
    return float(data["format"]["duration"]), has_video, has_audio


def energy_per_second(path: str | Path, rate: int = 4000) -> list[float]:
    """Her saniye için ses enerjisi (RMS). Düşük örnekleme hızı hızlı hesap için yeterli."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"]
    raw = _run(cmd).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    result = []
    for i in range(len(samples) // rate):
        chunk = samples[i * rate:(i + 1) * rate]
        result.append((sum(x * x for x in chunk) / rate) ** 0.5)
    return result


def best_window(energy: list[float], win: int, exclude: list[tuple[float, float]] | None = None,
                skip_start: int = 5) -> tuple[int, int]:
    """En yüksek ortalama enerjili `win` saniyelik pencerenin (başlangıç, uzunluk) değeri.

    `exclude`: daha önce kullanılmış (başlangıç, bitiş) aralıkları; çakışanlar atlanır.
    """
    n = len(energy)
    if n <= win:
        return 0, max(n, 1)
    exclude = exclude or []
    prefix = [0.0]
    for e in energy:
        prefix.append(prefix[-1] + e)
    best: tuple[float, int] | None = None
    for s in range(min(skip_start, n - win), n - win + 1):
        if any(s < b and s + win > a for a, b in exclude):
            continue
        score = (prefix[s + win] - prefix[s]) / win
        if best is None or score > best[0]:
            best = (score, s)
    start = best[1] if best else min(skip_start, n - win)
    return start, win


def make_clip(src: str | Path, out: str | Path, start: float, length: float) -> Path:
    """`src` içinden [start, start+length) kesitini 1080x1920 MP4 olarak yazar.

    Videolu kaynakta yatay görüntü bulanık arka plan üstüne ortalanır (kenarlar kesilmez).
    Sadece sesli kaynakta dalga formu görseli üretilir.
    """
    _, has_video, has_audio = probe(src)
    if not has_audio:
        raise RuntimeError(f"{src} içinde ses akışı yok")
    audio = (f"afade=t=in:d=0.3,afade=t=out:st={max(length - 0.8, 0):.2f}:d=0.8,"
             "loudnorm=I=-14:TP=-1.5:LRA=11")
    if has_video:
        fc = (f"[0:v]split=2[bg][fg];"
              f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:6[b];"
              f"[fg]scale={W}:{H}:force_original_aspect_ratio=decrease[f];"
              f"[b][f]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[v];"
              f"[0:a]{audio}[a]")
    else:
        fc = (f"[0:a]asplit=2[a1][a2];"
              f"[a1]showwaves=s={W}x700:mode=cline:colors=0xff2d55:r=30[w];"
              f"color=c=black:s={W}x{H}:r=30,format=yuv420p[bg];"
              f"[bg][w]overlay=0:610:shortest=1[v];"
              f"[a2]{audio}[a]")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", str(src),
           "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-maxrate", "8M", "-bufsize", "16M",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", f"{length:.2f}", str(out)]
    _run(cmd)
    return out
