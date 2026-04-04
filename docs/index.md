<div class="luz-hero">
  <h1>Luz Language</h1>
  <p>A lightweight, interpreted programming language designed to be simple, readable, and easy to learn.</p>
  <div class="luz-hero-btns">
    <a id="download-btn" href="https://github.com/Elabsurdo984/luz-lang/releases/latest" class="luz-btn-primary">Download</a>
    <a href="getting-started/installation/" class="luz-btn-secondary">Get Started →</a>
  </div>
  <p style="margin-top:1.25rem;color:#555;font-size:0.85rem;" id="download-info">No Python required</p>
</div>

<script>
fetch("https://api.github.com/repos/Elabsurdo984/luz-lang/releases")
  .then(r => r.json())
  .then(releases => {
    const isLinux = navigator.platform.toLowerCase().includes("linux");
    const winRelease = releases.find(r => r.tag_name.startsWith("win-v"));
    const linuxRelease = releases.find(r => r.tag_name.startsWith("linux-v"));
    const winAsset = winRelease?.assets.find(a => a.name.endsWith("-setup.exe"));
    const linuxAsset = linuxRelease?.assets.find(a => a.name.endsWith(".tar.gz"));
    const asset = isLinux ? (linuxAsset || winAsset) : (winAsset || linuxAsset);
    const tag = isLinux ? linuxRelease?.tag_name : winRelease?.tag_name;
    if (asset) {
      const label = asset.name.endsWith(".exe") ? "🪟 Download for Windows" : "🐧 Download for Linux";
      document.getElementById("download-btn").href = asset.browser_download_url;
      document.getElementById("download-btn").textContent = label;
      document.getElementById("download-info").textContent = (tag || "") + " · No Python required";
    }
  });
</script>

---

## A taste of Luz

```
name = listen("What is your name? ")
write($"Hello {name}!")

for i = 1 to 5 {
    if even(i) {
        write($"{i} is even")
    } else {
        write($"{i} is odd")
    }
}
```

---

## Why Luz?

<div class="luz-features">
  <div class="luz-card">
    <div class="luz-card-icon">⚡</div>
    <h3>No boilerplate</h3>
    <p>Variables need no declaration keyword. Blocks use <code>{ }</code>.</p>
  </div>
  <div class="luz-card">
    <div class="luz-card-icon">📖</div>
    <h3>Readable syntax</h3>
    <p>Keywords read like English: <code>for i = 1 to 10</code>, <code>attempt / rescue</code>.</p>
  </div>
  <div class="luz-card">
    <div class="luz-card-icon">🏗️</div>
    <h3>Full OOP</h3>
    <p>Classes, inheritance, method overriding, and <code>super</code>.</p>
  </div>
  <div class="luz-card">
    <div class="luz-card-icon">🔧</div>
    <h3>First-class functions</h3>
    <p>Lambdas, closures, and higher-order functions.</p>
  </div>
  <div class="luz-card">
    <div class="luz-card-icon">🛡️</div>
    <h3>Helpful errors</h3>
    <p>Every error includes the source line number.</p>
  </div>
  <div class="luz-card">
    <div class="luz-card-icon">📦</div>
    <h3>Standard library</h3>
    <p>Math, random, I/O, system, and clock — all built in.</p>
  </div>
</div>

---

## Quick example

```
class Animal {
    function init(self, name) {
        self.name = name
    }
    function speak(self) {
        write($"{self.name} says hello!")
    }
}

class Dog extends Animal {
    function speak(self) {
        super.speak()
        write("(woof!)")
    }
}

d = Dog("Rex")
d.speak()
```

---

## Features at a glance

| Feature | Syntax |
|---|---|
| Variable | `x = 10` |
| Null coalescing | `x = value ?? "default"` |
| Format string | `$"Hello {name}"` |
| List comprehension | `[x * x for x in list]` |
| Membership | `3 in [1, 2, 3]` |
| String repeat | `"ha" * 3` |
| For range | `for i = 1 to 10 { }` |
| For each | `for item in list { }` |
| Lambda | `fn(x) => x * 2` |
| Class | `class Dog extends Animal { }` |
| Error handling | `attempt { } rescue (e) { }` |
| Import | `import "math"` |
