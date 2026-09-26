"""WhatsApp Web adapter. DOM selectors may need adjustment after WhatsApp updates."""

from __future__ import annotations

import hashlib
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .audio import Transcriber
from .config import Settings
from .service import process
from .storage import Store


log = logging.getLogger(__name__)


@dataclass
class Incoming:
    message_id: str
    text: str
    voice: bool = False
    bubble: object | None = None


class WhatsAppWeb:
    def __init__(self, settings: Settings):
        from selenium import webdriver

        settings.chrome_profile.mkdir(parents=True, exist_ok=True)
        self.download_dir = settings.data_dir / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        options = webdriver.ChromeOptions()
        options.add_argument(f"--user-data-dir={settings.chrome_profile}")
        options.add_argument("--disable-notifications")
        options.add_experimental_option("prefs", {
            "download.default_directory": str(self.download_dir),
            "download.prompt_for_download": False,
        })
        self.driver = webdriver.Chrome(options=options)
        self.settings = settings
        self.driver.get("https://web.whatsapp.com/")

    def wait_for_login(self) -> None:
        from selenium.webdriver.common.by import By

        log.info("Waiting for WhatsApp Web login in the bot Chrome window")
        while True:
            if self.driver.find_elements(By.CSS_SELECTOR, "#pane-side"):
                log.info("WhatsApp Web login detected")
                return
            time.sleep(5)

    def open_chat(self, number: str) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        self.driver.get(f"https://web.whatsapp.com/send?phone={number}")
        WebDriverWait(self.driver, 40).until(EC.presence_of_element_located((By.CSS_SELECTOR, "footer [contenteditable='true']")))

    def _direction(self, bubble) -> str | None:
        """Read message alignment within its row; never guess from the page midpoint.

        Long outgoing bubbles can begin left of the chat midpoint. WhatsApp also
        omits tail markers on consecutive bubbles, so an absent tail is not an
        incoming marker. Ambiguous layout is deliberately ignored.
        """
        return self.driver.execute_script("""
            const bubble = arguments[0];
            if (bubble.querySelector('[data-testid="tail-out"]')) return 'out';
            if (bubble.querySelector('[data-testid="tail-in"]')) return 'in';
            const row = bubble.closest('.focusable-list-item');
            if (!row) return null;
            const item = bubble.getBoundingClientRect();
            const bounds = row.getBoundingClientRect();
            const left = item.left - bounds.left;
            const right = bounds.right - item.right;
            if (Math.abs(left - right) < 24) return null;
            return left < right ? 'in' : 'out';
        """, bubble)

    def incoming(self) -> list[Incoming]:
        from selenium.webdriver.common.by import By

        messages = []
        seen_keys: dict[str, int] = {}
        for bubble in self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='msg-container']")[-40:]:
            if self._direction(bubble) != "in":
                continue
            spans = bubble.find_elements(By.CSS_SELECTOR, "span.selectable-text")
            text = " ".join(span.text for span in spans if span.text).strip()
            pre_nodes = bubble.find_elements(By.CSS_SELECTOR, "[data-pre-plain-text]")
            pre = pre_nodes[0].get_attribute("data-pre-plain-text") if pre_nodes else ""
            meta_nodes = bubble.find_elements(By.CSS_SELECTOR, "[data-testid='msg-meta']")
            meta = meta_nodes[0].text if meta_nodes else ""
            identity = pre + "\n" + text if text else pre + "\n" + text + "\n" + meta
            duplicate_index = seen_keys.get(identity, 0)
            seen_keys[identity] = duplicate_index + 1
            message_id = hashlib.sha256(f"{identity}\n{duplicate_index}".encode()).hexdigest()
            voice = not text and bool(bubble.find_elements(By.CSS_SELECTOR, "[data-icon='ptt-status'], button[aria-label*='voice message']"))
            if text or voice:
                messages.append(Incoming(message_id, text, voice, bubble if voice else None))
        return messages

    def _audio(self, bubble) -> bytes | None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.support.ui import WebDriverWait

        before = {path.name for path in self.download_dir.iterdir()}
        ActionChains(self.driver).move_to_element(bubble).perform()
        menu_icon = WebDriverWait(bubble, 5).until(
            lambda node: node.find_element(By.CSS_SELECTOR, "[data-testid='icon-down-context']")
        )
        self.driver.execute_script("arguments[0].click()", menu_icon)
        download = WebDriverWait(self.driver, 5).until(
            lambda driver: next((item for item in driver.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if item.text.strip() == "Download"), None)
        )
        download.click()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            ready = [path for path in self.download_dir.iterdir()
                     if path.name not in before and path.suffix.lower() not in {".tmp", ".crdownload"}]
            if ready:
                path = max(ready, key=lambda item: item.stat().st_mtime)
                if path.parent.resolve() != self.download_dir.resolve():
                    raise ValueError("Download escaped the configured directory")
                data = path.read_bytes()
                path.unlink()
                return data
            time.sleep(0.5)
        log.warning("Voice download did not complete within 30 seconds")
        return None

    def send(self, message: str) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        editor = self.driver.find_element(By.CSS_SELECTOR, "footer [contenteditable='true']")
        for index, line in enumerate(message.splitlines()):
            if index:
                editor.send_keys(Keys.SHIFT, Keys.ENTER)
            editor.send_keys(line)
        editor.send_keys(Keys.ENTER)

    def close(self) -> None:
        self.driver.quit()


def run(settings: Settings, store: Store) -> None:
    from selenium.common.exceptions import WebDriverException

    if not settings.allowed_numbers:
        raise ValueError("WHATSAPP_ALLOWED_NUMBERS must contain at least one trusted phone number")
    transcriber = Transcriber(settings)
    while True:
        client = None
        try:
            client = WhatsAppWeb(settings)
            log.info("Chrome opened. Scan QR code once if WhatsApp asks for it.")
            client.wait_for_login()
            current_chat = ""
            while True:
                for number in settings.allowed_numbers:
                    try:
                        if current_chat != number:
                            client.open_chat(number)
                            current_chat = number
                        incoming = client.incoming()
                        if not store.chat_initialized(number):
                            for message in incoming:
                                store.mark_existing(message.message_id)
                            store.mark_chat_initialized(number)
                            log.info("Chat %s ready; %d older messages skipped", number, len(incoming))
                            continue
                        for message in incoming:
                            if store.is_sent(message.message_id):
                                continue
                            reply = store.previous_reply(message.message_id)
                            if reply is None:
                                text = message.text
                                if message.voice:
                                    audio = client._audio(message.bubble)
                                    if audio is None:
                                        continue
                                    audio_dir = settings.data_dir / "audio"
                                    audio_dir.mkdir(parents=True, exist_ok=True)
                                    path = audio_dir / ("voice-" + "".join(c for c in message.message_id if c.isalnum())[:80] + ".ogg")
                                    path.write_bytes(audio)
                                    try:
                                        text = transcriber.transcribe(path)
                                    finally:
                                        path.unlink(missing_ok=True)
                                reply = process(text, store, settings, message_id=message.message_id)
                            client.send(reply)
                            store.mark_sent(message.message_id)
                            log.info("Processed message %s from %s", message.message_id, number)
                    except WebDriverException:
                        raise
                    except Exception:
                        log.exception("Failed to poll %s; retrying", number)
                time.sleep(settings.poll_seconds)
        except WebDriverException as exc:
            log.warning("WhatsApp browser disconnected (%s); reconnecting", type(exc).__name__)
        finally:
            if client is not None:
                with suppress(Exception):
                    client.close()
        time.sleep(10)
