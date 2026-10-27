# Changelog

## 1.2.1 — October 2026

- **Key + click for a wheel key:** hold a key and click while setting a wheel key, e.g. Ctrl + right click; the click goes to DragWheel instead of opening Explorer's menu (right clicks work while dragging a file; left clicks with Mouse hover and File selection)
- **File preview opens** (Settings → Wheel): *Press to open, press again to close* or *Hold to show, let go to close*
- **Custom Slices** (was Your own slices, now under Wheel slices): add a slice that opens files in any app — browse for the app, pick which files it shows for, no commands to type (the slices file is still there under *Advanced…*)
- **Auto Convert** window has a **Save result as** choice: *Copy* (into a Converted folder, as before) or *Overwrite original* (the new file takes the original's place; the original goes to the Recycle Bin)
- **Three more sound styles:** Velvet, Crystal and Pulse
- **The installer speaks every language DragWheel does:** French, Spanish, German, Italian, Portuguese, Turkish, Russian, Persian, Urdu, Hindi, Japanese and Chinese join English and Arabic, and the app starts in the language you pick there
- **Any key or combination for each wheel:** click a wheel's key box and press what you like (Shift, Ctrl+Q, F8, the mouse's side buttons…); a key that is also part of a longer combination counts when you let it go; File preview (Space) has its own key box too
- **Mouse Control** on the Wheel page: Mouse Shake, Scroll Wheel and Loading Spin with on/off switches and a line about each; choose whether a shake or a scroll opens Convert, Tools, Actions or File preview
- Clearer names in Settings: *Wheel keys*, *Jobs*, *Auto Convert* (was Watch folders), *Startup*, *Enable notification sound*, *Enable wheel sound*, and an *Animations* section; every option is now an on/off switch
- **Trigger on** has new choices: *File drag (recommended)*, *Mouse hover* (point at a file in Explorer or on the desktop and tap the key) and *File selection* (select files and tap the key); the wheel keys and File preview follow the choice you make, and this replaces Ctrl + Alt + Space
- A key can belong to only one wheel: giving it to another one sets the first to None
- **Opening and closing animation** can be different (Settings → Wheel → Animations), with six new styles: Zoom, Pop, Drop, Rise, Flip and Swirl
- **Six new themes:** Midnight, Ocean, Forest, Grape, Rose and Sand, each with its own accent colour
- **Show in taskbar:** each float gets a taskbar button, so it's easy to get back to (Settings → Float)
- Shorter Float options: *Play files and links instantly*, *Always on top*, *Ctrl+Enter opens a file in Float*, *Stop playing while loading*, *Remove float border*, *Enable multimedia logos on screen*
- **Right-click menu** in Settings → General: the context menu, Send To and the Windows 11 context menu are separate switches
- The wheel's buttons show the key under the wheel's name, so long names (like the mouse's side buttons) fit; the welcome tour fits them too
- **New Settings layout:** clear pages down the side (General, Wheel, Sounds & notifications, Files & jobs, Float, Customize, Advanced, About) with each section on its own card, new page icons and bolder page names; Segoe UI everywhere, more room next to tick boxes, buttons no longer stay lit after you click them, and lists show one clean highlight
- **Actions for all file types at once:** in Customize → Choose slices, the Actions wheel can be arranged once for every type of file
- "Last checked" for updates shows the time with AM/PM
- **MKV H.264 and MKV H.265** (smaller) instead of a single MKV slice
- **DOC, XLS and PPT** for older Office: Word, Excel and PowerPoint files can be saved in the 97–2003 formats
- **Float and Quick preview show documents:** PDFs, e-books, comics, Word (DOC, DOCX, RTF, ODT), Excel, PowerPoint, text, Markdown, HTML and CSV files show their first page instead of an icon
- Quick preview follows the pointer while you drag
- **PDF to Word that looks the same:** every line stays where it was, in the same font, size and weight, tables become real Word tables, and lines, logos and pictures stay behind the text; Arabic is written as proper right-to-left text you can edit
- A second **PDF to Word (flowing text)** slice keeps the old way, for documents you want to rewrite freely (Microsoft Word's own PDF import when Word is installed)
- **Animation speed** slider next to the wheel animation in Settings (opening and closing)
- **Sound styles** for the wheel (Settings → Sounds & notifications): Classic, Soft, Glass, Bubble, Mechanical and Retro, each with its own open, close, click and choose sounds, and a Listen button
- New subtle sounds when the wheel opens and closes (with the click sounds and their volume, shown as a percentage)
- Changing the language or theme: Settings fades out, changes, and fades back in (no flash)
- **Unblock** on the Actions wheel: removes Windows' "This file came from another computer" mark from downloaded files (and everything inside a folder)
- **Drag a web page into a float:** drag the site icon from the browser's address bar (or a link or tab) onto a float to play that video there
- **Paste a file into a float:** copy a video or song in Explorer (Ctrl+C) or "Copy as path", then press Ctrl+V on a float to play it
- **Restore defaults** in Settings → Advanced → Settings Config (was "Move your setup to another PC"), next to Export and Import; your saved links, presets, chains and own slices are kept
- **Open the log** and **Show the log folder** at the bottom of Settings → Advanced → Help
- **Saved links are yours to choose:** links are saved only when you add them (*Save this link* on a float, or *Add…* in Manage saved links); the menu shows your last five, all of them in *Manage saved links…*, where you can rename, reorder, add, remove or clear them
- **Recently played:** a new list on the float's menu with the links and files you played, to play again, save, or remove
- *Play copied link* is now called *Paste link* (and *Paste link to Float* on the desktop's right-click menu)
- **Playback speed** for videos and music in Float (right-click → Speed: 0.5× to 2×)
- Folders, programs and other files in Float show just their icon and name (in bold, without the extension, sized with the icon; *Hide name* hides it) — no background, frame or highlight, even when you point at them (can be turned off in Settings → Float)
- An empty float: *Open* and double-click choose a file (the window now comes to the front); *Show in Explorer* and *Copy path* only show when something is open
- Fixed: pressing the wheel key again sometimes reopened the wheel instead of closing it, especially with a key set to None
- **JPEG** slice next to JPG for pictures (same format, .jpeg name); Settings → Wheel slices lists every format of a type
- Fixed: right-clicking many files at once (Explorer starts DragWheel once per file) now gathers all of them into one wheel, and a slice you already chose is applied to files that arrive late; Unblock also handles very long paths and read-only files
- Fixed: choosing a saved link could play a different one (the link on the clipboard), and a renamed live link showed the video's own title again; the same fix applies to Recent results and the QR menu in the tray
- **Smoother live streams:** live videos now come from YouTube's mobile-web player first, whose live stream keeps playing (the stream used before was refused by YouTube every ~30 seconds); other players are asked at the same time, so if YouTube starts refusing one, the float switches to another in a moment instead of reloading for 12 seconds; the stream is also fetched one request at a time after a refusal, and reconnects by itself after network hiccups
- Fixed: the wheel couldn't be used while Settings was open
- Fixed: resizing a float past its smallest or largest size moved it around instead of stopping
- Fixed: moving a dragged file quickly over the wheel could freeze DragWheel for a few seconds (the click sounds now play without Qt's audio engine)
- Fixed: links reopened after an update or at Windows start were not added to Saved links
- Fixed: right-clicking a float playing a link could fail (Repeat menu)
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
