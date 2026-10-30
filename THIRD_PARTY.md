# Third-party software

NetworkHub source is GPL-3.0-only. See LICENSE. Binary dependencies are downloaded separately; no runtime settings, tokens, or model files belong in this repository.

| Component | Version | License / corresponding source |
| --- | --- | --- |
| Mihomo | v1.19.33, unmodified windows-amd64-v3 | [GPL v3 license and source](https://github.com/MetaCubeX/mihomo/tree/v1.19.33); [source archive](https://github.com/MetaCubeX/mihomo/archive/refs/tags/v1.19.33.tar.gz) |
| Wintun | 0.14.1, official amd64 DLL | [Official distribution and source](https://www.wintun.net/); downloaded archive includes its binary redistribution license, copied to bin/WINTUN-LICENSE.txt |
| Python / Tk | Runtime dependent | [Python license](https://docs.python.org/3/license.html), [Tcl/Tk license](https://www.tcl.tk/software/tcltk/license.html) |
| requests | See requirements.txt | [Apache 2.0](https://github.com/psf/requests/blob/main/LICENSE) |
| psutil | See requirements.txt | [BSD 3-Clause](https://github.com/giampaolo/psutil/blob/master/LICENSE) |
| filelock | See requirements.txt | [Unlicense](https://github.com/tox-dev/filelock/blob/main/LICENSE) |
| PyInstaller | Build dependency | [GPL with bootloader exception](https://pyinstaller.org/en/stable/license.html) |

Binary distributors must preserve the applicable license notices and meet corresponding-source obligations. Keep component versions and source references with releases. The fetch script pins upstream archive SHA-256 hashes.
