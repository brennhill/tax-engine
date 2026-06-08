from __future__ import annotations

import argparse
from pathlib import Path
import sys

from tax_pipeline.intake.server import build_server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    project_root = Path(__file__).resolve().parent.parent
    server = build_server(args.host, args.port, project_root=project_root)
    try:
        print(f"Tax Engine intake listening on http://{args.host}:{server.server_port}")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
