# Reel Maker

Every day it picks up the top trending Google searches and turns each one into a ready-to-post vertical reel (1080x1920 MP4, 18 seconds) with on-screen captions, stock footage, a title, a post caption, hashtags and YouTube tags. You download or share them from a small app in your browser.

## Use it from your phone only (no computer)

GitHub runs the app for free every morning and publishes your reels to your own phone page, `https://<your-github-name>.github.io/reel-maker/`.

1. Put this folder in a public GitHub repository named `reel-maker`. Free GitHub accounts can only publish pages from public repos. Your API keys stay secret either way.
2. In the repo go to **Settings > Pages** and set **Source** to **GitHub Actions**.
3. In **Settings > Secrets and variables > Actions**, add the secret `PEXELS_API_KEY`. Optionally add `ANTHROPIC_API_KEY` too. Under the **Variables** tab you can set `TRENDS_GEO` (e.g. `IN`), `REELS_PER_DAY` and `HANDLE`.
4. Open **Actions > Daily reels > Run workflow** once to make the first batch. After that it runs every day at 08:00 India time; change the `cron` line in `.github/workflows/daily-reels.yml` for another time.
5. Open your page on your phone and tap **Add to Home Screen**, so it opens like an app. Each reel has Download, Share (straight to Instagram, WhatsApp, YouTube) and copy buttons for the title, caption, hashtags and tags.

The page keeps the last 7 days of reels. To make a reel about your own topic, run the workflow and type the topic in the box.

## Or run it on your computer

1. Install Python 3.10 or newer from python.org (on Windows, tick "Add Python to PATH").
2. Download this `reel-maker` folder to your computer.
3. Double-click **start-windows.bat** (Windows) or **start-mac-linux.command** (Mac/Linux). The first run installs what it needs (including ffmpeg) and opens the app at http://localhost:8765.
4. Press **Make today's reels**.

Without any keys it already works: captions come from today's news headlines and the background is animated. For real video footage, add a free key (next section).

## Settings (`.env` file)

Open `.env` in any text editor:

| Setting | What it does |
|---|---|
| `PEXELS_API_KEY` | Free key from https://www.pexels.com/api/ for real stock footage matching each trend. Recommended. |
| `PIXABAY_API_KEY` | Optional second free footage source. |
| `ANTHROPIC_API_KEY` | Optional. Claude writes a sharper hook, slide captions, title, hashtags and tags. A few cents a day. |
| `TRENDS_GEO` | Country for trends: `US`, `IN`, `GB`, `CA`, `AU`... |
| `REELS_PER_DAY` | How many reels per day (default 3). |
| `DAILY_TIME` | When the app makes new reels each day, e.g. `08:00`. Works while the app window is open. |
| `HANDLE` | Your @handle, shown small on every reel and in the caption. |
| `BLOCKLIST` | Trends with these words are skipped (deaths, crimes, disasters by default) so you don't post about tragedies. |

Restart the app after changing `.env`.

## What you get for each reel

Saved in `output/<date>/<rank>-<topic>/`:
- `reel.mp4`: vertical video, ready for Instagram Reels, YouTube Shorts and TikTok
- `cover.jpg`: thumbnail
- `post.txt`: title, caption, hashtags, tags, video credits and the news links (check the facts before posting)

In the app each reel has **Download video**, **Share** (sends the video to Instagram/WhatsApp etc. from your phone's share menu where the browser supports it), and **Copy title / caption / hashtags / tags** buttons.

## Using it from your phone

The start scripts run with `--lan`, so the terminal also prints an address like `http://192.168.1.20:8765`. Open it on your phone on the same Wi-Fi to watch and download reels there. Phone browsers only allow the Share button on secure (https) pages, so on the Wi-Fi address use Download, then post from your gallery.

## Command line

```
python -m reelmaker make                     # today's trending reels
python -m reelmaker make --geo IN --count 5  # 5 reels from India's trends
python -m reelmaker make --topic "iPhone 18" # a reel about your own topic
python -m reelmaker serve                    # the app
python -m reelmaker site                     # build the phone page into site/
```

## Tips for monetization

- Add trending audio inside Instagram/TikTok when you post. The reels carry silent audio by default so you can pick what's trending that day. To bake in music, put royalty-free tracks (mp3/m4a) in the `music/` folder and one is picked at random.
- Post early: trends peak within hours.
- Footage from Pexels and Pixabay is free for commercial use; credits are listed in `post.txt` anyway.
- Captions built from headlines quote the news, so skim `post.txt` sources before posting.

## Where things come from

- Trends: Google Trends daily trending searches RSS (`trends.google.com/trending/rss`), public and free.
- Video: Pexels and Pixabay APIs (free, royalty-free).
- Font: Inter (SIL Open Font License, see `fonts/`).
