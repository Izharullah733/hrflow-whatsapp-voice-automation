"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from hrbot.audio import Transcriber
from hrbot.config import load_settings
from hrbot.service import process
from hrbot.sheets import sync
from hrbot.storage import Store
from hrbot.whatsapp import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Urdu WhatsApp HR data bot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="Connect to WhatsApp Web and poll allowed chats")
    text = commands.add_parser("process", help="Process a text message locally")
    text.add_argument("text")
    voice = commands.add_parser("transcribe", help="Process an audio file locally")
    voice.add_argument("audio_file", type=Path)
    commands.add_parser("sync", help="Retry Google Sheets synchronization")
    commands.add_parser("records", help="Print local records as JSON")
    args = parser.parse_args()
    settings = load_settings()
    store = Store(settings.db_file)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.command == "run":
            run(settings, store)
        elif args.command == "process":
            print(process(args.text, store, settings))
        elif args.command == "transcribe":
            print(process(Transcriber(settings).transcribe(args.audio_file), store, settings))
        elif args.command == "sync":
            if not settings.sheet_id:
                raise SystemExit("Set GOOGLE_SHEET_ID in .env before syncing")
            records, compensation = sync(store, settings)
            print(f"Synced {records} registrations and {compensation} compensation records")
        elif args.command == "records":
            print(json.dumps(store.records(), ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
