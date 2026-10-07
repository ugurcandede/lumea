---
layout: default
title: Features
description: Everything Lumea does — strips, colour, effects, music, PC RGB, remote control and plugins
---

# Features

One small window for every light on your desk: Bluetooth strips, the motherboard,
the keyboard and the mouse. Here is what it does.

<div class="feature-row">
<div markdown="1">

## Every strip, one picker

Scan once, tick the strips you want and press **Connect**. From then on the
colour square, the hue bar, brightness and power drive all of them at the same
time — commands go out in parallel, so the strips change together instead of one
after another.

- **Aliases** — double-click a row and call it *Desk* instead of `ELK-BLEDOM`.
- **Remembered** — ticked strips, names, presets and each strip's last colour are
  restored on the next launch.
- **Forget** a strip with the bin icon; a new scan finds it again.
- **Hex input** — type `#33C9A4` and press Enter.

</div>
<div class="shot"><img src="{{ site.baseurl }}/assets/images/main-all.png" alt="Lumea with three strips connected"></div>
</div>

<div class="feature-row feature-row--flip">
<div markdown="1">

## One strip, or all of them

The **Editing** chips above the picker choose the target. **All** sends to every
ticked strip; click a strip's chip — or its row — and you edit just that one,
with its own colour, brightness and power loaded into the picker.

The strips never report their state back, so Lumea keeps each one's last
command and shows that. Switch from the shelf to the desk and the picker jumps
to the desk's colour.

</div>
<div class="shot"><img src="{{ site.baseurl }}/assets/images/main-focus.png" alt="Editing a single strip"></div>
</div>

<div class="feature-row">
<div markdown="1">

## Presets and brightness

**Twelve presets** sit under the picker: left-click applies one, right-click
saves the current colour into that slot. The same twelve are in the tray menu as
**Quick colors**.

**Brightness** dims the colour itself rather than sending a firmware brightness
command — that command differs between strip variants and isn't confirmed, so
Lumea doesn't guess. The result is the same on every strip.

**Power** is the pill at the end of the brightness row.

</div>
<div class="shot"><img src="{{ site.baseurl }}/assets/images/main-dark.png" alt="Lumea in dark theme"></div>
</div>

<div class="feature-row feature-row--flip">
<div markdown="1">

## Effects

Animations computed by Lumea and sent as colour frames, so they work the same on
every strip and every USB device:

| Effect | What it does |
|---|---|
| **Rainbow** | turns through the colour wheel, starting from your colour |
| **Breathe** | fades the picked colour in and out |
| **Cycle** | glides through your twelve presets |

**Speed** appears while an effect runs, and the dot at the end of the row shows
the colour being sent right now. Bluetooth strips get about 12 frames a second.

</div>
<div class="shot"><img src="{{ site.baseurl }}/assets/images/effects.png" alt="Rainbow effect running"></div>
</div>

<div class="feature-row feature-row--text">
<div markdown="1">

## Music mode <span class="platform">Windows</span>

The lights follow whatever your PC is playing — a loopback of the system audio,
so **no microphone** and **no virtual audio driver**.

| Mode | What it does |
|---|---|
| **Pulse** | your colour, brightness following the music |
| **Spectrum** | bass drives red, mids green, treble blue |
| **Beat** | steps through your presets on every beat |
| **Flow** | the hue keeps turning, faster the louder it gets |

**Sensitivity** tunes it for quiet tracks or busy ones. USB devices follow
closely; Bluetooth strips can lag a little, since BLE only carries so many
updates a second.

</div>
</div>

<div class="feature-row feature-row--flip">
<div markdown="1">

## PC RGB, without the vendor apps <span class="platform">Windows</span>

Supported USB devices appear in the list on their own, always connected. Tick
one and it mirrors the picker — next to your strips, from the same window.

- **MSI Mystic Light** — the motherboard and its RGB/ARGB headers. A
  **Static / Rainbow** menu on its row; Rainbow has its own speed.
- **SteelSeries Apex 3** keyboard and **Rival 650** mouse.

No MSI Center, no SteelSeries GG, no kernel driver. Lumea only sends the
static-colour report — never the undocumented effect bytes that have bricked
boards — and the writes are volatile: a reboot restores your BIOS lighting.

</div>
<div class="shot"><img src="{{ site.baseurl }}/assets/images/usb-devices.png" alt="MSI and SteelSeries devices in the list"></div>
</div>

<div class="feature-row">
<div markdown="1">

## Remote control from your phone

An optional plugin turns Lumea into a small web app on your network. Open it on
a phone, tablet or another computer: colour, brightness, presets, effects,
music, the device list and the settings are all there.

- **Pair once** — scan the QR, or open the address and type the 6-digit PIN.
  The browser then keeps a token; wrong PINs lock out after five tries.
- **Several PCs?** Each one announces itself on the network, and the page lists
  them and switches between them.
- **Reset pairings** draws a new PIN and forgets every paired browser.
- The **port** is yours to change if something else uses it.

</div>
<div class="shot"><img src="{{ site.baseurl }}/assets/images/remote.png" alt="Remote control page on a phone" style="max-width:280px"></div>
</div>

<div class="feature-row feature-row--flip">
<div markdown="1">

## Plugins

**Settings › Manage plugins** lists optional add-ons. Install one, switch it on,
and it runs inside Lumea — no restart. Plugins update on their own, without a
new Lumea release; a failed download leaves the old copy untouched.

Writing one is a folder of Python with a `Plugin` class. See
[plugins/README.md](https://github.com/ugurcandede/Lumea/blob/master/plugins/README.md)
for the contract; **Random color** is the small example.

</div>
<div class="shot"><img src="{{ site.baseurl }}/assets/images/plugins.png" alt="Plugins page with Remote control on"></div>
</div>

<div class="feature-row feature-row--text">
<div markdown="1">

## Polite with Bluetooth

- **No connection on launch.** Lumea lives in the tray and doesn't touch
  Bluetooth until you scan and press Connect.
- **Idle release.** After a minute without changes it lets go of the links, so
  they stop competing with your Bluetooth headphones. The next colour you pick
  reconnects them. Effects and music keep the links up while they run.
- **Auto-reconnect.** A link that drops for real is retried five times.
- **Found by name**, never by a hardcoded address — the same scan works on
  Windows and macOS.

</div>
</div>

<div class="feature-row feature-row--flip">
<div markdown="1">

## Tray, themes and updates

- **Lives in the tray.** Closing the window keeps Lumea running; quick colours,
  power and settings are in the tray menu. The tray icon can show the strip
  colour.
- **Light and dark**, following the system or fixed.
- **Updates itself.** On Windows the new exe swaps in and restarts; on macOS
  through Homebrew. A dismissed version stays hidden until a newer one ships.
- **Privacy.** One anonymous ping a day — a random install id and the version.
  Switch it off in Settings.

</div>
<div class="shot">
  <img src="{{ site.baseurl }}/assets/images/settings-dark.png" alt="Settings, dark theme" style="max-width:300px">
  <img src="{{ site.baseurl }}/assets/images/tray.png" alt="Tray menu" style="max-width:220px;margin-top:16px">
</div>
</div>

<div class="home-cta">
  <h2>Try it</h2>
  <p>Free and open source, for Windows and macOS.</p>
  <div class="btn-row">
    <a class="btn btn-accent" href="{{ '/download' | relative_url }}">Download Lumea</a>
    <a class="btn btn-ghost" href="{{ '/guide' | relative_url }}">Read the guide</a>
  </div>
</div>
