# Releasing, code signing and the Microsoft Store

## 1. Code signing with SignPath (free for open source)

Signing removes the "Windows protected your PC" SmartScreen warning over time and is required for the Microsoft Store.
Everything on the DragWheel side is ready: the GitHub workflow signs `DragWheel.exe` and the installer automatically
**as soon as the settings below exist**. Until then it builds unsigned exactly as before.

**What only you can do (one time):**

1. Apply at **https://signpath.org/apply** (SignPath Foundation, free for OSI-licensed projects — DragWheel is MIT).
   They check the repository: public source, a release built by GitHub Actions, and the *Code signing policy* section
   in the README (already there).
2. When they accept the project, in SignPath:
   - create the project with the slug **`DragWheel`**,
   - add two artifact configurations, pasting the files from this repository:
     - **`app`** ← `.signpath/artifact-configurations/app.xml`
     - **`installer`** ← `.signpath/artifact-configurations/installer.xml`
   - use (or create) the signing policy **`release-signing`**, and link the GitHub repository as a trusted build system.
3. In GitHub → repository **Settings → Secrets and variables → Actions**:
   - **Variable** `SIGNPATH_ORGANIZATION_ID` = your SignPath organization ID
   - **Secret** `SIGNPATH_API_TOKEN` = a SignPath API token for a CI user that may submit signing requests
   - (only if you chose other names) variables `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_POLICY_SLUG`

From then on every build waits for the signing request (you approve release signing in SignPath, as the policy says)
and publishes signed files. The release notes stop mentioning SmartScreen by themselves.

## 2. Microsoft Store listing (free for individual developers)

The Store accepts DragWheel's normal installer ("MSI or EXE app"), so nothing changes in the app.

**Needs first:** the installer must be **code-signed** (section 1).

**What only you can do:**

1. Create a free individual developer account: **https://storedeveloper.microsoft.com** (sign in with a Microsoft account, identity check).
2. In Partner Center → **Apps and games → New product → EXE or MSI app**, reserve the name **DragWheel**.
3. **Packages:**
   - Package URL: `https://github.com/ilukezippo/DragWheel/releases/download/v1.2.0/DragWheel-Setup-1.2.0.exe`
     (a versioned link — it never changes for that version, which the Store requires)
   - Architecture: **x64** · Installer type: **EXE** · Silent install switch: **`/S`**
   - Languages: English, Arabic (the installer's own languages)
4. **Properties:** category *Productivity* (sub-category *File managers* or *Utilities & tools*);
   privacy policy URL `https://github.com/ilukezippo/DragWheel/blob/main/PRIVACY.md`; support `https://github.com/ilukezippo/DragWheel/issues`.
5. **Age rating:** fill the questionnaire (no user-generated content, no purchases; it can play web links).
6. **Store listing** — text below, plus 4–10 screenshots at 1920×1080 (wheel open, Float playing, Settings, a PDF tool).
7. Submit. Certification usually takes a few days. For each new version, update the package URL to the new release.

### Store listing text (English)

**Short description:** Drag a file, tap a key, drop it on the wheel — convert and fix files in seconds, offline.

**Description:**
DragWheel turns every file drag into a quick menu. Start dragging any file, tap Shift and a wheel of options opens
right under your mouse; drop the file on a slice and it's done — the result lands next to the original.

• Convert images, video, audio, documents, PDFs, e-books, comics, fonts, subtitles and archives
• Tools: compress, crop & resize, remove background (AI, offline), blur faces, trim, extract audio, merge, sign and arrange PDFs, watermark and more
• Float: keep any picture, video, song or YouTube link on top of your work as a mini player
• Send to phone with Quick Share, Bluetooth or a temporary link with a QR code
• Make it yours: presets, chains, your own commands, watch folders, a command line
• Works offline. Your files never leave your PC unless you choose to send one.
• English and Arabic, plus 11 more languages.

**Keywords:** file converter, convert, compress, pdf, heic to jpg, video converter, offline, drag and drop

### نص المتجر (العربية)

**وصف قصير:** اسحب ملفًا، اضغط مفتاحًا، أفلته على العجلة — حوّل الملفات وأصلحها في ثوانٍ، دون إنترنت.

**الوصف:**
يحوّل DragWheel كل عملية سحب لملف إلى قائمة سريعة. ابدأ بسحب أي ملف واضغط Shift فتظهر عجلة الخيارات تحت الماوس مباشرة؛
أفلت الملف على شريحة وانتهى الأمر — تُحفظ النتيجة بجانب الملف الأصلي.

• تحويل الصور والفيديو والصوت والمستندات وملفات PDF والكتب الإلكترونية والقصص المصوّرة والخطوط والترجمات والأرشيفات
• أدوات: ضغط، قص وتغيير حجم، إزالة الخلفية (ذكاء اصطناعي دون إنترنت)، تمويه الوجوه، تقطيع، استخراج الصوت، دمج وتوقيع وترتيب صفحات PDF، علامة مائية والمزيد
• النافذة العائمة: أبقِ أي صورة أو فيديو أو أغنية أو رابط يوتيوب فوق عملك كمشغّل صغير
• إرسال إلى الهاتف عبر Quick Share أو البلوتوث أو رابط مؤقت مع رمز QR
• اجعله على ذوقك: إعدادات مسبقة، سلاسل، أوامرك الخاصة، مجلدات مراقبة، سطر أوامر
• يعمل دون إنترنت. لا تغادر ملفاتك جهازك إلا إذا اخترت إرسال أحدها.
