import os
from dotenv import load_dotenv

# Cargar el archivo .env
load_dotenv()

key = os.getenv('BINANCE_API_KEY')
secret = os.getenv('BINANCE_SECRET_KEY')

print(f"API KEY: '{key}'")
print(f"Longitud API KEY: {len(key) if key else 0}")
print(f"SECRET KEY: '{secret}'")
print(f"Longitud SECRET KEY: {len(secret) if secret else 0}")