"""Rewind: keep a rolling recording of chosen cameras so you can scrub back.

Camera servers keep only their last few chunks (10-60 seconds), so there is
nothing to rewind into on their side. Instead, while the map is open, you can
tell ACE to keep a camera: it then records that camera into
data/recordings/<camera>/ on your own computer, keeping only the last 30 or
60 minutes (older video is deleted as new video arrives). The map's viewer
can then play any moment in that window.

Ground rules, built in:
  - nothing is recorded unless you switch it on for a camera;
  - at most MAX_MINUTES are kept, on your computer only, never uploaded;
  - a recording is deleted when you stop it or quit the map, and any left
    over from a crash are deleted the next time the map starts;
  - only live video from camera servers (HLS, MJPEG); YouTube is never
    recorded, and no more than MAX_CAMERAS cameras at once.
Recorded video is for looking back at traffic, like the rest of ACE: not for
identifying or following people, and not for publishing.

Needs ffmpeg: either on your PATH, or `pip install imageio-ffmpeg`, which
brings its own copy. HLS is copied as it arrives (no re-encoding, so it uses
almost no CPU). MJPEG is converted to H.264 so the browser can seek in it.
Storage: about 0.5-1 GB per camera per half hour at 1080p.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

RECORDINGS = Path("data/recordings")
MAX_MINUTES = 60
MAX_CAMERAS = 4
CHUNK_S = 4  # length of the recorded chunks for MJPEG (HLS keeps its own)


def ffmpeg_path() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def folder_name(camera_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", camera_id)[:100]


class _Recording:
    def __init__(self, cam: dict, minutes: int, ffmpeg: str):
        self.cam, self.minutes, self.ffmpeg = cam, minutes, ffmpeg
        self.folder = RECORDINGS / folder_name(cam["id"])
        self.started = time.time()
        self.proc: subprocess.Popen | None = None
        self.launched = 0.0
        self.restarts = 0
        self.quick_fails = 0
        self.last_error = ""
        self.stopped = False

    def command(self) -> list[str]:
        q = self.cam.get("q") or {}
        url = self.cam["stream_url"]
        out = self.folder / "index.m3u8"
        segs = str(self.folder / "seg_%07d.ts")
        common_in = ["-nostdin", "-loglevel", "error", "-rw_timeout", "15000000"]
        if (q.get("kind") or "") == "mjpeg" or self.cam.get("url_type") == "stream":
            chunk = CHUNK_S
            source = ["-f", "mpjpeg", "-i", url]
            # MJPEG pictures carry no times; stamp each with the moment it arrived.
            video = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-pix_fmt", "yuv420p",
                     "-vf", "setpts=(RTCTIME-RTCSTART)/(TB*1000000),scale=trunc(iw/2)*2:trunc(ih/2)*2",
                     "-fps_mode", "vfr",
                     "-force_key_frames", f"expr:gte(t,n_forced*{chunk})"]
        else:
            chunk = max(2, float(q.get("segment_s") or 6))
            source = ["-i", url]
            video = ["-map", "0:v:0", "-an", "-c:v", "copy"]
        keep = max(3, math.ceil(self.minutes * 60 / chunk))
        return [self.ffmpeg, *common_in, *source, *video,
                "-f", "hls", "-hls_time", str(int(chunk)), "-hls_list_size", str(keep),
                # append_list: a restart (cameras drop their connection now and then) adds to
                # the recording instead of starting it again; discont_start marks the join.
                "-hls_flags", "delete_segments+program_date_time+omit_endlist+independent_segments"
                              "+append_list+discont_start",
                "-hls_segment_filename", segs, str(out)]

    def start(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "meta.json").write_text(json.dumps({
            "id": self.cam["id"], "minutes": self.minutes, "started": self.started,
            "stream_url": self.cam["stream_url"]}), encoding="utf-8")
        self.launched = time.time()
        # ffmpeg shares the map's terminal, so Ctrl+C or closing that window
        # stops it along with the map.
        self.proc = subprocess.Popen(self.command(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)

    def check(self) -> None:
        """Reconnect when the camera drops the connection. Some servers end
        every viewer's stream after half a minute or so: reconnect at once.
        A camera that keeps failing straight away gets longer pauses."""
        if self.stopped or not self.proc or self.proc.poll() is None:
            return
        err = (self.proc.stderr.read() or b"").decode("utf-8", "ignore").strip() if self.proc.stderr else ""
        self.last_error = err.splitlines()[-1][:200] if err else ""
        self.restarts += 1
        self.quick_fails = 0 if time.time() - self.launched > 20 else self.quick_fails + 1
        time.sleep(1 if not self.quick_fails else min(60, 2 ** min(self.quick_fails, 6)))
        if not self.stopped:
            self.start()

    def stop(self) -> None:
        self.stopped = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.folder, ignore_errors=True)

    def status(self) -> dict:
        playlist = self.folder / "index.m3u8"
        kept = 0.0
        if playlist.exists():
            kept = sum(float(x) for x in re.findall(r"#EXTINF:([\d.]+)",
                                                     playlist.read_text(encoding="utf-8", errors="ignore")))
        return {"id": self.cam["id"], "minutes": self.minutes, "started": self.started,
                "kept_s": round(kept), "playlist": f"recordings/{folder_name(self.cam['id'])}/index.m3u8",
                "running": bool(self.proc and self.proc.poll() is None), "restarts": self.restarts,
                "error": self.last_error}


class Recorder:
    """Keeps the recordings the map asks for. Thread-safe."""

    def __init__(self, cameras: dict[str, dict]):
        self.cameras = cameras
        self.ffmpeg = ffmpeg_path()
        self.lock = threading.Lock()
        self.active: dict[str, _Recording] = {}
        shutil.rmtree(RECORDINGS, ignore_errors=True)  # leftovers from a crash
        self._watch = threading.Thread(target=self._watchdog, daemon=True)
        self._watch.start()

    def _watchdog(self) -> None:
        while True:
            time.sleep(3)
            with self.lock:
                recs = list(self.active.values())
            for rec in recs:
                rec.check()

    def start(self, camera_id: str, minutes: int) -> dict:
        if not self.ffmpeg:
            return {"error": "Rewind needs ffmpeg. Run: pip install imageio-ffmpeg  (then restart the map)"}
        cam = self.cameras.get(camera_id)
        if not cam or cam.get("url_type") not in ("hls", "stream"):
            return {"error": "Only live video cameras (HLS or MJPEG) can be kept"}
        minutes = max(5, min(int(minutes or 30), MAX_MINUTES))
        with self.lock:
            if camera_id in self.active:
                return self.active[camera_id].status()
            if len(self.active) >= MAX_CAMERAS:
                return {"error": f"Already keeping {MAX_CAMERAS} cameras; stop one first"}
            rec = _Recording(cam, minutes, self.ffmpeg)
            rec.start()
            self.active[camera_id] = rec
            return rec.status()

    def stop(self, camera_id: str) -> dict:
        with self.lock:
            rec = self.active.pop(camera_id, None)
        if rec:
            rec.stop()
        return {"stopped": camera_id}

    def stop_all(self) -> None:
        with self.lock:
            recs = list(self.active.values())
            self.active.clear()
        for rec in recs:
            rec.stop()
        shutil.rmtree(RECORDINGS, ignore_errors=True)

    def status(self) -> dict:
        with self.lock:
            recs = [r.status() for r in self.active.values()]
        return {"ffmpeg": bool(self.ffmpeg), "max_cameras": MAX_CAMERAS, "max_minutes": MAX_MINUTES,
                "recordings": recs}
