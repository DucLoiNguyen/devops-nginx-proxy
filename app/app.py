import socket
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return f"Tạm biệt! Mình là container: {socket.gethostname()}\n"

@app.route("/health")
def health():
    return {"status": "ok"}
