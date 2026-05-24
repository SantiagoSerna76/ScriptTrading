import logging
import requests
import threading
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """Clase para enviar notificaciones a Telegram de forma asíncrona."""

    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.is_configured = bool(self.bot_token and self.chat_id)

        if not self.is_configured:
            logger.warning("TelegramNotifier: No se encontraron TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env. Las notificaciones están desactivadas.")

    def send_message(self, text: str, parse_mode: str = "Markdown") -> None:
        """Envía un mensaje usando un hilo para no bloquear el bot principal."""
        if not self.is_configured:
            return

        def _send():
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            try:
                # Timeout corto para evitar colgar el hilo si Telegram falla
                response = requests.post(url, json=payload, timeout=5)
                if response.status_code != 200:
                    logger.error(f"Error enviando mensaje a Telegram HTTP {response.status_code}: {response.text}")
            except Exception as e:
                logger.error(f"Excepción enviando mensaje a Telegram: {e}")

        # Ejecutar la petición HTTP en background para cero latencia
        thread = threading.Thread(target=_send, daemon=True)
        thread.start()
