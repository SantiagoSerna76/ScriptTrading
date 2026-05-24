#!/usr/bin/env python3
"""
Punto de entrada para Render (servicio WEB gratuito).

Estrategia keep-alive:
  1. Flask corre en el hilo principal → Render lo detecta como web service
  2. TradingBot corre en un hilo daemon en paralelo
  3. cron-job.org hace ping a /health cada 10 min → el servicio nunca duerme
  4. Todo gratis con las 750 h/mes del free tier de Render
"""

import os
import threading
import logging
import traceback
from app import app  # Flask con dashboard + /api/*

logger = logging.getLogger(__name__)


# ── Endpoint de salud (para el ping de cron-job.org) ─────────────────────────
@app.route("/health")
def health():
    """Render y cron-job.org pingean aquí cada 10 min para mantener el servicio vivo."""
    return {"status": "ok", "service": "trading-bot"}, 200


# ── Hilo del bot de trading ───────────────────────────────────────────────────
def _run_bot():
    """Ejecuta el bot de trading en un hilo daemon independiente."""
    try:
        from trading_bot import main as bot_main
        logger.info("🤖  Bot de trading iniciado en background thread")
        bot_main()
    except Exception as e:
        logger.error(f"❌  Bot crashed: {e}")
        logger.error(traceback.format_exc())
        # Si el bot falla, el servidor Flask sigue corriendo (el proceso no muere)


# ── Arranque ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 1. Lanza el bot en un hilo daemon (muere si el proceso principal muere)
    bot_thread = threading.Thread(target=_run_bot, daemon=True, name="TradingBot")
    bot_thread.start()

    # 2. Flask en el hilo principal — Render asigna el puerto via env var PORT
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐  Flask server arrancando en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
