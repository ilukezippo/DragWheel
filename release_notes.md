**Drag a file, tap a key, drop it on the wheel.** Offline file converter and toolbox for Windows.

**Install:** download `DragWheel-Setup-1.2.2.exe` below and run it (asks for admin, installs to `C:\Program Files\DragWheel`).
The installer is not code-signed yet, so Windows may warn: if Edge holds the download, choose *… → Keep → Show more → Keep anyway*; if SmartScreen warns when you run it, choose *More info → Run anyway*.

**Portable:** `DragWheel-Portable-1.2.2.zip` — unzip anywhere and run `DragWheel.exe`.

Requires Windows 10 (1809+) or 11, 64-bit.

## What's new in 1.2.2

#### New tools
- **Read QR code on screen** (tray menu and the desktop's right-click menu): the QR codes on your screens light up; click one, or drag a box around a small one, and DragWheel shows what it says — open a link, copy text, or copy a Wi-Fi password. Pictures get a *Read QR code* action too. Works offline
- **Fix alignment…** for photos of documents, like a scanner app: DragWheel finds the page's edges and corners (even on a white table), you drag any corner or side with a magnifier showing exactly where, rotate left or right, and see a live preview of each look — clean document, original colours, black & white or grayscale. Several pictures at once are straightened automatically

#### Send to phone
- **Two new ways:** *Link from this PC* makes a link that works on any network, served straight from this PC through a free Cloudflare tunnel while the window is open (nothing is uploaded); *Cloud link* puts a copy in your OneDrive, Google Drive, iCloud Drive, Dropbox or Box and uses its own Copy link, so the link works even when this PC is off (the copy is deleted when the time you choose runs out)
- **Redone windows:** an icon for each way with a short line under it, ‹ Back at the top left to pick another way, a space for the QR code with a spinning wheel inside it until the link is ready (with the upload percentage), and clear main buttons; click a QR code to copy its link
- **Same file, same QR code:** choosing Internet link or Cloud link again for a file that's already shared shows the link you made, with the time left and *New link* if you want a fresh one
- **Stop sharing?** Closing a window with X or Back while something is shared asks whether to stop or keep sharing (the *Stop sharing* button just stops); shares that are still going are listed in the tray under *Send to phone — show QR code*
- **Choose the file service** for an internet link: Automatic (Litterbox, then 0x0.st, then uguu.se, which all give the file itself), one of them, or tmpfiles.org with a warning about the ads and pop-ups on its download page; each shows the link times it offers
- A service that refuses your network is skipped straight away instead of uploading half the file first; when an upload fails, the message says what each service did
- Programs go as *Name.zip* (not *Name.exe.zip*, which some services refuse) and files are sent with their real type
- Cloud link lists every cloud it supports (one that isn't set up offers to get it) and finds Google Drive in any of its setups
- The windows come to the front when they open but no longer stay on top of everything

#### Float and Settings
- **Smoother with a video playing:** Settings is prepared one page at a time in the background and opens at once, Send to phone looks for clouds and network addresses in the background, and DragWheel notes in its log anything that holds it up for a moment
- **Reopen** on the float's right-click menu: closes it and opens it again at the same size and place, with the same file or link, from the same point
- **Floats that open with Windows** come back at the same place and size
- **Playing again after a long break:** a video paused for more than 10 minutes (or overnight) reopens fresh when you press play, instead of the sound coming back with a frozen picture
- **Settings Config exports everything:** every option, your keys, slices, presets, chains, Custom Slices, Auto Convert folders and saved links, plus starting with Windows and the right-click menus
- The installer can download every extra ahead of time (Remove background, Transcribe, Paste link to Float and Link from this PC), all optional
- Windows 11: the right-click option is now called *Use the full right-click menu (like Windows 10)*, which is what it does — Windows' short menu only takes signed, packaged apps

#### Fixed
- A PDF you'd used in Manage pages, Sign, Watermark or another PDF tool stayed locked until DragWheel was closed, so it couldn't be renamed or deleted

