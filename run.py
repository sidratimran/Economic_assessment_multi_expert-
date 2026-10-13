"""Start the AsiaPulse AI dashboard:  python run.py   →  http://localhost:8000

On a cloud host, PORT is provided by the platform and the server listens on all interfaces.
"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    uvicorn.run("api.server:app", host=host, port=port, reload=False)
