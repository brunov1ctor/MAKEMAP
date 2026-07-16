"""Audio processing utilities — trim/loop sounds to 30s with crossfade."""

from __future__ import annotations

import shutil
import struct
import wave
from pathlib import Path

MAX_SOUND_DURATION_S = 30
FADE_DURATION_S = 1.5


def process_sound_file(src: Path, dest: Path):
    """Trim to 30s or loop short sounds with crossfade to fill 30s."""
    try:
        import subprocess
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        _process_with_ffmpeg(src, dest)
    except (FileNotFoundError, OSError, Exception):
        if src.suffix.lower() == ".wav":
            _process_wav_pure(src, dest)
        else:
            shutil.copy2(src, dest)


def _process_with_ffmpeg(src: Path, dest: Path):
    import subprocess
    tmp_wav = dest.with_suffix(".tmp.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", "44100", "-ac", "2", str(tmp_wav)],
        capture_output=True, check=True,
    )
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(tmp_wav)],
        capture_output=True, text=True,
    )
    duration = float(result.stdout.strip())

    if duration >= MAX_SOUND_DURATION_S:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp_wav), "-t", str(MAX_SOUND_DURATION_S),
             "-af", f"afade=t=out:st={MAX_SOUND_DURATION_S - FADE_DURATION_S}:d={FADE_DURATION_S}",
             str(dest)], capture_output=True, check=True)
    else:
        loops = int(MAX_SOUND_DURATION_S / duration) + 1
        subprocess.run(
            ["ffmpeg", "-y", "-stream_loop", str(loops - 1), "-i", str(tmp_wav),
             "-t", str(MAX_SOUND_DURATION_S),
             "-af", f"afade=t=out:st={MAX_SOUND_DURATION_S - FADE_DURATION_S}:d={FADE_DURATION_S}",
             str(dest)], capture_output=True, check=True)
    tmp_wav.unlink(missing_ok=True)


def _process_wav_pure(src: Path, dest: Path):
    """Pure Python wav: trim/loop to 30s with crossfade."""
    with wave.open(str(src), 'rb') as wf:
        n_ch = wf.getnchannels()
        sw = wf.getsampwidth()
        fr = wf.getframerate()
        nf = wf.getnframes()
        raw = wf.readframes(nf)

    if sw != 2:
        shutil.copy2(src, dest)
        return

    samples = list(struct.unpack(f"<{nf * n_ch}h", raw))
    duration = nf / fr
    target_frames = int(MAX_SOUND_DURATION_S * fr)
    fade_frames = int(FADE_DURATION_S * fr)

    if duration >= MAX_SOUND_DURATION_S:
        samples = samples[:target_frames * n_ch]
        fs = (target_frames - fade_frames) * n_ch
        for i in range(fs, len(samples)):
            samples[i] = int(samples[i] * (1.0 - (i - fs) / (fade_frames * n_ch)))
    else:
        src_s = list(samples)
        result = list(src_s)
        cf_len = fade_frames * n_ch
        while len(result) < target_frames * n_ch:
            if cf_len > len(src_s):
                cf_len = len(src_s) // 2
            start = len(result) - cf_len
            for i in range(cf_len):
                p = i / cf_len
                result[start + i] = int(result[start + i] * (1.0 - p) + src_s[i] * p)
            result.extend(src_s[cf_len:])
        samples = result[:target_frames * n_ch]
        fs = (target_frames - fade_frames) * n_ch
        for i in range(fs, len(samples)):
            samples[i] = int(samples[i] * (1.0 - (i - fs) / (fade_frames * n_ch)))

    samples = [max(-32768, min(32767, s)) for s in samples]
    packed = struct.pack(f"<{len(samples)}h", *samples)
    with wave.open(str(dest), 'wb') as wf:
        wf.setnchannels(n_ch)
        wf.setsampwidth(sw)
        wf.setframerate(fr)
        wf.writeframes(packed)
