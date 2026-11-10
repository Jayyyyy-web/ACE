"""Read a video chunk's real picture size, codec and frame count, with no
video library: just enough MPEG-TS, MP4 and H.264/H.265 parsing to find the
stream's sequence parameter set (SPS), which states the picture size.

HLS playlists often don't say how big their picture is, so the scanner
downloads one chunk and asks this module.

    info = chunk_info(segment_bytes, init_bytes)   # init only for fMP4 streams
    # {"codec": "h264", "width": 1920, "height": 1080, "frames": 60}
"""

from __future__ import annotations

import struct

# MPEG-TS stream types for video.
_TS_VIDEO = {0x1B: "h264", 0x24: "hevc", 0x02: "mpeg2", 0x10: "mpeg4"}


# --------------------------------------------------------------------------
# Bit reading (exp-Golomb, as H.264 and H.265 use)
# --------------------------------------------------------------------------

class _Bits:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def u(self, n: int) -> int:
        value = 0
        for _ in range(n):
            byte = self.data[self.pos >> 3]  # IndexError ends parsing of a truncated SPS
            value = (value << 1) | ((byte >> (7 - (self.pos & 7))) & 1)
            self.pos += 1
        return value

    def ue(self) -> int:
        zeros = 0
        while self.u(1) == 0:
            zeros += 1
            if zeros > 31:
                raise ValueError("bad exp-Golomb code")
        return (1 << zeros) - 1 + self.u(zeros)

    def se(self) -> int:
        k = self.ue()
        return (k + 1) // 2 if k % 2 else -(k // 2)


def _unescape(nal: bytes) -> bytes:
    """Drop emulation-prevention bytes (00 00 03 -> 00 00)."""
    return nal.replace(b"\x00\x00\x03", b"\x00\x00")


def _nal_units(es: bytes):
    """Split an Annex-B byte stream on 00 00 01 start codes."""
    starts, i = [], es.find(b"\x00\x00\x01")
    while i != -1:
        starts.append(i + 3)
        i = es.find(b"\x00\x00\x01", i + 3)
    for n, s in enumerate(starts):
        end = starts[n + 1] - 3 if n + 1 < len(starts) else len(es)
        yield es[s:end].rstrip(b"\x00")


# --------------------------------------------------------------------------
# SPS parsing
# --------------------------------------------------------------------------

def _skip_scaling_list(b: _Bits, size: int) -> None:
    last, nxt = 8, 8
    for _ in range(size):
        if nxt:
            nxt = (last + b.se() + 256) % 256
        last = nxt or last


def h264_sps_size(nal: bytes) -> tuple[int, int] | None:
    """Picture size from an H.264 SPS NAL unit (header byte included)."""
    try:
        b = _Bits(_unescape(nal[1:]))
        profile = b.u(8)
        b.u(16)  # constraint flags, level
        b.ue()   # seq_parameter_set_id
        chroma = 1
        if profile in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135):
            chroma = b.ue()
            if chroma == 3:
                b.u(1)
            b.ue(), b.ue()  # bit depths
            b.u(1)
            if b.u(1):  # scaling matrices
                for i in range(8 if chroma != 3 else 12):
                    if b.u(1):
                        _skip_scaling_list(b, 16 if i < 6 else 64)
        b.ue()  # log2_max_frame_num_minus4
        poc_type = b.ue()
        if poc_type == 0:
            b.ue()
        elif poc_type == 1:
            b.u(1)
            b.se(), b.se()
            for _ in range(b.ue()):
                b.se()
        b.ue()   # max_num_ref_frames
        b.u(1)
        width_mbs = b.ue() + 1
        height_units = b.ue() + 1
        frame_mbs_only = b.u(1)
        if not frame_mbs_only:
            b.u(1)
        b.u(1)
        crop = (0, 0, 0, 0)
        if b.u(1):
            crop = (b.ue(), b.ue(), b.ue(), b.ue())
        unit_x = 1 if chroma in (0, 3) else 2
        unit_y = (2 - frame_mbs_only) * (2 if chroma == 1 else 1)
        width = width_mbs * 16 - unit_x * (crop[0] + crop[1])
        height = (2 - frame_mbs_only) * height_units * 16 - unit_y * (crop[2] + crop[3])
        return (width, height) if width > 0 and height > 0 else None
    except (IndexError, ValueError):
        return None


def hevc_sps_size(nal: bytes) -> tuple[int, int] | None:
    """Picture size from an H.265 SPS NAL unit (2-byte header included)."""
    try:
        b = _Bits(_unescape(nal[2:]))
        b.u(4)
        sub_layers = b.u(3)
        b.u(1)
        b.u(96)  # general profile_tier_level (2+1+5+32+4+43+1 bits) and level (8)
        present = [(b.u(1), b.u(1)) for _ in range(sub_layers)]
        if sub_layers:
            b.u(2 * (8 - sub_layers))
        for profile_present, level_present in present:
            b.u(88 if profile_present else 0)
            b.u(8 if level_present else 0)
        b.ue()  # sps_seq_parameter_set_id
        chroma = b.ue()
        if chroma == 3:
            b.u(1)
        width, height = b.ue(), b.ue()
        if b.u(1):  # conformance window
            left, right, top, bottom = b.ue(), b.ue(), b.ue(), b.ue()
            sub_w = 2 if chroma in (1, 2) else 1
            sub_h = 2 if chroma == 1 else 1
            width -= sub_w * (left + right)
            height -= sub_h * (top + bottom)
        return (width, height) if width > 0 and height > 0 else None
    except (IndexError, ValueError):
        return None


def _size_from_es(es: bytes, codec: str) -> tuple[int, int] | None:
    for nal in _nal_units(es):
        if not nal:
            continue
        if codec == "h264" and nal[0] & 0x1F == 7:
            size = h264_sps_size(nal)
        elif codec == "hevc" and len(nal) > 2 and (nal[0] >> 1) & 0x3F == 33:
            size = hevc_sps_size(nal)
        else:
            continue
        if size:
            return size
    return None


# --------------------------------------------------------------------------
# MPEG-TS
# --------------------------------------------------------------------------

def _ts_packets(data: bytes):
    start = data.find(b"\x47")
    while start != -1 and start + 188 < len(data) and data[start + 188] != 0x47:
        start = data.find(b"\x47", start + 1)
    if start == -1:
        return
    for i in range(start, len(data) - 187, 188):
        pkt = data[i:i + 188]
        if pkt[0] != 0x47:
            continue
        pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
        unit_start = bool(pkt[1] & 0x40)
        control = (pkt[3] >> 4) & 3
        offset = 4
        if control in (2, 3):
            offset += 1 + pkt[4]
        if control in (1, 3) and offset < 188:
            yield pid, unit_start, pkt[offset:]


def ts_info(data: bytes) -> dict:
    pmt_pids, video_pid, codec = set(), None, None
    es, frames = bytearray(), 0
    for pid, unit_start, payload in _ts_packets(data):
        if pid == 0 and unit_start and len(payload) > 8:
            section = payload[1 + payload[0]:]
            length = ((section[1] & 0x0F) << 8) | section[2]
            for j in range(8, min(3 + length - 4, len(section) - 3), 4):
                program = (section[j] << 8) | section[j + 1]
                if program:
                    pmt_pids.add(((section[j + 2] & 0x1F) << 8) | section[j + 3])
        elif pid in pmt_pids and unit_start and video_pid is None and len(payload) > 12:
            section = payload[1 + payload[0]:]
            length = ((section[1] & 0x0F) << 8) | section[2]
            info_len = ((section[10] & 0x0F) << 8) | section[11]
            j, end = 12 + info_len, min(3 + length - 4, len(section))
            while j + 5 <= end:
                stype = section[j]
                epid = ((section[j + 1] & 0x1F) << 8) | section[j + 2]
                es_len = ((section[j + 3] & 0x0F) << 8) | section[j + 4]
                if stype in _TS_VIDEO and video_pid is None:
                    video_pid, codec = epid, _TS_VIDEO[stype]
                j += 5 + es_len
        elif pid == video_pid:
            if unit_start and payload[:3] == b"\x00\x00\x01":
                frames += 1
                payload = payload[9 + payload[8]:] if len(payload) > 9 else b""
            if len(es) < 600_000:
                es += payload
    size = _size_from_es(bytes(es), codec) if codec in ("h264", "hevc") else None
    return {"codec": codec, "width": size and size[0], "height": size and size[1],
            "frames": frames or None}


# --------------------------------------------------------------------------
# MP4 (fragmented, as CMAF/fMP4 HLS uses)
# --------------------------------------------------------------------------

_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"moof", b"traf", b"mvex"}


def _boxes(data: bytes, start: int = 0, end: int | None = None):
    end = len(data) if end is None else end
    i = start
    while i + 8 <= end:
        size, kind = struct.unpack(">I4s", data[i:i + 8])
        header = 8
        if size == 1 and i + 16 <= end:
            size, header = struct.unpack(">Q", data[i + 8:i + 16])[0], 16
        elif size == 0:
            size = end - i
        if size < header:
            return
        yield kind, i + header, min(i + size, end)
        i += size


def mp4_info(data: bytes) -> dict:
    codec, size, samples = None, None, 0

    def walk(start, end):
        nonlocal codec, size, samples
        for kind, body, stop in _boxes(data, start, end):
            if kind in _CONTAINERS:
                walk(body, stop)
            elif kind == b"stsd" and stop - body > 16:
                entry = data[body + 8:stop]  # skip version/flags and entry count
                fourcc = entry[4:8]
                if fourcc in (b"avc1", b"avc3", b"hvc1", b"hev1") and len(entry) > 36:
                    codec = "h264" if fourcc.startswith(b"avc") else "hevc"
                    w, h = struct.unpack(">HH", entry[32:36])
                    if w and h:
                        size = (w, h)
            elif kind == b"trun" and stop - body >= 8:
                samples += struct.unpack(">I", data[body + 4:body + 8])[0]

    walk(0, len(data))
    return {"codec": codec, "width": size and size[0], "height": size and size[1],
            "frames": samples or None}


def chunk_info(segment: bytes, init: bytes = b"") -> dict:
    """Codec, picture size and number of frames in one HLS chunk.
    Values that can't be read come back as None."""
    if segment[:1] == b"\x47" or segment[188:189] == b"\x47":
        return ts_info(segment)
    return mp4_info(init + segment)
