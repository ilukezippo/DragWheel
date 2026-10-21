# DragWheel privacy policy

_Last updated: October 2026_

DragWheel converts and processes files **entirely on your own computer**. Your files are never uploaded, and DragWheel does not collect, store or send any personal data, usage statistics or telemetry.

## The only network connection: the update check

DragWheel can check whether a newer version has been released:

- **What is contacted:** the public GitHub API, `https://api.github.com/repos/ilukezippo/DragWheel/releases/latest`.
- **When:** at most once a day while DragWheel is running, or when you click **Check for updates**.
- **What is sent:** a standard HTTPS request with the user agent `DragWheel-updater`. No files, file names, personal data or identifiers are sent. GitHub, like any web server, receives your IP address as part of the connection; see [GitHub's privacy statement](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement).
- **Downloading an update:** only when you click **Download & install**, the new installer is downloaded from this repository's GitHub Releases page.
- **How to turn it off:** Settings → About → uncheck **Check for updates automatically**. With it off, DragWheel makes no network connections at all unless you click **Check now**.

## Files and logs on your computer

- Converted files are saved next to the originals (or in the folder you choose in Settings).
- Settings are stored in the Windows registry under `HKEY_CURRENT_USER\Software\DragWheel`.
- A small troubleshooting log is kept at `%LOCALAPPDATA%\DragWheel\dragwheel.log`. It stays on your computer and is never sent anywhere.

Uninstalling DragWheel removes the program, its settings and its Explorer integration.

## Contact

Questions: open an issue at https://github.com/ilukezippo/DragWheel/issues
