# Contributing

Bug reports are as useful as patches. If GhostRead does something odd, open an
issue with your Windows version, your Python version (`python --version`) and
what you did. If the window misbehaves, a screenshot usually says it all.

## Getting set up

```
git clone https://github.com/Amrita0205/ghostreader
cd ghostreader
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
build.bat            test, rebuild the exe, update the installed copy
build.bat /fast      skip the tests
build.bat /install   also create the install if there is not one yet
build.bat /noinstall build only, leave the installed copy alone
build.bat /run       start the app when it is done
```

It sets up the same `.venv` that `run.bat` uses, adds PyInstaller the first
time, and stops before touching the exe if a test fails or if GhostRead is
still open, since Windows will not let a running exe be overwritten.

### Why it installs as well as builds

`dist\GhostRead.exe` is not the exe anyone runs. A desktop shortcut points at
`%LOCALAPPDATA%\GhostRead\GhostRead.exe`, and a build that stops at `dist\`
leaves that copy on the old code: the build succeeds, the app behaves exactly
as before, and the change looks like it failed when it is really just sitting
in a file nothing launches.

So the build updates an install that already exists, every time. It only
*creates* one when you pass `/install`, which also makes the desktop shortcut
if it is missing, so a plain `build.bat` on a machine that has no install
still writes nothing outside the project folder.

The long way, if you want the steps yourself:

```
pip install pyinstaller
pyinstaller packaging/ghostread.spec --noconfirm --clean
```

`--clean` matters. Without it a stale analysis cache can freeze the previous
code, and you get an exe that looks built but behaves like the old one.

CI does all this for you on every `v*` tag, so a local build is only needed to
try a change in the real exe before tagging it.

## Licence

Contributions are accepted under the MIT licence, the same as the rest of the
project. Note that the bundled binary is subject to PyMuPDF's AGPL terms, which
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) explains.
