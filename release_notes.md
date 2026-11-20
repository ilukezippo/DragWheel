**Drag a file, tap a key, drop it on the wheel.** Offline file converter and toolbox for Windows.

**Install:** download `DragWheel-Setup-1.2.3.exe` below and run it (asks for admin, installs to `C:\Program Files\DragWheel`).
The installer is not code-signed yet, so Windows may warn: if Edge holds the download, choose *… → Keep → Show more → Keep anyway*; if SmartScreen warns when you run it, choose *More info → Run anyway*.

**Portable:** `DragWheel-Portable-1.2.3.zip` — unzip anywhere and run `DragWheel.exe`.

Requires Windows 10 (1809+) or 11, 64-bit.

## What's new in 1.2.3

#### New
- **Sticky notes** on the desktop: right-click the desktop → DragWheel → *New sticky note* (or the tray). They save themselves as you type (plain .txt files in Documents › DragWheel Notes), six colours, Keep on top, bigger or smaller text, and they come back when DragWheel starts. Floating a .txt, .md or .log file opens it as a note you can edit. ⋯ → *Keep notes in* moves them to OneDrive, Google Drive or any folder so they follow you to your other PCs; *Show all notes* opens every one
- **DragWheel for Browser** (Chrome Web Store and Firefox Add-ons): right-click a video, song or link → *Play in DragWheel Float*; right-click a picture → *Save image as* PNG, JPG, WebP, AVIF, ICO, PDF and more. The installer's *Browser extension* option adds it to Chrome, Edge and Brave the way IDM does (the browser asks once to turn it on); Firefox opens its add-on page once
- **Right-click a file → DragWheel: Convert ▸ / Tools ▸ / Actions ▸**, with the slices of your wheels for that kind of file
- **Floats stay open after a restart** until you close them, at the same place and size, with videos waiting where they were
- **Float name and icon**: right-click an app, folder or shortcut float → *Name and icon*: show or hide the name, *Auto hide name*, rename it, font, size and colour, or *Change icon…* (any picture, .ico or a program's icon). Shortcut floats show the big icon Explorer shows, including icons you set in a shortcut's Properties
- **Keep aspect ratio** on/off for picture and video floats: off, resize them to any shape
- A video or song playing in a Float shows its progress on the taskbar button
- **Crop & Resize**: an *Image sizes* list with printable sizes (wallet, passport, 4×6, 5×7, 8×10, Letter, A4…): it crops to that size the way the picture faces and saves it at 300 dpi, ready to print. And an **Overwrite** button next to *Save copy* (the original goes to the Recycle Bin)
- **Trim…** shows the part you keep, like Ringtone: drag its edges on the sound wave, scroll to zoom, and press Play to hear it. Videos also show the picture at the edge you drag and play the part with sound. Any length (several files at once still use Start and End)
- **Flip horizontal** and **Flip vertical** for videos (Tools wheel)
- New sound packs: Xbox, PlayStation and Steam
- Settings → About: *Star on GitHub*; after 20 jobs a small window asks once whether you'd like to star DragWheel

#### Fixed
- Float: playing a web video again after a long pause no longer asks the site again (about 14 s) while its link is still good for a while; the player restarts on the same link at once
- A Float playing through a headset went silent when Windows switched to another output (speakers, or the headset turned off): the sound now moves to the new device
- *Original* in Crop & Resize now goes back to the whole picture, not just its shape
- Freezes: starting a long online video (the temp file is reserved instantly), a video stuttering while the mouse was over its Float, the wheel keys and Float settings read from the registry many times a second, the Settings window looking through the Temp folder and searching for LibreOffice
- 64-bit Windows: big icons failing to load for app and shortcut Floats
- Playing a video from the browser extension no longer fails (DragWheel was started in System32)
- No duplicate Floats after an update; a video paused for hours starts fresh in the same window
- A pinned Float of a file that was deleted is forgotten instead of being looked for at every start
- The freeze log ignores the PC sleeping, and old crash reports are tidied (the newest 20, under 30 days)

