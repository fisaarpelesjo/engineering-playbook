from __future__ import annotations

import sys

from engineering_playbook.local_ci import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
