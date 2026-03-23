# Download

<div style="display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin:2rem 0;">
  <div style="text-align:center;">
    <a id="win-btn" href="https://github.com/Elabsurdo984/luz-lang/releases/latest"
       style="display:inline-block;background:#e65100;color:white;padding:14px 32px;border-radius:8px;font-size:1.1rem;font-weight:bold;text-decoration:none;">
      🪟 Download for Windows
    </a>
    <p style="margin-top:0.6rem;color:#888;font-size:0.9rem;" id="win-info">Installer · No dependencies</p>
  </div>
  <div style="text-align:center;">
    <a id="linux-btn" href="https://github.com/Elabsurdo984/luz-lang/releases/latest"
       style="display:inline-block;background:#37474f;color:white;padding:14px 32px;border-radius:8px;font-size:1.1rem;font-weight:bold;text-decoration:none;">
      🐧 Download for Linux
    </a>
    <p style="margin-top:0.6rem;color:#888;font-size:0.9rem;" id="linux-info">tar.gz · luz + ray binaries</p>
  </div>
</div>

<script>
const API = "https://api.github.com/repos/Elabsurdo984/luz-lang/releases";
fetch(API)
  .then(r => r.json())
  .then(releases => {
    const latest = releases.find(r => r.tag_name.startsWith("v"));
    if (latest) {
      const win = latest.assets.find(a => a.name.endsWith("-setup.exe"));
      if (win) {
        document.getElementById("win-btn").href = win.browser_download_url;
        document.getElementById("win-info").textContent = latest.tag_name + " · No dependencies";
      }
      const linux = latest.assets.find(a => a.name.endsWith(".tar.gz"));
      if (linux) {
        document.getElementById("linux-btn").href = linux.browser_download_url;
        document.getElementById("linux-info").textContent = latest.tag_name + " · luz + ray binaries";
      }
    }

    // Older releases table
    const container = document.getElementById("older-releases");
    if (!container) return;

    const rows = releases
      .filter(r => r.tag_name.startsWith("v"))
      .slice(1)  // skip latest
      .map(r => {
        const win   = r.assets.find(a => a.name.endsWith("-setup.exe"));
        const linux = r.assets.find(a => a.name.endsWith(".tar.gz"));
        const winLink   = win   ? `<a href="${win.browser_download_url}">Windows</a>`   : "—";
        const linuxLink = linux ? `<a href="${linux.browser_download_url}">Linux</a>` : "—";
        const date = r.published_at ? r.published_at.slice(0, 10) : "";
        return `<tr><td>${r.tag_name}</td><td>${date}</td><td>${winLink}</td><td>${linuxLink}</td></tr>`;
      });

    if (rows.length === 0) {
      container.innerHTML = "<p style='color:#888'>No previous releases yet.</p>";
    } else {
      container.innerHTML = `
        <table>
          <thead><tr><th>Version</th><th>Date</th><th>Windows</th><th>Linux</th></tr></thead>
          <tbody>${rows.join("")}</tbody>
        </table>`;
    }
  });
</script>

### Windows — What's included

- Full Luz interpreter (`luz.exe`)
- `ray` package manager (`ray.exe`)
- `luz` and `ray` added to your system PATH automatically
- Standard libraries pre-installed (`luz-math`, `luz-random`, `luz-io`, `luz-system`)
- No Python required

### Linux — Setup after download

```bash
tar -xzf luz-*-linux.tar.gz
sudo mv luz ray /usr/local/bin/
luz program.luz
```

### After installing

```bash
luz program.luz        # run a file
luz                    # open the interactive REPL
ray install user/pkg   # install a package
```

---

## Older releases

<div id="older-releases"><p style="color:#888">Loading...</p></div>
