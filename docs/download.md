---
layout: default
title: Download
description: Install Lumea on Windows or macOS
---

# Download

## macOS — Homebrew

```bash
brew tap ugurcandede/tap
brew install --cask lumea
```

The cask clears Gatekeeper for you. Lumea updates itself from then on; to do it
by hand: `brew upgrade --cask lumea`.

## Direct download

<div class="btn-row" style="justify-content:flex-start;margin-bottom:24px">
  <a class="btn btn-accent" href="https://github.com/ugurcandede/Lumea/releases/latest/download/Lumea-windows.exe">Download for Windows</a>
  <a class="btn btn-accent" href="https://github.com/ugurcandede/Lumea/releases/latest/download/Lumea-macos-arm64.zip">Download for macOS</a>
  <a class="btn btn-ghost" href="https://github.com/ugurcandede/Lumea/releases/latest">All releases</a>
</div>

Those links always point at the newest build.

**Windows** — run `Lumea-windows.exe`. It isn't code-signed, so SmartScreen
warns on the first launch: choose **More info → Run anyway**.

**macOS** — Homebrew is the recommended way: the app is not notarized, and the
cask takes care of Gatekeeper. If you unzip it by hand, move `Lumea.app` to your
Applications folder; when macOS blocks the first launch, allow it under
*System Settings › Privacy & Security › Open Anyway*.

macOS asks once for Bluetooth access; allow it, or Lumea can't see your strips.

## Run from source

Requires Python 3.11 or later (3.11–3.13 if PySide6 has no wheel for the newest
one yet).

```bash
git clone https://github.com/ugurcandede/Lumea.git
cd Lumea
pip install -r requirements.txt
python main.py
```

On macOS, Bluetooth access needs an `NSBluetoothAlwaysUsageDescription` entry
in the *interpreter's* app bundle — without it macOS kills the process on the
first scan. Lumea detects this, refuses to scan, and shows the one-line fix in
its status line. For python.org's 3.13 it is:

```bash
plutil -insert NSBluetoothAlwaysUsageDescription -string "Lumea controls Bluetooth LED strips." \
  /Library/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/Info.plist
```

## Requirements

Windows or macOS on Apple Silicon · Bluetooth turned on · a strip advertising
as `ELK-BLE…`, `MELK…` or `ELK-BULB…`

## Uninstall

```bash
brew uninstall --cask lumea
```

On Windows, quit Lumea from the tray and delete the exe. Settings live in the
registry under `HKEY_CURRENT_USER\Software\ugurcandede\Lumea`; on macOS in
`~/Library/Preferences/com.ugurcandede.Lumea.plist`.
