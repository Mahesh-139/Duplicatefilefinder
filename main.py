"""
main.py - Desktop Application Entry Point

This file launches the desktop application:
1. Allocates an available local port on 127.0.0.1 (localhost).
2. Starts the Flask server in a background daemon thread.
3. Polls the Flask health check endpoint until the server is fully ready.
4. Opens a native Windows desktop window using PyWebView pointing to the local Flask application.
5. Handles clean application shutdown when the window is closed.
"""

import sys
import os
import socket
import threading
import time
import urllib.request
import webview
from werkzeug.serving import make_server

# Import the Flask application instance
from app import app


def find_free_port():
    """
    Find an unused TCP port on localhost (127.0.0.1).
    This ensures the app will never fail due to port 5000 being already in use.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerThread(threading.Thread):
    """
    Background daemon thread to host the Flask WSGI server.
    """
    def __init__(self, host, port):
        super().__init__()
        self.daemon = True
        self.host = host
        self.port = port
        self.server = make_server(host, port, app)

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


def wait_for_server(url, max_attempts=50, delay=0.1):
    """
    Poll the health endpoint until Flask is accepting requests.
    Returns True if the server became ready within the timeout, False otherwise.
    """
    health_url = f"{url}/api/health"
    for _ in range(max_attempts):
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(delay)
    return False


def get_asset_path(filename):
    """
    Resolve asset path both in normal execution and in PyInstaller frozen bundle.
    """
    if getattr(sys, "frozen", False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "assets", filename)


def main():
    host = "127.0.0.1"
    port = find_free_port()
    base_url = f"http://{host}:{port}"

    print(f"[Duplicate File Finder] Starting internal Flask server on {base_url}...")
    server_thread = ServerThread(host, port)
    server_thread.start()

    # Wait for the internal Flask server to be ready before opening the native window
    if not wait_for_server(base_url):
        print("[Duplicate File Finder] Error: Internal server failed to initialize in time.")
        sys.exit(1)

    print("[Duplicate File Finder] Server ready. Launching desktop window...")

    icon_path = get_asset_path("icon.ico")
    if not os.path.exists(icon_path):
        icon_path = None

    # Open the PyWebView desktop window
    window = webview.create_window(
        title="Duplicate File Finder",
        url=base_url,
        width=1120,
        height=800,
        min_size=(900, 640),
        resizable=True
    )

    # Start PyWebView native loop. This blocks until the window is closed by the user.
    webview.start(icon=icon_path)

    print("[Duplicate File Finder] Window closed. Shutting down cleanly...")
    server_thread.shutdown()
    sys.exit(0)


if __name__ == "__main__":
    main()

