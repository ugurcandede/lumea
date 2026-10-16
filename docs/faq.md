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

## Does music mode work on macOS?

Yes, on macOS 13 and later: the Music mode plugin captures the system audio
through ScreenCaptureKit, so no virtual audio driver. macOS asks for the Screen &
System Audio Recording permission the first time; allow Lumea and relaunch it.

## Why does music mode want to record my screen?

Because macOS has no audio-only permission: Screen & System Audio Recording is
the one way an app can hear what the system plays, and it covers the screen as
well. Lumea reads the audio alone — the screen isn't looked at, recorded or sent
anywhere, and the microphone isn't involved.

## A plugin says *Needs a newer Lumea* or *Needs a plugin update*

Lumea and each plugin declare the plugin API version they speak. *Needs a newer
Lumea* means the plugin was written for a newer app than yours: update Lumea
from Settings › About. *Needs a plugin update* means the installed copy
predates your Lumea: press **Update** on the Plugins page. Plugins are
published from the repository, so they update without a new Lumea release.

## Does Lumea collect any data?

Once a day it sends an anonymous ping to Google Analytics: a random install id
and the app version. **No device names, no addresses, no colours.** Turn it off
any time by unchecking **Send anonymous usage stats** in Settings.

## Why does Windows warn me / why isn't the Mac app notarized?

Neither build is signed with a paid certificate. On Windows choose **More
info → Run anyway** on the SmartScreen prompt; on macOS install with Homebrew,
which takes care of Gatekeeper, or allow the first launch under *System Settings ›
Privacy & Security › Open Anyway*.

## Do the MSI and SteelSeries plugins work on macOS?

No. Both drive the hardware through `hidapi`, which Lumea bundles on Windows
only; on a Mac they install and run but add no device. The strips, effects,
music mode and the remote work the same on both systems.

## Is it safe for my MSI motherboard?

Lumea only sends the static-colour report, never effect or mode bytes — those
are undocumented and have bricked some boards. The writes are volatile: a
reboot restores your BIOS lighting. Boards that don't match the verified
controller are detected and left untouched.
