"""
Thin wrapper around openai-whisper so the rest of the app doesn't care
about model-loading details.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("transcriber")


class WhisperTranscriber:
    def __init__(self, model_size: str = "base", language: str | None = None):
        # Imported lazily so the rest of the codebase (tracker, watcher,
        # CLI --help, etc.) doesn't require whisper/torch to be installed
        # just to be imported/tested.
        import whisper  # noqa: WPS433

        logger.info("Loading Whisper model '%s' (this can take a while the "
                    "first time as it downloads weights)...", model_size)
        self.model = whisper.load_model(model_size)
        self.language = language
        logger.info("Model loaded.")

    def transcribe(self, filepath: str) -> str:
        """
        Returns the transcript text. Raises on failure so callers can
        record it via FileTracker.mark_failed.
        """
        result = self.model.transcribe(
            filepath,
            language=self.language,
            verbose=False,
        )
        return result.get("text", "").strip()
