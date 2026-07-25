"""
Two jobs live here:

1. scan_existing(): a one-time recursive walk of the watch directory,
   used at startup to catch files that arrived while the app wasn't running.
2. MediaEventHandler + start_observer(): watchdog-based real-time monitoring
   that enqueues new/modified files as they show up.

Both funnel into the same `queue.Queue`, which a pool of worker threads
(in main.py) drains and hands to the transcriber.
"""

import logging
import os
import queue
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import config

logger = logging.getLogger("watcher")


def is_supported(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in config.SUPPORTED_EXTENSIONS


def is_state_or_transcript_file(path: str, watch_root: str) -> bool:
    """Filter out files the app itself creates, so it never watches its
    own output/state and loops."""
    name = os.path.basename(path)
    if name in (config.STATE_FILENAME, config.LOG_FILENAME):
        return True
    if name.startswith(config.STATE_FILENAME):  # .tmp / .corrupt variants
        return True
    if path.endswith(config.TRANSCRIPT_SUFFIX):
        return True
    return False


def scan_existing(watch_root: str, tracker, work_queue: "queue.Queue", force: bool = False):
    """Recursive walk of watch_root and every subdirectory."""
    found = 0
    for dirpath, _dirnames, filenames in os.walk(watch_root):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if not is_supported(filepath):
                continue
            if is_state_or_transcript_file(filepath, watch_root):
                continue
            if tracker.needs_processing(filepath, force=force):
                work_queue.put(filepath)
                found += 1
    logger.info("Initial scan complete: %d file(s) queued for transcription.",
                found)


def wait_until_stable(filepath: str) -> bool:
    """
    Polls file size until it stops changing for FILE_STABILITY_WINDOW
    seconds, so we don't try to transcribe a file that's still being
    copied/downloaded/recorded. Returns False if the file disappears
    before it stabilizes.
    """
    last_size = -1
    stable_since = None
    while True:
        try:
            size = os.path.getsize(filepath)
        except OSError:
            return False  # file was removed/renamed mid-copy

        now = time.monotonic()
        if size != last_size:
            last_size = size
            stable_since = now
        elif stable_since and (now - stable_since) >= config.FILE_STABILITY_WINDOW:
            return True

        time.sleep(config.STABILITY_POLL_INTERVAL)


class MediaEventHandler(FileSystemEventHandler):
    """
    Watchdog callback handler. We only care about file creation and
    modification (a copy showing up in chunks fires 'modified' repeatedly,
    which is fine — the stability check in the worker absorbs that).
    """

    def __init__(self, watch_root: str, tracker, work_queue: "queue.Queue",
                 force: bool = False):
        self.watch_root = watch_root
        self.tracker = tracker
        self.work_queue = work_queue
        self.force = force

    def _consider(self, path: str):
        if os.path.isdir(path):
            return
        if not is_supported(path):
            return
        if is_state_or_transcript_file(path, self.watch_root):
            return
        if self.tracker.needs_processing(path, force=self.force):
            logger.info("Detected new/changed media file: %s", path)
            self.work_queue.put(path)

    def on_created(self, event):
        self._consider(event.src_path)

    def on_modified(self, event):
        self._consider(event.src_path)

    def on_moved(self, event):
        # e.g. a download tool renaming file.part -> file.mp4 on completion
        self._consider(event.dest_path)


def start_observer(watch_root: str, tracker, work_queue: "queue.Queue",
                   force: bool = False) -> Observer:
    handler = MediaEventHandler(watch_root, tracker, work_queue, force=force)
    observer = Observer()
    observer.schedule(handler, watch_root, recursive=True)
    observer.start()
    logger.info("Real-time monitoring started on: %s", watch_root)
    return observer
