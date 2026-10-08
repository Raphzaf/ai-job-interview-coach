"""Logging setup.

Logs are meant for developers: they record what the pipeline did (sizes,
timings, provider errors) but never document contents or API keys, because CVs
contain personal data.
"""

import logging

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level.upper(), format=_FORMAT)
    # Third-party libraries are very chatty at INFO level (HTTP calls, model loading).
    for noisy in ("httpx", "httpcore", "urllib3", "sentence_transformers", "openai", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
