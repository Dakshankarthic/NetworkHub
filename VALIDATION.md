# Validation

Tested on Windows with Python 3.12.

- Five automated tests pass: selected adapter binding, TUN/private routes and loopback controller, disconnected selection, proxy/PAC restoration, and preservation of independently changed proxy settings.
- Tests use a temporary registry key; they do not change the real Windows proxy settings.
- Source UI startup check passes at 1000 × 820. On a fresh profile, adapter cards arrive after asynchronous discovery; the fast self-test intentionally does not wait for discovery.
- The public executable was built in a clean virtual environment and passed the packaged startup check with its routing core present.
- All nine 1 MiB HTTPS transfers completed through the public version's manual proxy. Ethernet and USB tethering were observed. A test assertion expecting all three routes failed because Wi-Fi was not observed during that run; no claim of three-link operation is made for this public-version test. Original Windows proxy settings were preserved after shutdown.
- The initial local build passed nine simultaneous 1 MiB HTTPS transfers through the manual proxy, with Ethernet, USB tethering, and Wi-Fi routes all observed.
- All-app TUN mode has configuration validation only. It has not been activated on the development PC and is experimental.

Use a local proxy test before considering system routing. Do not interpret aggregate NIC counters as proof that one download is bonded across networks.
