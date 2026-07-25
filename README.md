# Automated Transcription System Using Whisper

A lightweight Python system that watches a folder and automatically transcribes supported audio and video files with OpenAI Whisper.

## What it does

- Recursively scans a root directory for media files (`.mp3`, `.wav`, `.mp4`, `.mkv`, `.mov`, `.flv`, `.aac`, `.m4a`).
- Transcribes each file using Whisper and saves the result as a `.txt` file next to the original media.
- Watches the directory in real time and processes new or changed files automatically.
- Stores progress in `.transcription_state.json`, so completed files are skipped and interrupted work resumes after restart.

## Files

- `main.py`: Entry point, CLI, worker coordination, folder scanning, watcher startup, and graceful shutdown.
- `transcriber.py`: Loads the Whisper model and exposes a `transcribe()` method.
- `watcher.py`: Scans existing files, monitors filesystem changes, and enqueues media files for transcription.
- `file_tracker.py`: Persists file processing state and decides whether files need transcription.
- `config.py`: Shared defaults for supported extensions, model settings, stability timing, and output names.
- `requirements.txt`: External dependencies needed by the project.

## Requirements

- Python 3.10+ (recommended)
- `openai-whisper`
- `watchdog`

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Usage

Run the watcher and transcribe files in a folder:

```bash
python main.py "C:\path\to\media\folder"
```

Optional arguments:

- `--model`: Whisper model size (`tiny`, `base`, `small`, `medium`, `large`, `large-v2`, `large-v3`). Default: `base`.
- `--language`: Language code (e.g. `en`). Omit to auto-detect.
- `--no-watch`: Run only the initial scan and exit.

Example:

```bash
python main.py "C:\Users\GAYATHRI\OneDrive\Desktop\transcriptionSystem" --model small --language en
```

## Output

- Transcript files are written next to each media file with the `.txt` suffix.
- Logs are written to `.transcription.log` in the watched root.
- Processing state is saved in `.transcription_state.json`.

## Notes

- The app waits until files are stable before transcribing, to avoid processing partially copied/recorded files.
- Only one worker thread is enabled by default because Whisper model inference is not thread-safe on one loaded model instance.
