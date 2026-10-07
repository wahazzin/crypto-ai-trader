"""
yt_learn.py -- pull a YouTube channel's (or one video's) transcripts as text, so Claude can study them.
Usage: python tools/yt_learn.py <channel-or-video-url> [out_dir]
Writes <out_dir>/<channel>/<NN>_<video_id>.md (title, date, length, url, transcript) + index.md.
Shared research tool for all three trading projects. Transcripts are the creator's words: notes, not evidence.
"""
import json
import os
import re
import subprocess
import sys


def videos(url):
    if "watch?v=" in url or "youtu.be/" in url:
        cmd = [sys.executable, "-m", "yt_dlp", "-J", "--skip-download", url]
        js = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
        return js.get("uploader") or "single", [js]
    if not url.rstrip("/").endswith(("/videos", "/streams", "/shorts")):
        url = url.rstrip("/") + "/videos"
    cmd = [sys.executable, "-m", "yt_dlp", "-J", "--flat-playlist", url]
    js = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    return js.get("channel") or js.get("uploader") or "channel", js.get("entries", [])


def transcript(vid):
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    try:
        tr = api.fetch(vid, languages=["en", "en-US", "en-GB"])
    except Exception:
        tl = api.list(vid)
        tr = next(iter(tl)).fetch()
    return " ".join(s.text.replace("\n", " ") for s in tr)


def main(url, out="research/out/youtube"):
    name, entries = videos(url)
    d = os.path.join(out, re.sub(r"[^A-Za-z0-9_-]+", "_", name))
    os.makedirs(d, exist_ok=True)
    idx = [f"# {name}: {len(entries)} videos", "", "| # | Title | Length | Transcript |", "|---|---|---|---|"]
    for i, e in enumerate(reversed(entries), 1):                      # oldest first = watch order
        vid, title = e["id"], e.get("title", "")
        mins = round((e.get("duration") or 0) / 60)
        try:
            text, ok = transcript(vid), "ok"
        except Exception as ex:
            text, ok = "", f"FAILED: {type(ex).__name__}: {str(ex)[:150]}"
        with open(os.path.join(d, f"{i:02d}_{vid}.md"), "w") as f:
            f.write(f"# {title}\n\nhttps://www.youtube.com/watch?v={vid} · {mins} min · views {e.get('view_count')}\n\n{text}\n")
        idx.append(f"| {i} | {title} | {mins} min | {ok if ok != 'ok' else f'{len(text.split()):,} words'} |")
        print(i, vid, title[:60], ok if ok != "ok" else len(text.split()), flush=True)
    with open(os.path.join(d, "index.md"), "w") as f:
        f.write("\n".join(idx) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
