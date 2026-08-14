from __future__ import annotations

import sys

from hatop.app import HatopApp
from hatop.config import HatopConfigError


def main() -> None:
    try:
        app = HatopApp()
    except HatopConfigError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    app.run()


if __name__ == "__main__":
    main()
