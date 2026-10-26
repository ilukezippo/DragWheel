# Changelog

## 1.2.1 — October 2026

- **Float and Quick preview show documents:** PDFs, e-books, comics, Word (DOC, DOCX, RTF, ODT), Excel, PowerPoint, text, Markdown, HTML and CSV files show their first page instead of an icon
- Quick preview follows the pointer while you drag
- **PDF to Word that looks the same:** every line stays where it was, in the same font, size and weight, tables become real Word tables, and lines, logos and pictures stay behind the text; Arabic is written as proper right-to-left text you can edit
- A second **PDF to Word (flowing text)** slice keeps the old way, for documents you want to rewrite freely (Microsoft Word's own PDF import when Word is installed)
- **Animation speed** slider next to the wheel animation in Settings (opening and closing)
- New subtle sounds when the wheel opens and closes (with the click sounds and their volume)
- Changing the language or theme in Settings fades smoothly instead of flashing
- **Rename saved links** (right-click a float → Saved links): rename the one playing, or rename, reorder and remove them all in *Manage saved links…*
- An empty float: *Open* and double-click choose a file (the window now comes to the front); *Show in Explorer* and *Copy path* only show when something is open
- Fixed: pressing the wheel key again sometimes reopened the wheel instead of closing it, especially with a key set to None
- Fixed: a crash repeating many times a second is written to the log only once

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
