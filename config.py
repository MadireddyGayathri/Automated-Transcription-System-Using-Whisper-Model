"""
Central configuration for the transcription system.
Edit these defaults or override via CLI args in main.py.
"""

# Media extensions we care about (lowercase, with dot)
SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".mp4", ".mkv", ".mov", ".flv", ".aac", ".m4a"
}

# Whisper model size: tiny, base, small, medium, large, large-v2, large-v3
# Bigger = more accurate but slower / more RAM+VRAM.
DEFAULT_MODEL_SIZE = "base"

# Language hint for Whisper. None = auto-detect (slower, but flexible).
DEFAULT_LANGUAGE = None

# Name of the state file that tracks processed files (stored at the root
# of the watched directory so it survives restarts).
STATE_FILENAME = ".transcription_state.json"

# How long (seconds) a file's size must stay unchanged before we consider
# it "done being written" and safe to transcribe. Prevents grabbing a
# video that's still mid-copy/mid-download.
FILE_STABILITY_WINDOW = 5

# How often (seconds) the stability checker polls a pending file.
STABILITY_POLL_INTERVAL = 2

# Output transcript file suffix (saved next to the source file).
TRANSCRIPT_SUFFIX = ".txt"

# Number of worker threads consuming the transcription queue.
# Whisper itself is not thread-safe for concurrent inference on one model
# instance, so keep this at 1 unless you load one model per worker.
NUM_WORKERS = 1

# Log file (in addition to console output), stored at the watch root.
LOG_FILENAME = ".transcription.log"
