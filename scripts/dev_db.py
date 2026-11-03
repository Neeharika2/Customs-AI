"""Start the bundled Postgres used for local development and keep it alive.

Run in the background:  .venv/bin/python scripts/dev_db.py
Stop with Ctrl-C (or kill the process); the data directory persists.
"""
import pathlib
import signal
import time

import pgserver

DATA = pathlib.Path("/tmp/opencode/pgdata")


def main() -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(str(DATA))
    print("Postgres running", flush=True)
    print("DATABASE_URL=" + server.get_uri().replace("postgresql://", "postgresql+psycopg://"),
          flush=True)

    stopping = False

    def stop(*_args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        time.sleep(1)


if __name__ == "__main__":
    main()
