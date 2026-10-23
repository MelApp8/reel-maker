"""Renders a 1080x1920 MP4 reel with ffmpeg: real photos with slow zoom, captions, progress bar, voiceover and music."""
import random
import shutil
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from . import audio, config

W, H, FPS = config.W, config.H, config.FPS
ACCENT = (255, 212, 0)        # yellow
ACCENT_2 = (255, 45, 85)      # pink-red
PX, PY, PW, PH = 60, 230, 960, 1100   # where the photo sits


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
    for width in range(34, 6, -1):
        lines = textwrap.wrap(text, width=width)
        if all(draw.textlength(line, font=fnt) <= max_w for line in lines):
            return lines
    return textwrap.wrap(text, width=6)


def _cover(img, w, h, top_bias=0.25):
    """Scale and crop to fill w x h. Keeps more of the top, where faces usually are."""
    scale = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * scale)), max(h, round(img.height * scale))), Image.LANCZOS)
    x = (img.width - w) // 2
    y = int((img.height - h) * top_bias)
    return img.crop((x, y, x + w, y + h))


def prepare_photo(path, work, i):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    bg = _cover(img, W // 4, H // 4).filter(ImageFilter.GaussianBlur(12)).resize((W, H), Image.LANCZOS)
    bg = ImageEnhance.Brightness(bg).enhance(0.38)
    bg.save(work / f"bg{i}.jpg", quality=90)
    _cover(img, PW * 2, PH * 2).save(work / f"photo{i}.jpg", quality=92)
    return work / f"bg{i}.jpg", work / f"photo{i}.jpg"


def mask_png(path):
    m = Image.new("L", (PW, PH), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, PW - 1, PH - 1), radius=44, fill=255)
    m.save(path)


def caption_png(slide, path, credit=""):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if credit:
        cf = font(24, bold=False)
        credit = "Photo: " + credit
        while d.textlength(credit, font=cf) > PW - 20 and len(credit) > 10:
            credit = credit[:-4] + "..."
        d.text((PX + PW - d.textlength(credit, font=cf), PY + PH + 10), credit, font=cf, fill=(255, 255, 255, 150))
    top = PY + PH + 70
    kicker = (slide.get("kicker") or "").upper()
    if kicker:
        kf = font(36)
        kw = d.textlength(kicker, font=kf)
        d.rounded_rectangle(((W - kw) / 2 - 24, top, (W + kw) / 2 + 24, top + 60), radius=30, fill=ACCENT)
        d.text(((W - kw) / 2, top + 9), kicker, font=kf, fill=(20, 20, 20))
        top += 90
    size = 66
    while True:
        fnt = font(size)
        lines = _wrap(d, slide["text"], fnt, W - 140)
        line_h = int(size * 1.2)
        if top + line_h * len(lines) <= H - 150 or size <= 40:
            break
        size -= 4
    for line in lines:
        d.text(((W - d.textlength(line, font=fnt)) / 2, top), line, font=fnt, fill="white",
               stroke_width=2, stroke_fill=(0, 0, 0))
        top += line_h
    img.save(path)


def header_png(path, name, handle):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    label = (name or "").upper()
    f = font(36)
    while d.textlength(label, font=f) > W - 200 and len(label) > 10:
        label = label[:-4] + "..."
    if label:
        tw = d.textlength(label, font=f)
        d.rounded_rectangle(((W - tw) / 2 - 30, 120, (W + tw) / 2 + 30, 186), radius=33, fill=ACCENT_2)
        d.text(((W - tw) / 2, 132), label, font=f, fill="white")
    if handle:
        hf = font(34, bold=False)
        hw = d.textlength(handle, font=hf)
        d.text(((W - hw) / 2, H - 110), handle, font=hf, fill=(255, 255, 255, 200))
    img.save(path)


def _durations(slides, total, voice_lens=None):
    weights = [len(s["text"]) + 35 for s in slides]
    durs = [max(2.6, total * w / sum(weights)) for w in weights]
    if voice_lens:  # every caption stays up until its voiceover has finished
        durs = [max(d, v + 0.5) if v else d for d, v in zip(durs, voice_lens)]
    return durs


def render(script, photos, out_dir, rank=1):
    """photos: list of {'path', 'credit'}; at least one is required."""
    if not photos:
        raise ValueError("no photos for this topic")
    work = out_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)
    slides = script["slides"]
    voices = []
    if config.VOICEOVER:
        for i, sl in enumerate(slides):
            path = work / f"voice{i}.mp3"
            voices.append((path, audio.voice(sl["text"], path)))
            if voices[-1][1] is None:
                voices = []  # voice service unavailable: music only
                break
    durs = _durations(slides, config.REEL_SECONDS, [v for _, v in voices])
    total = sum(durs)
    args, filters, n = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"], [], 0
    mask_png(work / "mask.png")
    prepared = {}

    # One segment per caption: blurred backdrop + the photo slowly zooming
    for i, seg in enumerate(durs):
        k = i % len(photos)
        if k not in prepared:
            prepared[k] = prepare_photo(photos[k]["path"], work, k)
        bg, ph = prepared[k]
        frames = int(round(seg * FPS))
        z = f"1+0.10*on/{frames}" if i % 2 == 0 else f"1.10-0.10*on/{frames}"
        args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg:.3f}", "-i", str(bg)]
        args += ["-i", str(ph)]
        args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg:.3f}", "-i", str(work / "mask.png")]
        filters.append(f"[{n + 1}:v]zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}"
                       f":s={PW}x{PH}:fps={FPS},format=yuva420p[pz{i}]")
        filters.append(f"[pz{i}][{n + 2}:v]alphamerge[pm{i}]")
        filters.append(f"[{n}:v]format=yuv420p,setsar=1[bgv{i}]")
        filters.append(f"[bgv{i}][pm{i}]overlay={PX}:{PY}:shortest=1,trim=duration={seg:.3f},setpts=PTS-STARTPTS[seg{i}]")
        n += 3
    filters.append("".join(f"[seg{i}]" for i in range(len(slides))) + f"concat=n={len(slides)}:v=1:a=0[base]")

    header_png(work / "header.png", script.get("topic", ""), config.HANDLE)
    args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", str(work / "header.png")]
    filters.append(f"[base][{n}:v]overlay=0:0[v0]")
    n += 1

    args += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", f"color=c=0xFFD400:s={W}x12:r={FPS}"]
    filters.append(f"[v0][{n}:v]overlay=x='-w+w*t/{total:.3f}':y=0[v1]")
    n += 1

    last, start = "v1", 0.0
    for i, (slide, seg) in enumerate(zip(slides, durs)):
        png = work / f"cap{i}.png"
        caption_png(slide, png, photos[i % len(photos)].get("credit", ""))
        end = start + seg
        args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg:.3f}", "-i", str(png)]
        filters.append(f"[{n}:v]format=rgba,fade=in:st=0:d=0.25:alpha=1,setpts=PTS-STARTPTS+{start:.3f}/TB[c{i}]")
        filters.append(f"[{last}][c{i}]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})':eof_action=pass[o{i}]")
        last, start = f"o{i}", end
        n += 1

    tracks = [p for p in config.MUSIC_DIR.glob("*") if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac", ".ogg")]
    track = random.choice(tracks) if tracks else audio.music(work / "music.wav", total + 0.5, seed=rank)
    args += ["-stream_loop", "-1", "-i", str(track)]
    level = config.MUSIC_VOLUME if voices else 0.8
    filters.append(f"[{n}:a]atrim=duration={total:.3f},afade=t=out:st={total - 1.5:.3f}:d=1.5,volume={level},"
                   f"aformat=sample_rates=44100:channel_layouts=stereo[mus]")
    n += 1
    mix, start = ["[mus]"], 0.0
    for i, ((path, _), seg) in enumerate(zip(voices, durs)):
        args += ["-i", str(path)]
        ms = int((start + 0.15) * 1000)
        filters.append(f"[{n}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.4,adelay={ms}|{ms}[vo{i}]")
        mix.append(f"[vo{i}]")
        start += seg
        n += 1
    if voices:
        filters.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first[aout]")
    else:
        filters.append("[mus]anull[aout]")

    reel = out_dir / "reel.mp4"
    args += ["-filter_complex", ";".join(filters), "-map", f"[{last}]", "-map", "[aout]", "-t", f"{total:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(reel)]
    subprocess.run(args, check=True)

    cover = out_dir / "cover.jpg"
    subprocess.run([ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{min(durs[0] * 0.7, 2):.2f}",
                    "-i", str(reel), "-frames:v", "1", "-q:v", "3", str(cover)], check=True)
    shutil.rmtree(work, ignore_errors=True)
    return reel, cover
