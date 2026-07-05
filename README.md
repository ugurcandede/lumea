<div align="center">

<img src="assets/icon.png" alt="Lumea" width="128" />

# Lumea

**Desktop control for ELK-BLEDOM / MELK Bluetooth LED strips — drive multiple strips at once with a live color picker,
presets, and a system tray.**

![Version](https://img.shields.io/badge/version-1.0.0-blue?style=flat-square)
![Windows](https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=windows&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-000000?style=flat-square&logo=apple&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)

</div>

# Quick start

```bash
pip install -r requirements.txt
python main.py
```

> If `pip install` fails on the newest Python, use a 3.11–3.13 interpreter (PySide6/Pillow wheels can lag).

## Install

### macOS (Apple Silicon)

```bash
brew tap ugurcandede/tap
brew install --cask lumea
```

The cask clears Gatekeeper for you. To update later: `brew upgrade --cask lumea`.

### Windows

Download [`Lumea-windows.exe`](https://github.com/ugurcandede/lumea/releases/latest) and run it. On the SmartScreen prompt, choose **More info → Run anyway**.

## Prerequisites

- Python 3.11+
- A strip advertising as `ELK-BLE`, `MELK`, or `ELK-BULB`
- Bluetooth turned on
- *(optional, MSI motherboard RGB)* an MSI board with a Mystic Light USB controller — driven via `hidapi` (installed on Windows by `requirements.txt`)
- *(optional, SteelSeries RGB)* a SteelSeries Apex 3 keyboard and/or Rival 650 mouse — same driverless `hidapi` path

## Usage

1. **Scan** — lists nearby strips.
2. **Tick** the devices you want, then press **Connect Selected**. Double-click a row to set an **alias**.
3. **On / Off** and the **color picker** (live) — commands go to every checked-and-connected device at once.
4. **Presets** — the 12 swatches: left-click applies, right-click saves the current color.
5. **Disconnect All** drops every connection.

Closing the window keeps the app in the **system tray**. Checked devices, aliases, presets and the last color are saved
and restored on launch, and dropped links auto-reconnect.

## Features

- Control **multiple strips at once**
- Per-device **aliases**
- **Live color** picker with 12 savable **presets**
- **System tray** — runs in the background, icon reflects the current color
- Settings persistence and auto-reconnect
- **MSI motherboard RGB** *(Windows, optional)* — mirror the color to a Mystic Light controller, driverless
- **SteelSeries RGB** *(Windows, optional)* — mirror the color to an Apex 3 keyboard and/or Rival 650 mouse, driverless

## MSI motherboard RGB (optional · Windows)

If your PC is an MSI board with a **Mystic Light** USB controller, Lumea can control its RGB too — no MSI Center, no kernel driver. The controller appears in the device list as **MSI Mystic Light** (always "Connected"); tick it to mirror the color picker to the motherboard and any RGB/ARGB headers, alongside your BLE strips.

- **Driverless** — pure USB HID via [`hidapi`](https://pypi.org/project/hidapi/) (an optional dependency, Windows only).
- **Static color only.** Lumea never sends firmware effect/mode bytes — those are undocumented and have bricked some boards. Writes are volatile, so a reboot restores your BIOS lighting.
- **Case fans:** if they run off a case controller (e.g. MSI Gungnir), set that controller to **motherboard control** (JARGB) mode so they follow Lumea.
- Verified on an **MSI MPG Z790 CARBON WIFI**. Same-variant Mystic Light USB boards should work; anything else is detected and left untouched.

## SteelSeries RGB (optional · Windows)

If a SteelSeries **Apex 3** keyboard or **Rival 650** mouse is plugged in, Lumea can drive its lighting too — no SteelSeries GG, no driver. Each appears as its own device row (**SteelSeries Apex 3** / **SteelSeries Rival 650**, always "Connected"); tick it to mirror the color picker to that device.

- **Driverless** — pure USB HID via [`hidapi`](https://pypi.org/project/hidapi/), the same optional dependency as the MSI path.
- **Static color only**, following the picker. No brick risk (plain HID output reports; nothing is written to onboard flash).
- Verified on an **Apex 3** and a **Rival 650**. Other SteelSeries models are detected and left alone.

## Layout

```
main.py          entry point: QApplication + qasync event loop
ble.py           scan(); ElkBledom (one strip); DeviceManager (many strips, fan-out)
msi_mystic.py    optional MSI Mystic Light (USB HID) backend
steelseries.py   optional SteelSeries Apex 3 / Rival 650 (USB HID) backend
ui.py            LedController: device list, color, presets, system tray
colorpicker.py   embedded SV-square + hue-bar color picker
icon.py          app icon + dynamic tray icon
protocol.py      pure command encoders
```

---

<p align="center">
   <a href="https://github.com/ugurcandede">
    <img src="https://img.shields.io/badge/Built%20with%20%E2%9D%A4%20by-@ugurcandede-181717?logo=github&logoColor=white" alt="Built with love by @ugurcandede">
  </a>
</p>

<p align="center">
  <sub>Not affiliated with the makers of ELK-BLEDOM / MELK devices, or with MSI / Mystic Light or SteelSeries.</sub>
</p>
