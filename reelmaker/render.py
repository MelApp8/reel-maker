"""Renders a 1080x1920 MP4 reel with ffmpeg: background clips, timed captions, progress bar, music."""
import random
import shutil
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import config

W, H, FPS = config.W, config.H, config.FPS
ACCENT = (255, 212, 0)        # yellow
ACCENT_2 = (255, 45, 85)      # pink-red
PALETTES = [((255, 94, 98), (88, 24, 140)), ((0, 198, 255), (0, 40, 120)), ((255, 175, 64), (180, 30, 90)),
            ((60, 220, 160), (10, 60, 110)), ((150, 90, 255), (20, 10, 60))]


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("ffmpeg not found. Run: pip install imageio-ffmpeg  (or install ffmpeg)")


def font(size, bold=True):
    name = "Inter-ExtraBold.otf" if bold else "Inter-SemiBold.otf"
    return ImageFont.truetype(str(config.FONTS_DIR / name), size)


def _wrap(draw, text, fnt, max_w):
    for width in range(28, 6, -1):
        lines = textwrap.wrap(text, width=width)
        if all(draw.textlength(line, font=fnt) <= max_w for line in lines):
            return lines
    return textwrap.wrap(text, width=6)


def caption_png(slide, path, big=False):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 96 if big else 74
    fnt = font(size)
    lines = _wrap(d, slide["text"], fnt, 880)
    while len(lines) > 5 and size > 50:
        size -= 6
        fnt = font(size)
        lines = _wrap(d, slide["text"], fnt, 880)
    line_h = int(size * 1.18)
    box_h = line_h * len(lines) + 70
    top = int(H * 0.56) - box_h // 2
    d.rounded_rectangle((70, top, W - 70, top + box_h), radius=40, fill=(0, 0, 0, 170))
    y = top + 35
    for line in lines:
        x = (W - d.textlength(line, font=fnt)) / 2
        d.text((x, y), line, font=fnt, fill="white", stroke_width=3, stroke_fill=(0, 0, 0))
        y += line_h
    kicker = (slide.get("kicker") or "").upper()
    if kicker:
        kf = font(40)
        kw = d.textlength(kicker, font=kf)
        d.rounded_rectangle(((W - kw) / 2 - 28, top - 90, (W + kw) / 2 + 28, top - 18), radius=36, fill=ACCENT)
        d.text(((W - kw) / 2, top - 82), kicker, font=kf, fill=(20, 20, 20))
    img.save(path)


def header_png(path, rank, handle):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    label = f"TRENDING #{rank} TODAY" if rank else "TRENDING NOW"
    f = font(42)
    tw = d.textlength(label, font=f)
    d.rounded_rectangle((60, 110, 60 + tw + 64, 186), radius=38, fill=ACCENT_2)
    d.text((92, 122), label, font=f, fill="white")
    if handle:
        hf = font(40, bold=False)
        hw = d.textlength(handle, font=hf)
        d.text(((W - hw) / 2, H - 230), handle, font=hf, fill=(255, 255, 255, 210), stroke_width=2, stroke_fill=(0, 0, 0))
    img.save(path)


def gradient_png(path, palette):
    w, h = W + 300, H + 300
    top, bottom = palette
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)))
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for _ in range(7):  # soft light blobs so the background isn't flat
        r = random.randint(160, 420)
        x, y = random.randint(0, w), random.randint(0, h)
        g.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 28))
    img = Image.alpha_composite(img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(60))).convert("RGB")
    img.save(path)


def render(script, clips, out_dir, rank=1):
    """clips: list of {'path': ...}. Empty list -> animated gradient background."""
    work = out_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)
    slides = script["slides"]
    total = config.REEL_SECONDS
    seg = total / len(slides)
    args, filters, n = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"], [], 0

    # Background: one segment per caption
    for i in range(len(slides)):
        if clips:
            clip = clips[i % len(clips)]
            offset = (i // len(clips)) * seg
            args += ["-stream_loop", "-1", "-ss", f"{offset:.2f}", "-t", f"{seg:.3f}", "-i", clip["path"]]
            filters.append(f"[{n}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                           f"setsar=1,fps={FPS},format=yuv420p,trim=duration={seg:.3f},setpts=PTS-STARTPTS[bg{i}]")
        else:
            g = work / f"grad{i}.png"
            gradient_png(g, PALETTES[(rank + i) % len(PALETTES)])
            args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg:.3f}", "-i", str(g)]
            filters.append(f"[{n}:v]crop={W}:{H}:x='300*t/{seg:.3f}':y='300*t/{seg:.3f}',"
                           f"setsar=1,format=yuv420p,trim=duration={seg:.3f},setpts=PTS-STARTPTS[bg{i}]")
        n += 1
    filters.append("".join(f"[bg{i}]" for i in range(len(slides))) + f"concat=n={len(slides)}:v=1:a=0,"
                   f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.28:t=fill[base]")

    # Header overlay (whole reel)
    header_png(work / "header.png", rank, config.HANDLE)
    args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", str(work / "header.png")]
    filters.append(f"[base][{n}:v]overlay=0:0[v0]")
    n += 1

    # Progress bar
    args += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", f"color=c=0xFFD400:s={W}x14:r={FPS}"]
    filters.append(f"[v0][{n}:v]overlay=x='-w+w*t/{total:.3f}':y=0[v1]")
    n += 1

    # Captions, each faded in at its own time
    last = "v1"
    for i, slide in enumerate(slides):
        png = work / f"cap{i}.png"
        caption_png(slide, png, big=(i == 0))
        start, end = i * seg, (i + 1) * seg
        args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg:.3f}", "-i", str(png)]
        filters.append(f"[{n}:v]format=rgba,fade=in:st=0:d=0.3:alpha=1,setpts=PTS-STARTPTS+{start:.3f}/TB[c{i}]")
        filters.append(f"[{last}][c{i}]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})':eof_action=pass[o{i}]")
        last = f"o{i}"
        n += 1

    # Audio: a random track from music/ if you add some, otherwise silence
    tracks = [p for p in config.MUSIC_DIR.glob("*") if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac", ".ogg")]
    if tracks:
        args += ["-stream_loop", "-1", "-i", str(random.choice(tracks))]
        filters.append(f"[{n}:a]atrim=duration={total:.3f},afade=t=out:st={total - 1.5:.3f}:d=1.5,volume=0.8[aout]")
    else:
        args += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        filters.append(f"[{n}:a]anull[aout]")

    reel = out_dir / "reel.mp4"
    args += ["-filter_complex", ";".join(filters), "-map", f"[{last}]", "-map", "[aout]", "-t", f"{total:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(reel)]
    subprocess.run(args, check=True)

    cover = out_dir / "cover.jpg"
    subprocess.run([ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{min(seg * 0.6, 2):.2f}",
                    "-i", str(reel), "-frames:v", "1", "-q:v", "3", str(cover)], check=True)
    shutil.rmtree(work, ignore_errors=True)
    return reel, cover
