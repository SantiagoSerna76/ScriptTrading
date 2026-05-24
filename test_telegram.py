import time
from notifier import TelegramNotifier

print("Iniciando prueba de Telegram...")
notifier = TelegramNotifier()
print(f"Chat ID configurado: {notifier.chat_id}")

notifier.send_message("🚀 *Hola desde Antigravity!* Tu bot de Telegram está conectado correctamente y listo para hacer dinero de forma segura. 🤖💰")

# Esperar unos segundos para que el hilo termine la petición POST
time.sleep(2)
print("Prueba completada.")
