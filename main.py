#!/usr/bin/env python3
"""
Automated Transcription System (Whisper-based)

Usage:
    python main.py /path/to/media/folder
    python main.py /path/to/media/folder --model small --language en

Behavior:
  1. Recursively scans the folder for audio/video files.
  2. Transcribes each with OpenAI Whisper, saving <file>.txt next to it.
  3. Keeps watching the folder (and subfolders) in real time; new files
     are transcribed automatically as they appear.
  4. A state file (.transcription_state.json in the watch root) tracks
     progress so already-done files are skipped and a crash/restart
     resumes instead of starting over.

"""

import argparse
import logging
import os
import queue
import signal
import sys
import threading

import config
from file_tracker import FileTracker
from transcriber import WhisperTranscriber
from watcher import scan_existing, start_observer, wait_until_stable

logger = logging.getLogger("main")

shutdown_event = threading.Event()


def setup_logging(watch_root: str):
    log_path = os.path.join(watch_root, config.LOG_FILENAME)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def worker_loop(work_queue: "queue.Queue", tracker: FileTracker,
                 transcriber: WhisperTranscriber):
    while not shutdown_event.is_set():
        try:
            filepath = work_queue.get(timeout=1)
        except queue.Empty:
            continue

        try:
            if not os.path.exists(filepath):
                logger.warning("Skipping (no longer exists): %s", filepath)
                continue

            # Don't grab a file mid-copy/mid-recording.
            if not wait_until_stable(filepath):
                logger.warning("File disappeared before stabilizing: %s",
                                filepath)
                continue

            # Re-check: another trigger (e.g. both the initial scan and a
            # watchdog event) may have already queued/finished this file.
            if not tracker.needs_processing(filepath):
                continue

            tracker.mark_in_progress(filepath)
            logger.info("Transcribing: %s", filepath)

            text = transcriber.transcribe(filepath)

            transcript_path = os.path.splitext(filepath)[0] + config.TRANSCRIPT_SUFFIX
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(text)

            tracker.mark_done(filepath, transcript_path)
            logger.info("Done -> %s", transcript_path)

        except Exception as exc:  # noqa: BLE001 - keep worker alive
            logger.exception("Failed to transcribe %s", filepath)
            tracker.mark_failed(filepath, str(exc))
        finally:
            work_queue.task_done()


def main():
    parser = argparse.ArgumentParser(description="Automated Whisper transcription "
                                                   "system with real-time folder "
                                                   "monitoring.")
    parser.add_argument("directory", help="Root folder to scan and watch "
                                           "(recursively).")
    parser.add_argument("--model", default=config.DEFAULT_MODEL_SIZE,
                         help=f"Whisper model size (default: "
                              f"{config.DEFAULT_MODEL_SIZE}). One of tiny, "
                              f"base, small, medium, large, large-v2, large-v3.")
    parser.add_argument("--language", default=config.DEFAULT_LANGUAGE,
                         help="Language code (e.g. 'en'). Omit to auto-detect.")
    parser.add_argument("--no-watch", action="store_true",
                         help="Run the initial scan only, then exit "
                              "(no real-time monitoring).")
    args = parser.parse_args()

    watch_root = os.path.abspath(args.directory)
    if not os.path.isdir(watch_root):
        print(f"Error: '{watch_root}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    setup_logging(watch_root)

    state_path = os.path.join(watch_root, config.STATE_FILENAME)
    tracker = FileTracker(state_path)

    # Files marked 'in_progress' from a previous run that never finished
    # (crash / kill -9) need to be requeued, not silently dropped.
    stale = tracker.resume_candidates()
    if stale:
        logger.info("Resuming %d file(s) interrupted by a previous shutdown.",
                    len(stale))

    logger.info("Loading Whisper model (model='%s')...", args.model)
    transcriber = WhisperTranscriber(model_size=args.model, language=args.language)

    work_queue: "queue.Queue[str]" = queue.Queue()
    for filepath in stale:
        work_queue.put(filepath)

    scan_existing(watch_root, tracker, work_queue)

    workers = []
    for i in range(config.NUM_WORKERS):
        t = threading.Thread(target=worker_loop, args=(work_queue, tracker, transcriber),
                              name=f"worker-{i}", daemon=True)
        t.start()
        workers.append(t)

    observer = None
    if not args.no_watch:
        observer = start_observer(watch_root, tracker, work_queue)

    def handle_sigint(_signum, _frame):
        logger.info("Shutdown requested (Ctrl+C). Finishing current file, "
                    "then exiting...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        if args.no_watch:
            work_queue.join()
        else:
            while not shutdown_event.is_set():
                shutdown_event.wait(timeout=1)
    finally:
        if observer:
            observer.stop()
            observer.join()
        shutdown_event.set()
        for t in workers:
            t.join(timeout=5)
        stats = tracker.stats()
        logger.info("Final stats: %s", stats)
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
