# DragWheel privacy policy

_Last updated: October 2026 (DragWheel 1.2)_

DragWheel converts and processes files **entirely on your own computer**. Conversions and tools never upload your files, and DragWheel does not collect usage statistics, telemetry or any personal data.

A few features need the internet. Each one connects **only when you use it**, and only to the service named below.

## Connections DragWheel makes, and when

| Feature | When | What is contacted | What is sent |
|---|---|---|---|
| **Update check** | At most once a day, or when you click *Check for updates*. Can be turned off. | `api.github.com` (this project's releases) | A standard HTTPS request. No files or personal data. |
| **Downloading an update** | Only when you click *Download & install* | GitHub Releases of this project | — |
| **One-time downloads** (AI background removal model, speech-to-text model, the link reader *yt-dlp*) | Only the first time you use the feature, after you agree | GitHub and Hugging Face | — |
| **Play a link in Float** | When you play a copied link | The website the link points to (for example YouTube), the way a browser would | The link |
| **Send to phone → Internet link** | Only when you choose it and click *Upload* | One free temporary file service (litterbox.catbox.moe, 0x0.st, tmpfiles.org or uguu.se) | **The file you chose.** Anyone with the link can download it until the service deletes it (5 minutes to 72 hours). |
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

## Contact

Questions: open an issue at https://github.com/ilukezippo/DragWheel/issues
