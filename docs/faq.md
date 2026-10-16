---
layout: default
title: FAQ
description: Common questions about Lumea
---

# FAQ

<details class="faq" markdown="1">
<summary>Will my strip work?</summary>

If its Bluetooth name starts with `ELK-BLE`, `MELK` or `ELK-BULB`, Lumea lists
it. Power and colour use the frames confirmed on these controllers. If yours
shows up but doesn't respond, please
[open an issue](https://github.com/ugurcandede/Lumea/issues) with its name.

</details>

<details class="faq" markdown="1">
<summary>My strip doesn't show up</summary>

- Make sure Bluetooth is on and the strip has power.
- **Close the phone app.** Most of these controllers accept one connection at a
  time; if your phone is connected, the strip stops advertising.
- On macOS, check *System Settings › Privacy & Security › Bluetooth* and allow
  Lumea.

</details>

<details class="faq" markdown="1">
<summary>Why doesn't Lumea connect on launch?</summary>

On purpose. Lumea lives in the tray; grabbing Bluetooth every time it opens
would be rude to everything else using it.
Scan, then Connect — it takes a second.

</details>

<details class="faq" markdown="1">
<summary>My Bluetooth headphones stutter</summary>

A busy Bluetooth radio can do that. Lumea releases its links after a minute
without changes, so idle strips don't compete with your audio; the next colour
you pick reconnects them. Effects and music mode keep the links busy while they
run.

</details>

<details class="faq" markdown="1">
<summary>Why doesn't the app show the strip's real colour?</summary>

These strips never report their state back — not the colour, not whether they
are on. Lumea shows the last command it sent, and remembers it per strip. If
you change the colour with the remote or the phone app, Lumea can't know.

</details>

<details class="faq" markdown="1">
<summary>Where are the strip's built-in effects and native brightness?</summary>

Their command bytes differ between ELK-BLEDOM variants and haven't been
confirmed on real hardware, so Lumea doesn't send them — a guessed command
does nothing at best. Brightness dims the colour instead, and the effects
(Rainbow, Breathe, Cycle) are animated by Lumea itself.

</details>

<details class="faq" markdown="1">
<summary>Does music mode work on macOS?</summary>

Yes, on macOS 13 and later: the Music mode plugin captures the system audio
through ScreenCaptureKit, so no virtual audio driver. macOS asks for the Screen &
System Audio Recording permission the first time; allow Lumea and relaunch it.

</details>

<details class="faq" markdown="1">
<summary>Why does music mode want to record my screen?</summary>

Because macOS has no audio-only permission: Screen & System Audio Recording is
the one way an app can hear what the system plays, and it covers the screen as
well. Lumea reads the audio alone — the screen isn't looked at, recorded or sent
anywhere, and the microphone isn't involved.

</details>

<details class="faq" markdown="1">
<summary>A plugin says <em>Needs a newer Lumea</em> or <em>Needs a plugin update</em></summary>

Lumea and each plugin declare the plugin API version they speak. *Needs a newer
Lumea* means the plugin was written for a newer app than yours: update Lumea
from Settings › About. *Needs a plugin update* means the installed copy
predates your Lumea: press **Update** on the Plugins page. Plugins are
published from the repository, so they update without a new Lumea release.

</details>

<details class="faq" markdown="1">
<summary>Does Lumea collect any data?</summary>

Once a day it sends an anonymous ping to Google Analytics: a random install id
and the app version. **No device names, no addresses, no colours.** Turn it off
any time by unchecking **Send anonymous usage stats** in Settings.

</details>

<details class="faq" markdown="1">
<summary>Why does Windows warn me / why isn't the Mac app notarized?</summary>

Neither build is signed with a paid certificate. On Windows choose **More
info → Run anyway** on the SmartScreen prompt; on macOS install with Homebrew,
which takes care of Gatekeeper, or allow the first launch under *System Settings ›
Privacy & Security › Open Anyway*.

</details>

<details class="faq" markdown="1">
<summary>Do the MSI and SteelSeries plugins work on macOS?</summary>

No. Both drive the hardware through `hidapi`, which Lumea bundles on Windows
only; on a Mac they install and run but add no device. The strips, effects,
music mode and the remote work the same on both systems.

</details>

<details class="faq" markdown="1">
<summary>Is it safe for my MSI motherboard?</summary>

Lumea only sends the static-colour report, never effect or mode bytes — those
are undocumented and have bricked some boards. The writes are volatile: a
reboot restores your BIOS lighting. Boards that don't match the verified
controller are detected and left untouched.

</details>
