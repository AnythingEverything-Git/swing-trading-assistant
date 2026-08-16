"""Logging helpers and configuration.

Provides a centralized place for logging configuration; implementation can be
expanded later.
"""
import logging


def configure_logging():
    logging.basicConfig(level=logging.INFO)
