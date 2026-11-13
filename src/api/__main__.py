"""
Start the NeuroSync server:  python -m src.api  [--host 127.0.0.1] [--port 8000]

Binding to anything other than 127.0.0.1 exposes session data and the live
camera stream to the network – only do that behind authentication and TLS.
"""

import argparse

import uvicorn

from src.api.app import create_app
from src.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="NeuroSync local server")
    parser.add_argument("--host", default=str(settings.api.host))
    parser.add_argument("--port", type=int, default=int(settings.api.port))
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"[warning] binding to {args.host}: NeuroSync data will be reachable from the network.")
    print(f"NeuroSync: http://{args.host}:{args.port}   (API docs: http://{args.host}:{args.port}/docs)")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
