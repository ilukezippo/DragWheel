# Changelog

## 1.2.2 — November 2026

### New tools
- **Read QR code on screen** (tray menu and the desktop's right-click menu): the QR codes on your screens light up; click one, or drag a box around a small one, and DragWheel shows what it says — open a link, copy text, or copy a Wi-Fi password. Pictures get a *Read QR code* action too. Works offline
- **Fix alignment…** for photos of documents, like a scanner app: DragWheel finds the page's edges and corners (even on a white table), you drag any corner or side with a magnifier showing exactly where, rotate left or right, and see a live preview of each look — clean document, original colours, black & white or grayscale. Several pictures at once are straightened automatically

### Send to phone
- **Two new ways:** *Link from this PC* makes a link that works on any network, served straight from this PC through a free Cloudflare tunnel while the window is open (nothing is uploaded); *Cloud link* puts a copy in your OneDrive, Google Drive, iCloud Drive, Dropbox or Box and uses its own Copy link, so the link works even when this PC is off (the copy is deleted when the time you choose runs out)
- **Redone windows:** an icon for each way with a short line under it, ‹ Back at the top left to pick another way, a space for the QR code with a spinning wheel inside it until the link is ready (with the upload percentage), and clear main buttons; click a QR code to copy its link
- **Same file, same QR code:** choosing Internet link or Cloud link again for a file that's already shared shows the link you made, with the time left and *New link* if you want a fresh one
- **Stop sharing?** Closing a window with X or Back while something is shared asks whether to stop or keep sharing (the *Stop sharing* button just stops); shares that are still going are listed in the tray under *Send to phone — show QR code*
- **Choose the file service** for an internet link: Automatic (Litterbox, then 0x0.st, then uguu.se, which all give the file itself), one of them, or tmpfiles.org with a warning about the ads and pop-ups on its download page; each shows the link times it offers
- A service that refuses your network is skipped straight away instead of uploading half the file first; when an upload fails, the message says what each service did
- Programs go as *Name.zip* (not *Name.exe.zip*, which some services refuse) and files are sent with their real type
- Cloud link lists every cloud it supports (one that isn't set up offers to get it) and finds Google Drive in any of its setups
- The windows come to the front when they open but no longer stay on top of everything

### Float and Settings
- **Smoother with a video playing:** Settings is prepared one page at a time in the background and opens at once, Send to phone looks for clouds and network addresses in the background, and DragWheel notes in its log anything that holds it up for a moment
- **Reopen** on the float's right-click menu: closes it and opens it again at the same size and place, with the same file or link, from the same point
- **Floats that open with Windows** come back at the same place and size
- **Playing again after a long break:** a video paused for more than 10 minutes (or overnight) reopens fresh when you press play, instead of the sound coming back with a frozen picture
- **Settings Config exports everything:** every option, your keys, slices, presets, chains, Custom Slices, Auto Convert folders and saved links, plus starting with Windows and the right-click menus
- The installer can download every extra ahead of time (Remove background, Transcribe, Paste link to Float and Link from this PC), all optional
- Windows 11: the right-click option is now called *Use the full right-click menu (like Windows 10)*, which is what it does — Windows' short menu only takes signed, packaged apps

### Fixed
- A PDF you'd used in Manage pages, Sign, Watermark or another PDF tool stayed locked until DragWheel was closed, so it couldn't be renamed or deleted

## 1.2.1 — October 2026

### Wheel and keys
- **Any key or combination for each wheel:** click a wheel's key box and press what you like (Shift, Ctrl+Q, F8, the mouse's side buttons…), or hold a key and click (e.g. Ctrl + right click — the click goes to DragWheel instead of opening Explorer's menu); a key can belong to only one wheel
- **Trigger on:** *File drag (recommended)*, *Mouse hover* (point at a file in Explorer or on the desktop and tap the key) or *File selection* (select files and tap the key); this replaces Ctrl + Alt + Space
- **File preview** has its own key (Space) and opens with a press or only while you hold it; it shows PDFs, e-books, comics, Word, Excel, PowerPoint, text, Markdown, HTML and CSV files, and follows the pointer while you drag
- **Mouse Control:** Mouse Shake, Scroll Wheel and Loading Spin with on/off switches; choose whether a shake or a scroll opens Convert, Tools, Actions or File preview
- **Animations:** separate opening and closing styles, six new ones (Zoom, Pop, Drop, Rise, Flip, Swirl) and a speed slider
- **Sound styles:** Classic, Soft, Glass, Bubble, Mechanical, Retro, Velvet, Crystal and Pulse, with new open and close sounds, a Listen button and the volume shown as a percentage
- The wheel's buttons show their key under the wheel's name

### Converting and file tools
- **PDF to Word that looks the same:** every line stays where it was, in the same font and size, tables become real Word tables, pictures stay in place, and Arabic is proper right-to-left text; *PDF to Word (flowing text)* keeps the old way
- **New formats:** MKV H.264 and MKV H.265, JPEG next to JPG, and DOC, XLS and PPT for older Office
- **Unblock** on the Actions wheel removes Windows' "This file came from another computer" mark from downloads (whole folders too, any size)
- **Custom Slices:** open files in any app from the Actions wheel — browse for the app and pick which files it's for
- **Auto Convert** (was Watch folders): save the result as a copy or overwrite the original
- **Actions for every file type at once** in Customize → Choose slices
- **No more freezing on big jobs:** Unblock, Move to… and Copy to… run in the background with progress and Cancel

### Float
- **Saved links are yours to choose:** saved only when you add them; rename, reorder, add, remove or clear them in *Manage saved links…*; the menu shows the last five
- **Recently played:** the links and files you played, to play again, save or remove
- **Playback speed** from 0.5× to 2×
- **Drag a web page** (the icon in the browser's address bar, a link or a tab) onto a float to play it, or **paste** a copied video or song with Ctrl+V
- **Show in taskbar** gives each float a taskbar button
- Folders, programs and other files show just their icon and name, without a frame (*Hide name* hides the name)
- **Smoother live streams** that switch YouTube player instead of stalling, and expired video links are renewed and continue from the same spot
- *Paste link* (was *Play copied link*), also *Paste link to Float* on the desktop's right-click menu

### Settings and setup
- **New Settings layout:** pages down the side (General, Wheel, Sounds & notifications, Files & jobs, Float, Customize, Advanced, About), each section on its own card, Segoe UI everywhere and on/off switches for every option
- **Six new themes:** Midnight, Ocean, Forest, Grape, Rose and Sand
- **Right-click menu:** the context menu, Send To and the Windows 11 menu are separate switches
- **Settings Config:** Export, Import and **Restore defaults** (keeps your saved links, presets, chains and slices); **Open the log** in Help
- The wheel works while Settings is open; changing language or theme fades instead of flashing
- **The installer speaks all 14 of DragWheel's languages,** and the app starts in the language you pick there
- "Last checked" for updates shows AM/PM

### Fixed
- Pressing the wheel key again sometimes reopened the wheel instead of closing it
- Right-clicking many files at once now gathers them into one wheel
- Choosing a saved link could play a different one
- Moving a dragged file quickly over the wheel could freeze DragWheel for a few seconds
- Resizing a float past its smallest or largest size moved it around
- An empty float: *Open* and double-click now choose a file
- Links reopened after an update or at Windows start weren't added to Saved links
- Right-clicking a float playing a link could fail
- A crash repeating many times a second is written to the log only once

## 1.2.0 — October 2026

The biggest update so far.

### The wheel
- **Animations** when the wheel opens and closes: Bloom (the middle pops, then the slices open one by one like a flower), Circle, Fade, Spin or none
- **Shake the mouse** while dragging to open the wheel; wheel keys can be set to **None** for shake only
- Pressing the same key again **closes the wheel** (also Ctrl + Alt + Space)
- The wheel always stays **fully on screen**, even at the edges and corners
- **Quick preview:** tap Space while dragging to see the picture, PDF page, video frame or text you're holding
- **Click sounds** like an iPod: a tick when moving between slices and a press when choosing one, with their own volume
- Roomier wheels when there are many slices

### Make it yours
- **Choose slices:** hide slices and drag them into your order for every wheel and file type, with a live preview of the wheel
- **Presets** (for example *WebP · quality 80 · max 1920 px*) and **chains** (for example *resize → WebP → ZIP*) as one slice
- **Your own slices:** add commands to the Actions wheel in a simple settings file
- **Where results go:** next to the original, in a folder, replacing the original (asks first, originals to the Recycle Bin) or on the clipboard
- **Export and import** your settings to move them to another PC

### PDF
- **Sign** with a drawn or dropped signature, on this page, every page, a range or the pages you click
- **Arrange pages** by dragging; drop more PDFs or pictures to add pages
- **Watermark** with a live preview, direction, size, strength and colour; page numbers (Arabic numerals too)
- Grayscale, unlock, word count, PDF to CBZ

### Images, video and audio
- Images: resize presets, **remove background** (AI, offline, downloaded once), copy text (Windows OCR), upscale 2×, sharpen, watermark, **blur faces**, stitch, make GIF
- Video: compress to a target size, crops for Reels/TikTok/Stories centred on faces, burn or add subtitles, extract subtitles, make GIF, progress percentage on long jobs
- Audio: ringtone maker with a waveform trimmer (M4R/MP3), **speech to text** in many languages including Arabic (AI, offline)

### Files and archives
- Comic books: CBR, CBZ, CB7, CBT to PDF or CBZ, extract pages, make a CBZ from pictures
- Batch rename (numbers, dates, Arabic or Western numerals), split big files into parts and join them, password-protected ZIP and 7Z
- SHA-256 checksum with compare, secure shred, fonts (convert and install), fix garbled Arabic text

### Float, the mini player
- Plays video and music with fading controls, volume, audio tracks and subtitles; previous/next file; album covers
- **Play links** from YouTube and about 1,800 sites, live streams included, with a quality menu, Refresh and a loading circle
- **Repeat** this one or **loop** the whole folder (R key)
- **Saved links:** every link you play is remembered (right-click a float)
- **Open Float** from the desktop right-click menu: an empty float to drop a file or paste a link into
- Media keys control the float, with a big on-screen sign for play, pause, next, previous and the volume
- Always on top (optional), floats that reopen with Windows and after updates, Ctrl + double-click or Ctrl + Enter on a file opens it in Float

### Send to phone
- **Quick Share**, **Bluetooth**, a temporary **internet link with a QR code** (5 minutes to 72 hours) or the same Wi-Fi
- The QR code of a live link can be shown again from the tray until it runs out
- Programs are sent inside a ZIP, because file services refuse them

### Everyday
- **Recent results** in the tray menu, **Undo** on the Done notification
- **A queue** for many jobs (or all at the same time), with a "12 of 40 done" counter; one bad file doesn't stop a batch
- **Watch folders:** files that land in a folder are converted by themselves
- **Command line:** `dragwheel convert *.heic --to jpg`, and a button in Settings to open it
- **Welcome tour** with an animation (can show at every start or never)
- Notifications fade like Windows' own and come back when you hover; Windows notification sounds when jobs finish or fail
- A small spinning circle next to the pointer while DragWheel works
- High-contrast theme, screen-reader names for the wheel and notifications
- Windows 11: switch for the full right-click menu (no "Show more options")
- Left-click the tray icon opens Settings; Settings scrolls on small screens

### Install, trust and privacy
- **Smaller installer** (97 MB instead of 127 MB) and **optional downloads** to tick during setup (AI models, yt-dlp)
- Setup detects the same version and offers to reinstall or uninstall; uninstalling can keep or remove your settings and downloads
- Optional **crash reports**: off by default, you see the whole report before anything is sent
- Updated **privacy policy** listing every connection and when it happens
- Ready for code signing (SignPath) and the Microsoft Store

### Fixes
- Smoother online video and live streams (download-ahead cache, live relay with quick recovery, switching away from refused streams)
- No more Windows error sound with every notification
- Floats come to the front when you open them; reopened floats show instantly after an update

## 1.1.0 and 1.0.0

See the [1.1.0](https://github.com/ilukezippo/DragWheel/releases/tag/v1.1.0) and [1.0.0](https://github.com/ilukezippo/DragWheel/releases/tag/v1.0.0) release pages.
