# Contributing

Bug reports are as useful as patches. If GhostRead does something odd, open an
issue with your Windows version, your Python version (`python --version`) and
what you did. If the window misbehaves, a screenshot usually says it all.

## Getting set up

```
git clone https://github.com/Amrita0205/ghostread
cd ghostread
python -m venv .venv
.venv\Scripts\activate          # source .venv/bin/activate elsewhere
pip install -e .
ghostread some.pdf
```

## Before you open a pull request

```
python -m tests.test_core       # no display needed
python -m tests.test_gui        # opens a real window
```

Both must pass. On Linux the GUI ones need `xvfb-run -a python -m tests.test_gui`.
CI runs the same two on Windows and Ubuntu.

## How the code is arranged

| file | what lives there |
| --- | --- |
| `ghostread/document.py` | PDF loading, rendering, search, outline. **No GUI imports** |
| `ghostread/state.py` | per document page and geometry memory |
| `ghostread/app.py` | the Tk overlay window |
| `ghostread/winext.py` | Windows click through and global hotkey, via ctypes |
| `ghostread/cli.py` | argument parsing |

The rule worth keeping: `document.py` never imports tkinter. That is what makes
rendering and search debuggable without a display, and it is what lets
`test_core.py` run in CI on a headless box.

Anything Windows-only belongs in `winext.py` behind a capability check, so the
app still starts on Linux and macOS with those features quietly switched off.

## Building the Windows exe locally

```
pip install pyinstaller
pyinstaller packaging/ghostread.spec --noconfirm --clean
```

The result is `dist/GhostRead.exe`. CI does this for you on every `v*` tag, so
you only need it if you are changing how the build works.

## Licence

Contributions are accepted under the MIT licence, the same as the rest of the
project. Note that the bundled binary is subject to PyMuPDF's AGPL terms, which
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) explains.
