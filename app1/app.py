from flask import Flask
import socket
import time
import threading

app = Flask(__name__)

@app.route("/")
def home():
    hostname = socket.gethostname()
    return f"""
    <h1>Hello from Server 1</h1>
    <hr>
    <p><b>Server:</b> app1</p>
    <p><b>Hostname:</b> {hostname}</p>
    <p><b>IP Address:</b> {socket.gethostbyname(hostname)}</p>
    <hr>
    """

def cpu_burn(duration=5):
    """Bakar CPU ringan — pakai ~30% CPU per thread selama N detik."""
    end = time.time() + duration
    while time.time() < end:
        _ = sum(i * i for i in range(5000))
        time.sleep(0.05)  # Jeda kecil → CPU tidak langsung 100%

@app.route("/stress")
def stress():
    """Endpoint stress — 1 thread, 5 detik, ringan."""
    t = threading.Thread(target=cpu_burn, args=(5,))
    t.daemon = True
    t.start()
    hostname = socket.gethostname()
    return f"""
    <h1>Stress Test Dimulai - Server 1</h1>
    <hr>
    <p><b>Server:</b> app1</p>
    <p><b>Hostname:</b> {hostname}</p>
    <p><b>Durasi:</b> 5 detik</p>
    <hr>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0")
