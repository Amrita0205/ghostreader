"""Entry point for the frozen Windows build.

PyInstaller needs a script it can run as a top level module, which rules out
``ghostread/__main__.py`` because that uses a relative import. This does the
same job with an absolute one.
"""

import sys

from ghostread.cli import main

if __name__ == "__main__":
    sys.exit(main())
