---
layout: default
title: Home
---

<section class="hero">
  <img src="assets/images/icon.png" alt="Lumea" class="hero-icon">
  <h1>Lumea</h1>
  <p class="lede">Control your ELK-BLEDOM / MELK Bluetooth LED strips from the desktop — every strip at once.</p>
  <p class="sub"><strong>Windows and macOS</strong> — no phone, no vendor app, no account.</p>

  <div class="badges">
    <a href="https://github.com/ugurcandede/Lumea/releases/latest"><img src="https://img.shields.io/github/v/release/ugurcandede/Lumea?label=version&style=flat-square" alt="Version" height="20"></a>
    <a href="{{ '/download' | relative_url }}"><img src="https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows" height="20"></a>
    <a href="{{ '/download' | relative_url }}"><img src="https://img.shields.io/badge/macOS-Apple%20Silicon-000?style=flat-square&logo=apple&logoColor=white" alt="macOS" height="20"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" height="20"></a>
  </div>

  <pre class="terminal"><span class="comment"># macOS — install via Homebrew</span>
brew tap ugurcandede/tap
brew install --cask lumea</pre>

  <div class="btn-row">
    <a class="btn btn-accent" href="{{ '/download' | relative_url }}">Download Lumea</a>
    <a class="btn btn-ghost" href="https://github.com/ugurcandede/Lumea">View on GitHub</a>
  </div>
</section>

<section class="shots-section">
  <h2>One window for every light</h2>
  <div class="shots">
    <img src="assets/images/main-all.png" alt="Lumea, light theme">
    <img src="assets/images/main-dark.png" alt="Lumea, dark theme">
    <img src="assets/images/remote.png" alt="Remote control on a phone" class="shot-phone">
  </div>
  <p class="shot-label">Picker, presets, brightness and effects on top; strips and USB devices below. The phone gets the same controls.</p>
</section>

<section class="section">
  <h2>Features</h2>
  <div class="grid">
    <div class="card">
      <div class="icon">💡</div>
      <h3>Every strip at once</h3>
      <p>Connect several strips and drive them together, or click one to edit it on its own. Each strip remembers its last colour.</p>
    </div>
    <div class="card">
      <div class="icon">🎨</div>
      <h3>Live colour picker</h3>
      <p>Drag across the picker and the strips follow as you go. Brightness and power sit right below.</p>
    </div>
    <div class="card">
      <div class="icon">⭐</div>
      <h3>Twelve presets</h3>
      <p>Left-click a dot to apply it, right-click to save the current colour into it.</p>
    </div>
    <div class="card">
      <div class="icon">🌈</div>
      <h3>Effects</h3>
      <p>Rainbow turns through the colour wheel, Breathe fades your colour in and out, Cycle glides through your presets.</p>
    </div>
    <div class="card">
      <div class="icon">🎵</div>
      <h3>Music mode</h3>
      <p>The lights follow whatever your PC is playing — Pulse, Spectrum, Beat or Flow. No microphone, no virtual driver. <em>Plugin.</em></p>
    </div>
    <div class="card">
      <div class="icon">🖥️</div>
      <h3>PC RGB, too</h3>
      <p>Plugins put an MSI Mystic Light motherboard and SteelSeries Apex 3 / Rival 650 in the device list — driverless. <em>Windows.</em></p>
    </div>
    <div class="card">
      <div class="icon">📱</div>
      <h3>Remote control</h3>
      <p>An optional plugin lets a phone or tablet on the same network drive Lumea from the browser. Scan the QR and go.</p>
    </div>
    <div class="card">
      <div class="icon">🌙</div>
      <h3>Lives in the tray</h3>
      <p>Closing the window keeps Lumea running. Quick colours, power and settings from the tray menu; light or dark theme.</p>
    </div>
  </div>
  <div class="btn-row">
    <a class="btn btn-ghost" href="{{ '/features' | relative_url }}">See every feature</a>
  </div>
</section>

<section class="cta">
  <span class="pill">Polite with Bluetooth</span>
  <h2>Your headphones keep working</h2>
  <p>Lumea never connects on its own: opening the app doesn't touch Bluetooth until you scan and press Connect. Once the strips have been idle for a while it lets go of the links, so they stop competing with your Bluetooth audio — and the next colour you pick reconnects them. A link that drops for real is retried automatically.</p>
  <div class="btn-row">
    <a class="btn btn-accent" href="{{ '/guide' | relative_url }}">Read the guide</a>
    <a class="btn btn-ghost" href="{{ '/faq' | relative_url }}">FAQ</a>
  </div>
</section>

<section class="section">
  <h2>Which strips work</h2>
  <div class="grid grid-2">
    <div class="card">
      <div class="icon">📡</div>
      <h3>Found by name</h3>
      <p>Lumea lists any strip whose Bluetooth name starts with one of these. No addresses are hardcoded, so the same scan works on Windows and macOS.</p>
      <pre class="bytes">ELK-BLE…   MELK…   ELK-BULB…</pre>
    </div>
    <div class="card">
      <div class="icon">🎯</div>
      <h3>Only confirmed commands</h3>
      <p>Power and colour are the two commands verified on this hardware, so they are the only ones Lumea sends. Brightness dims the colour itself instead of guessing at a firmware command that differs between variants.</p>
      <pre class="bytes">7E 00 05 03 RR GG BB 00 EF</pre>
    </div>
  </div>
</section>

<section class="section center">
  <h2>Links</h2>
  <div class="badges">
    <a href="https://github.com/ugurcandede/Lumea"><img src="https://img.shields.io/badge/Repo-000?style=flat-square&logo=github&logoColor=white" alt="Repo" height="22"></a>
    <a href="https://github.com/ugurcandede/homebrew-tap"><img src="https://img.shields.io/badge/Homebrew%20Tap-FBB040?style=flat-square&logo=homebrew&logoColor=000" alt="Homebrew" height="22"></a>
    <a href="https://github.com/ugurcandede"><img src="https://img.shields.io/badge/ugurcandede-000?style=flat-square&logo=github&logoColor=white" alt="ugurcandede" height="22"></a>
  </div>
</section>

<section class="section center">
  <h2>Requirements</h2>
  <p class="muted">Windows or macOS on Apple Silicon · Bluetooth turned on · an ELK-BLEDOM / MELK strip</p>
  <p class="muted small">Not affiliated with the makers of ELK-BLEDOM / MELK devices, or with MSI / Mystic Light or SteelSeries.</p>
</section>
