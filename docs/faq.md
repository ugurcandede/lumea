---
layout: default
title: FAQ
description: Common questions about Lumea
---

# FAQ

## Will my strip work?

If its Bluetooth name starts with `ELK-BLE`, `MELK` or `ELK-BULB`, Lumea lists
it. Power and colour use the frames confirmed on these controllers. If yours
shows up but doesn't respond, please
[open an issue](https://github.com/ugurcandede/Lumea/issues) with its name.

## My strip doesn't show up

- Make sure Bluetooth is on and the strip has power.
- **Close the phone app.** Most of these controllers accept one connection at a
  time; if your phone is connected, the strip stops advertising.
- On macOS, check *System Settings › Privacy & Security › Bluetooth* and allow
  Lumea.

## Why doesn't Lumea connect on launch?

On purpose. Lumea lives in the tray; grabbing Bluetooth every time it opens
would be rude to everything else using it.
Scan, then Connect — it takes a second.

## My Bluetooth headphones stutter

A busy Bluetooth radio can do that. Lumea releases its links after a minute
without changes, so idle strips don't compete with your audio; the next colour
you pick reconnects them. Effects and music mode keep the links busy while they
run.

## Why doesn't the app show the strip's real colour?

These strips never report their state back — not the colour, not whether they
are on. Lumea shows the last command it sent, and remembers it per strip. If
you change the colour with the remote or the phone app, Lumea can't know.

## Where are the strip's built-in effects and native brightness?

Their command bytes differ between ELK-BLEDOM variants and haven't been
confirmed on real hardware, so Lumea doesn't send them — a guessed command
does nothing at best. Brightness dims the colour instead, and the effects
(Rainbow, Breathe, Cycle) are animated by Lumea itself.

## Is music mode coming to macOS?

It needs a loopback of the system audio, which Windows provides out of the box
and macOS does not without a virtual audio driver. For now it is Windows-only,
as are the MSI and SteelSeries devices.

## Does Lumea collect any data?

Once a day it sends an anonymous ping to Google Analytics: a random install id
and the app version. **No device names, no addresses, no colours.** Turn it off
any time by unchecking **Send anonymous usage stats** in Settings.

## Why does Windows warn me / why isn't the Mac app notarized?

Neither build is signed with a paid certificate. On Windows choose **More
info → Run anyway** on the SmartScreen prompt; on macOS install with Homebrew,
which takes care of Gatekeeper, or allow the first launch under *System Settings ›
Privacy & Security › Open Anyway*.

## Is it safe for my MSI motherboard?

Lumea only sends the static-colour report, never effect or mode bytes — those
are undocumented and have bricked some boards. The writes are volatile: a
reboot restores your BIOS lighting. Boards that don't match the verified
controller are detected and left untouched.
