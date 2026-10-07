---
layout: default
title: Guide
description: How to use Lumea
---

# Guide

## First connection

1. **Scan** — lists the strips nearby. Lumea never touches Bluetooth before you
   scan, so opening it can't steal a connection from anything else.
2. **Tick** the strips you want, then press **Connect**. Double-click a row to
   give it an **alias**.
3. Pick a colour. Commands go to every connected target at once.

The same button turns into **Disconnect** once everything ticked is linked, and
drops every connection.

Ticked strips, aliases, presets and each strip's last colour are saved, so the
next launch picks up where you left off — you only scan and connect again.

## Editing one strip or all of them

The **Editing** chips choose what the picker drives:

- **All** — every ticked strip gets the same colour, brightness and power.
- **A single strip** — click its chip to edit it on its own. Its own last
  colour loads into the picker.

The strips never report their state back, so what Lumea shows is the last
command it sent. Each strip remembers its own.

## Colour, brightness, power

Drag across the colour square and the hue bar; the strips follow live.
**Brightness** scales the colour itself rather than sending a firmware command,
because that command differs between strip variants and isn't confirmed.

**Presets** are the 12 dots: **left-click** applies one, **right-click** saves
the current colour into it.

## Effects

The **Effect** chips under Brightness animate every device the picker drives:

| Effect | What it does |
|---|---|
| **Rainbow** | turns through the colour wheel |
| **Breathe** | fades the picked colour in and out |
| **Cycle** | glides through your presets |

**Speed** sets the pace. Only one effect or music mode runs at a time.
Bluetooth strips get about 12 frames a second.

## Music mode <small>(Windows)</small>

The **Music** chips make the lights follow the system audio — a loopback of
what your PC is playing, so no microphone and no virtual audio driver.

| Mode | What it does |
|---|---|
| **Pulse** | the picked colour, brightness following the music |
| **Spectrum** | bass drives red, mids green, treble blue |
| **Beat** | steps through your presets on every beat |
| **Flow** | the hue keeps turning, faster the louder the music |

**Sensitivity** — raise it for quiet tracks, lower it if the lights jump
around.

Bluetooth strips may lag behind the music: BLE only carries so many updates a
second, and fewer the more strips are connected, so frames it can't keep up
with are dropped. Music mode listens to the output device that is the default
when it starts; after switching speakers or headphones, pick the mode again.

## PC RGB <small>(Windows)</small>

Supported USB devices show up in the device list on their own, always
*Connected*. Tick one to mirror the picker's colour to it, alongside your
strips. Both paths are driverless — no MSI Center, no SteelSeries GG.

**MSI Mystic Light** — the motherboard and its RGB/ARGB headers. Static colour
only: Lumea never sends firmware effect bytes, which have bricked boards, and
the writes are volatile, so a reboot restores your BIOS lighting. If your case
fans run off a case controller (e.g. MSI Gungnir), set it to motherboard
control (JARGB) so they follow. Verified on an MSI MPG Z790 CARBON WIFI; other
boards are detected and left untouched.

**SteelSeries Apex 3 and Rival 650** — each appears as its own row. Static
colour, nothing written to onboard flash. Other SteelSeries models are left
alone.

These devices follow the **All** colour; they aren't driven when you're editing
a single strip.

## Plugins

**Settings › Manage plugins** lists optional add-ons. Install one and switch it
on; plugins update on their own, without a new Lumea release.

**Remote control** drives Lumea from a phone, tablet or another computer's
browser on the same network: colour, brightness, presets, effects, music, the
devices and the settings. Switch it on, then scan the QR code shown under it —
or open the address and enter the PIN. Windows asks once to let Lumea through
the firewall: allow it on private networks. If several PCs run it, the page
lists them all and switches between them.

## Tray and settings

Closing the window keeps Lumea in the **system tray**; quit from the tray menu.
The menu has quick colours, power and settings, and the tray icon can show the
current colour.

**Settings** (the icon in the title bar, or the tray menu):

- **Theme** — Auto follows the system; or fixed Light / Dark
- **Tray icon** colour
- **Updates** — checks GitHub for a newer version and installs it
- **Send anonymous usage stats** — see the [FAQ]({{ '/faq' | relative_url }})
