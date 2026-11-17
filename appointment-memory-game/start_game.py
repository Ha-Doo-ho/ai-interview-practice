"""Run the game at http://localhost:8000 using the Python standard library."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __name__ == "__main__":
    handler = partial(SimpleHTTPRequestHandler, directory=str(Path(__file__).parent / "dist"))
    try:
        with ThreadingHTTPServer(("127.0.0.1", 8000), handler) as server:
            print("Open http://localhost:8000 in your browser. Press Ctrl+C to stop.")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("Server stopped.")
    except OSError as error:
        raise SystemExit(f"Could not start the local server: {error}")
