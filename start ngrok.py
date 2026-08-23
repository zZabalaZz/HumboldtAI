from pyngrok import ngrok
import time

public_url = ngrok.connect(5000)
print(public_url)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Cerrando túnel...")
    ngrok.kill()