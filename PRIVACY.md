# DragWheel privacy policy

_Last updated: October 2026 (DragWheel 1.2)_

DragWheel converts and processes files **entirely on your own computer**. Conversions and tools never upload your files, and DragWheel does not collect usage statistics, telemetry or any personal data.

A few features need the internet. Each one connects **only when you use it**, and only to the service named below.

## Connections DragWheel makes, and when

| Feature | When | What is contacted | What is sent |
|---|---|---|---|
| **Update check** | At most once a day, or when you click *Check for updates*. Can be turned off. | `api.github.com` (this project's releases) | A standard HTTPS request. No files or personal data. |
| **Downloading an update** | Only when you click *Download & install* | GitHub Releases of this project | — |
| **One-time downloads** (AI background removal model, speech-to-text model, the link reader *yt-dlp*, Cloudflare's *cloudflared*) | Only the first time you use the feature, after you agree | GitHub and Hugging Face | — |
| **Play a link in Float** | When you play a copied link | The website the link points to (for example YouTube), the way a browser would | The link |
| **Send to phone → Internet link** | Only when you choose it and click *Upload* | One free temporary file service (litterbox.catbox.moe, 0x0.st, uguu.se, or tmpfiles.org if you pick it) | **The file you chose.** Anyone with the link can download it until the service deletes it (5 minutes to 72 hours). |
| **Send to phone → Link from this PC** | While the window is open | Cloudflare (a free *Quick Tunnel* through `trycloudflare.com`, no account), using Cloudflare's own tool *cloudflared*, downloaded once from GitHub after you agree | **The file you chose**, sent from this PC through Cloudflare to whoever opens the link. It isn't stored; the link stops when you close the window. |
| **Send to phone → Cloud link** | When you click *Make a link* | Your own OneDrive, Google Drive, iCloud Drive, Dropbox or Box | A copy of **the file you chose**, in a *DragWheel shares* folder in your cloud. Who can open the link is set in the cloud's Share window. DragWheel deletes the copy when the time you chose runs out. |
| **Send to phone → Same Wi-Fi** | While the window is open | Nothing on the internet; your phone downloads from this PC over your own network | The file you chose, to your phone |
| **Send to phone → Quick Share / Bluetooth** | When you choose them | Handled by Google Quick Share or Windows' Bluetooth sender | The file you chose, to your phone |
| **Crash reports** | **Off by default.** If you turn them on, DragWheel shows you the full report and asks first | Nothing is sent by DragWheel. *Send report* opens a GitHub issue page in your browser, where you can read and change the report before you post it. | Only what you post. Your Windows user name is removed from the report. |

Every service above, like any website, receives your IP address as part of the connection. See its own privacy policy for what it keeps.

## Files and logs on your computer

- Converted files are saved next to the originals (or where you choose in Settings).
- Settings are stored in the Windows registry under `HKEY_CURRENT_USER\Software\DragWheel`.
- A troubleshooting log is kept at `%LOCALAPPDATA%\DragWheel\dragwheel.log`, and crash details in `%LOCALAPPDATA%\DragWheel\crash`. They stay on your computer.
- Links you play in Float are remembered in your settings (right-click a float → *Saved links* → *Clear the list* removes them).

Uninstalling DragWheel removes the program, its settings and its Explorer integration.

## DragWheel for Browser

DragWheel for Browser is the optional extension for Chrome, Edge, Brave and Firefox. **It collects no data and sends nothing to the developer or to any server.**

- It talks only to the DragWheel app on your own computer, through the browser's *native messaging*.
- **Play in DragWheel Float:** when you choose it, the address of the video, song, link or page you clicked is passed to DragWheel on your PC, which plays it the way a browser would.
- **Save image as…:** when you choose it, the extension reads that one picture from the page (the same file your browser already loaded) and passes it to DragWheel on your PC, which saves it in the format you picked in your Downloads folder.
- It runs only when you click one of its menu items or its toolbar button. It doesn't read, record or track the pages you visit, and keeps no history.
- It asks for access to all websites only so those right-click items work on any site you choose to use them on.
- No analytics, no advertising, no remote code. Nothing is sold or shared.

## Contact

Questions: open an issue at https://github.com/ilukezippo/DragWheel/issues
