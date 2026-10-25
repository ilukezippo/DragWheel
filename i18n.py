"""Translations. Strings are keyed by their English text; anything missing falls back to English."""
from __future__ import annotations

LANGUAGES = [("en", "English"), ("ar", "العربية"), ("fr", "Français"), ("es", "Español"),
             ("tr", "Türkçe"), ("de", "Deutsch")]
RTL = {"ar"}

_lang = "en"


def set_language(code: str | None):
    """code '' / None = follow Windows."""
    global _lang
    if not code:
        try:
            from PySide6.QtCore import QLocale
            code = QLocale.system().name()[:2]
        except Exception:
            code = "en"
    _lang = code if code in T or code == "en" else "en"


def language() -> str:
    return _lang


def is_rtl() -> bool:
    return _lang in RTL


def ui_font() -> str:
    """Font family for the interface (Segoe UI covers Arabic, Persian, Urdu, Hindi, CJK fall back automatically)."""
    return "Segoe UI"


def css(sheet: str) -> str:
    """Fill a stylesheet template with the current theme colours (and font)."""
    import theme
    return theme.sheet(sheet).replace("'Segoe UI'", f"'{ui_font()}'")


def tr(text: str, **kw) -> str:
    s = T.get(_lang, {}).get(text) or EN.get(text) or text
    if kw:
        try:
            s = s.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return s


EN = {
    "HELP_SCROLL": "<b>Mouse wheel:</b> while dragging, scroll to open the wheel, keep scrolling to move between slices, "
                   "then let go to apply the highlighted one. Esc cancels.",
    "HELP_HTML": (
        "<b>Drag any file</b> in Explorer or on the desktop, and while still holding the mouse:<br><br>"
        "• tap <b>{convert}</b> for the conversion wheel<br>"
        "• tap <b>{tool}</b> for file tools (compress, crop, trim, merge…)<br>"
        "• tap <b>{action}</b> for actions (copy, move, terminal, float…)<br><br>"
        "Drop on a slice to apply it. Drop in the middle to cancel. Hover a pill under the wheel to switch.<br><br>"
        "<b>Without dragging:</b> select files and press <b>Ctrl+Alt+Space</b>, or right-click → "
        "<i>{app}</i>. Use arrows + Enter, Tab to switch wheels, Esc to cancel.<br><br>"
        "Results are saved next to the original. Nothing leaves your PC."),
}

T: dict[str, dict[str, str]] = {}

# --------------------------------------------------------------------------- Arabic
T["ar"] = {
    "About": "حول",
    "Appearance": "المظهر",
    "Dark": "داكن",
    "Donate": "تبرّع",
    "Drag a file, tap a key, drop it on the wheel.": "اسحب ملفًا، اضغط مفتاحًا، وأفلته على العجلة.",
    "Free and open source (MIT License)": "مجاني ومفتوح المصدر (رخصة MIT)",
    "GitHub page": "صفحة GitHub",
    "Last checked: {when}": "آخر تحقق: {when}",
    "Light": "فاتح",
    "Made by {who}": "من تطوير {who}",
    "Privacy policy": "سياسة الخصوصية",
    "Report a problem": "الإبلاغ عن مشكلة",
    "Settings": "الإعدادات",
    "Theme": "السمة",
    "Version {v}": "الإصدار {v}",
    "never": "أبدًا",
    "Cancel: {what} — {name}": "إلغاء: {what} — {name}",
    "Cancel all ({n})": "إلغاء الكل ({n})",
    "Cancelled": "تم الإلغاء",
    "Cancelling…": "جارٍ الإلغاء…",
    "Check for updates automatically (once a day)": "التحقق من التحديثات تلقائيًا (مرة يوميًا)",
    "Check for updates…": "التحقق من التحديثات…",
    "Check now": "تحقق الآن",
    "Checking for updates…": "جارٍ التحقق من التحديثات…",
    "Couldn't check for updates": "تعذّر التحقق من التحديثات",
    "Couldn't download the update": "تعذّر تنزيل التحديث",
    "Couldn't start the installer": "تعذّر تشغيل المثبّت",
    "Download && install": "تنزيل وتثبيت",
    "Downloading update…": "جارٍ تنزيل التحديث…",
    "E-book": "كتاب إلكتروني",
    "Installing update…": "جارٍ تثبيت التحديث…",
    "Later": "لاحقًا",
    "Nothing was saved.": "لم يتم حفظ أي شيء.",
    "Open release page": "فتح صفحة الإصدار",
    "Skip this version": "تخطي هذا الإصدار",
    "The only connection is the update check to GitHub.": "الاتصال الوحيد هو التحقق من التحديثات عبر GitHub.",
    "The update was not downloaded.": "لم يتم تنزيل التحديث.",
    "Updates": "التحديثات",
    "You have {v}.": "لديك الإصدار {v}.",
    "You're up to date": "لديك أحدث إصدار",
    "smaller file": "حجم أصغر",
    "{app} update": "تحديث {app}",
    "Finish the steps in the setup window.": "أكمل الخطوات في نافذة التثبيت.",
    "{app} {v} is available": "يتوفر {app} {v}",
    "{app} {v} is the latest version.": "{app} {v} هو أحدث إصدار.",
    "Scroll the mouse wheel while dragging to open the wheel and move between slices": "مرّر عجلة الفأرة أثناء السحب لفتح العجلة والتنقل بين الأقسام",
    "HELP_SCROLL": "<b>عجلة الفأرة:</b> أثناء السحب، مرّر لفتح العجلة، واستمر بالتمرير للتنقل بين الأقسام، ثم أفلت لتطبيق القسم المحدد. Esc للإلغاء.",
    "Couldn't read the dragged file": "يتعذّر قراءة الملف المسحوب",
    "Try again, or select it and press Ctrl+Alt+Space": "حاول مجددًا، أو حدّده واضغط Ctrl+Alt+Space",
    "needs WinRAR": "يتطلب WinRAR",
    "Convert": "تحويل", "Tools": "أدوات", "Actions": "إجراءات",
    "CapsLock": "Caps Lock",
    # categories
    "Image": "صورة", "Video": "فيديو", "Audio": "صوت", "PDF": "PDF", "Document": "مستند", "Slides": "عرض تقديمي",
    "Spreadsheet": "جدول بيانات", "Subtitles": "ترجمة", "EPUB": "كتاب EPUB", "Archive": "أرشيف",
    "Folder": "مجلد", "Files": "ملفات", "File": "ملف",
    # wheel items
    "Compress": "ضغط", "Crop & Resize…": "قص وتحجيم…", "Rotate 90°": "تدوير 90°", "Flip": "قلب",
    "Grayscale": "تدرّج رمادي", "Strip metadata": "إزالة البيانات", "Combine PDF": "دمج في PDF",
    "720p": "720p", "Trim…": "قص المقطع…", "Mute": "كتم الصوت", "Snapshot…": "لقطة…", "Speed 2×": "سرعة 2×",
    "Merge": "دمج", "Normalize": "توحيد الصوت", "Mono": "أحادي", "Fade in/out": "تلاشي دخول/خروج",
    "Split pages": "تقسيم الصفحات", "Extract pages…": "استخراج صفحات…", "Extract images": "استخراج الصور",
    "Password…": "كلمة مرور…", "Zip": "ضغط ZIP", "Extract": "فك الضغط", "Markdown": "Markdown",
    "Copy": "نسخ", "Copy path": "نسخ المسار", "Move to…": "نقل إلى…", "Copy to…": "نسخ إلى…",
    "Terminal": "Terminal", "Float": "تثبيت عائم", "Show": "إظهار", "Open with…": "فتح بواسطة…",
    "to clipboard": "إلى الحافظة", "open here": "فتح هنا", "in Explorer": "في المستكشف", "audio only": "الصوت فقط",
    "No conversions": "لا توجد تحويلات", "try Tools or Actions": "جرّب الأدوات أو الإجراءات",
    "Cancel": "إلغاء", "drop here": "أفلت هنا", "move to read file": "حرّك لقراءة الملف",
    "{n} files": "{n} ملفات",
    # parameters
    "Start": "البداية", "End": "النهاية", "At time": "عند الوقت", "Pages (e.g. 1-3,5)": "الصفحات (مثال 1-3,5)",
    "Password": "كلمة المرور", "seconds, m:ss or h:mm:ss": "ثوانٍ أو د:ث أو س:د:ث", "Apply": "تطبيق", "OK": "موافق",
    # toasts
    "Copied to clipboard": "تم النسخ إلى الحافظة", "{n} item(s) — paste anywhere": "{n} عنصر — الصق في أي مكان",
    "Path copied": "تم نسخ المسار", "{n} paths": "{n} مسارات", "Move to": "نقل إلى", "Moved": "تم النقل",
    "Copy to": "نسخ إلى", "Copied": "تم النسخ", "{n} items saved": "تم حفظ {n} عناصر",
    "Converting to {fmt}…": "جارٍ التحويل إلى {fmt}…", "Converted to {fmt}": "تم التحويل إلى {fmt}",
    "Done": "تم", "{what} failed": "فشل: {what}", "Couldn't do that": "تعذّر تنفيذ ذلك",
    "Couldn't open image": "تعذّر فتح الصورة",
    "Nothing selected": "لا يوجد تحديد",
    "Select files in File Explorer, then press Ctrl+Alt+Space": "حدّد ملفات في مستكشف الملفات ثم اضغط Ctrl+Alt+Space",
    "Running in the tray. Drag a file and tap {key}.": "يعمل في شريط المهام. اسحب ملفًا واضغط {key}.",
    # float
    "Drag to move · drag ⠿ to drop the file · double-click to open · scroll to resize":
        "اسحب للتحريك · اسحب ⠿ لإفلات الملف · انقر مرتين للفتح · مرّر لتغيير الحجم",
    "Open": "فتح", "Show in Explorer": "إظهار في المستكشف", "Close": "إغلاق",
    # editor
    "Crop & Resize": "قص وتغيير الحجم", "Aspect ratio": "نسبة الأبعاد", "Free": "حر", "Original": "الأصلية",
    "Rotate & flip": "تدوير وقلب", "Rotate left": "تدوير لليسار", "Rotate right": "تدوير لليمين",
    "Flip horizontal": "قلب أفقي", "Flip vertical": "قلب عمودي", "Crop": "القص", "Output size": "حجم الناتج",
    "Width": "العرض", "Height": "الارتفاع", "Keep proportions": "الحفاظ على النسبة", "Save as": "حفظ بصيغة",
    "Same as original": "نفس الأصل", "Reset": "إعادة تعيين", "Save copy": "حفظ نسخة",
    "Drag the box or its corners. Double-click the image to reset the crop.":
        "اسحب الإطار أو زواياه. انقر مرتين على الصورة لإعادة تعيين القص.",
    # tray
    "{app} — drag a file, tap {key}": "{app} — اسحب ملفًا واضغط {key}", "Convert files…": "تحويل ملفات…",
    "How it works": "طريقة الاستخدام", "Settings…": "الإعدادات…", "Quit {app}": "إنهاء {app}",
    "Choose files to convert": "اختر ملفات للتحويل",
    # settings
    "{app} Settings": "إعدادات {app}", "Language": "اللغة", "App language": "لغة التطبيق",
    "System default": "لغة النظام", "Wheel keys — tap while dragging a file": "مفاتيح العجلة — اضغط أثناء سحب ملف",
    "File drags only (recommended)": "سحب الملفات فقط (مستحسن)", "Any mouse drag": "أي سحب بالفأرة",
    "Trigger on": "التفعيل عند", "Output": "الحفظ", "Next to the original file": "بجانب الملف الأصلي",
    "Browse…": "استعراض…", "Output folder": "مجلد الحفظ", "Save to": "حفظ في",
    "Start {app} when I sign in": "تشغيل {app} عند تسجيل الدخول",
    "Add {app} to the Explorer right-click menu and Send To": "إضافة {app} إلى قائمة الزر الأيمن و«إرسال إلى»",
    "Ctrl + Alt + Space opens the wheel for files selected in Explorer":
        "Ctrl + Alt + Space يفتح العجلة للملفات المحددة في المستكشف",
    "found": "موجود",
    "not found — DOCX/PPTX/XLS conversions need Microsoft Office or LibreOffice":
        "غير موجود — تحويلات DOCX/PPTX/XLS تتطلب Microsoft Office أو LibreOffice",
    "{c}+ conversions · {t}+ tools · 8 actions": "أكثر من {c} تحويل · أكثر من {t} أداة · 8 إجراءات",
    "Everything runs locally — nothing is uploaded.": "كل شيء يعمل على جهازك — لا يتم رفع أي ملف.",
    "Save": "حفظ", "Each wheel needs a different key.": "كل عجلة تحتاج مفتاحًا مختلفًا.",
    "Couldn't update Windows integration:": "تعذّر تحديث التكامل مع Windows:",
    "{app} — How it works": "{app} — طريقة الاستخدام",
    "HELP_HTML": (
        "<b>اسحب أي ملف</b> في المستكشف أو على سطح المكتب، وأثناء الضغط على الفأرة:<br><br>"
        "• اضغط <b>{convert}</b> لعجلة التحويل<br>"
        "• اضغط <b>{tool}</b> لأدوات الملفات (ضغط، قص، تقطيع، دمج…)<br>"
        "• اضغط <b>{action}</b> للإجراءات (نسخ، نقل، Terminal، تثبيت عائم…)<br><br>"
        "أفلت الملف على أحد الأقسام لتطبيقه، أو في المنتصف للإلغاء. مرّر فوق الأزرار أسفل العجلة للتبديل.<br><br>"
        "<b>بدون سحب:</b> حدّد الملفات واضغط <b>Ctrl+Alt+Space</b>، أو انقر بزر الفأرة الأيمن ← <i>{app}</i>. "
        "استخدم الأسهم و Enter، و Tab للتبديل بين العجلات، و Esc للإلغاء.<br><br>"
        "تُحفظ النتائج بجانب الملف الأصلي. لا يغادر أي شيء جهازك."),
}

# --------------------------------------------------------------------------- French
T["fr"] = {
    "About": "À propos",
    "Appearance": "Apparence",
    "Dark": "Sombre",
    "Donate": "Faire un don",
    "Drag a file, tap a key, drop it on the wheel.": "Glissez un fichier, appuyez sur une touche, déposez-le sur la roue.",
    "Free and open source (MIT License)": "Gratuit et open source (licence MIT)",
    "GitHub page": "Page GitHub",
    "Last checked: {when}": "Dernière vérification : {when}",
    "Light": "Clair",
    "Made by {who}": "Créé par {who}",
    "Privacy policy": "Politique de confidentialité",
    "Report a problem": "Signaler un problème",
    "Settings": "Paramètres",
    "Theme": "Thème",
    "Version {v}": "Version {v}",
    "never": "jamais",
    "Cancel: {what} — {name}": "Annuler : {what} — {name}",
    "Cancel all ({n})": "Tout annuler ({n})",
    "Cancelled": "Annulé",
    "Cancelling…": "Annulation…",
    "Check for updates automatically (once a day)": "Rechercher les mises à jour automatiquement (une fois par jour)",
    "Check for updates…": "Rechercher des mises à jour…",
    "Check now": "Vérifier",
    "Checking for updates…": "Recherche de mises à jour…",
    "Couldn't check for updates": "Impossible de vérifier les mises à jour",
    "Couldn't download the update": "Impossible de télécharger la mise à jour",
    "Couldn't start the installer": "Impossible de lancer l'installation",
    "Download && install": "Télécharger et installer",
    "Downloading update…": "Téléchargement de la mise à jour…",
    "E-book": "Livre numérique",
    "Installing update…": "Installation de la mise à jour…",
    "Later": "Plus tard",
    "Nothing was saved.": "Rien n'a été enregistré.",
    "Open release page": "Ouvrir la page de la version",
    "Skip this version": "Ignorer cette version",
    "The only connection is the update check to GitHub.": "La seule connexion est la vérification des mises à jour sur GitHub.",
    "The update was not downloaded.": "La mise à jour n'a pas été téléchargée.",
    "Updates": "Mises à jour",
    "You have {v}.": "Vous avez la {v}.",
    "You're up to date": "Vous êtes à jour",
    "smaller file": "fichier plus léger",
    "{app} update": "Mise à jour de {app}",
    "Finish the steps in the setup window.": "Terminez les étapes dans la fenêtre d'installation.",
    "{app} {v} is available": "{app} {v} est disponible",
    "{app} {v} is the latest version.": "{app} {v} est la dernière version.",
    "Scroll the mouse wheel while dragging to open the wheel and move between slices": "Faire défiler la molette pendant le glisser pour ouvrir la roue et changer de part",
    "HELP_SCROLL": "<b>Molette :</b> pendant le glisser, faites défiler pour ouvrir la roue, continuez pour changer de part, puis relâchez pour appliquer. Échap annule.",
    "Couldn't read the dragged file": "Impossible de lire le fichier glissé",
    "Try again, or select it and press Ctrl+Alt+Space": "Réessayez, ou sélectionnez-le puis Ctrl+Alt+Espace",
    "needs WinRAR": "nécessite WinRAR",
    "Convert": "Convertir", "Tools": "Outils", "Actions": "Actions", "CapsLock": "Verr. Maj",
    "Image": "Image", "Video": "Vidéo", "Audio": "Audio", "Document": "Document", "Slides": "Présentation",
    "Spreadsheet": "Tableur", "Subtitles": "Sous-titres", "Archive": "Archive", "Folder": "Dossier",
    "Files": "Fichiers", "File": "Fichier",
    "Compress": "Compresser", "Crop & Resize…": "Rogner et redim.…", "Rotate 90°": "Pivoter 90°", "Flip": "Miroir",
    "Grayscale": "Niveaux de gris", "Strip metadata": "Suppr. métadonnées", "Combine PDF": "Combiner en PDF",
    "Trim…": "Couper…", "Mute": "Muet", "Snapshot…": "Capture…", "Speed 2×": "Vitesse 2×", "Merge": "Fusionner",
    "Normalize": "Normaliser", "Mono": "Mono", "Fade in/out": "Fondu", "Split pages": "Séparer pages",
    "Extract pages…": "Extraire pages…", "Extract images": "Extraire images", "Password…": "Mot de passe…",
    "Zip": "Zip", "Extract": "Extraire",
    "Copy": "Copier", "Copy path": "Copier chemin", "Move to…": "Déplacer vers…", "Copy to…": "Copier vers…",
    "Terminal": "Terminal", "Float": "Flottant", "Show": "Afficher", "Open with…": "Ouvrir avec…",
    "to clipboard": "presse-papiers", "open here": "ouvrir ici", "in Explorer": "dans l'Explorateur",
    "audio only": "audio seul", "No conversions": "Aucune conversion", "try Tools or Actions": "essayez Outils ou Actions",
    "Cancel": "Annuler", "drop here": "déposer ici", "move to read file": "bougez pour lire le fichier",
    "{n} files": "{n} fichiers",
    "Start": "Début", "End": "Fin", "At time": "À l'instant", "Pages (e.g. 1-3,5)": "Pages (ex. 1-3,5)",
    "Password": "Mot de passe", "seconds, m:ss or h:mm:ss": "secondes, m:ss ou h:mm:ss", "Apply": "Appliquer",
    "Copied to clipboard": "Copié dans le presse-papiers", "{n} item(s) — paste anywhere": "{n} élément(s) — collez où vous voulez",
    "Path copied": "Chemin copié", "{n} paths": "{n} chemins", "Move to": "Déplacer vers", "Moved": "Déplacé",
    "Copy to": "Copier vers", "Copied": "Copié", "{n} items saved": "{n} éléments enregistrés",
    "Converting to {fmt}…": "Conversion en {fmt}…", "Converted to {fmt}": "Converti en {fmt}", "Done": "Terminé",
    "{what} failed": "Échec : {what}", "Couldn't do that": "Impossible", "Couldn't open image": "Impossible d'ouvrir l'image",
    "Nothing selected": "Aucune sélection",
    "Select files in File Explorer, then press Ctrl+Alt+Space": "Sélectionnez des fichiers dans l'Explorateur, puis Ctrl+Alt+Espace",
    "Running in the tray. Drag a file and tap {key}.": "Actif dans la barre des tâches. Glissez un fichier et appuyez sur {key}.",
    "Drag to move · drag ⠿ to drop the file · double-click to open · scroll to resize":
        "Glisser pour déplacer · glisser ⠿ pour déposer le fichier · double-clic pour ouvrir · molette pour redimensionner",
    "Open": "Ouvrir", "Show in Explorer": "Afficher dans l'Explorateur", "Close": "Fermer",
    "Crop & Resize": "Rogner et redimensionner", "Aspect ratio": "Proportions", "Free": "Libre", "Original": "Original",
    "Rotate & flip": "Rotation et miroir", "Rotate left": "Pivoter à gauche", "Rotate right": "Pivoter à droite",
    "Flip horizontal": "Miroir horizontal", "Flip vertical": "Miroir vertical", "Crop": "Rognage",
    "Output size": "Taille finale", "Width": "Largeur", "Height": "Hauteur", "Keep proportions": "Conserver les proportions",
    "Save as": "Enregistrer en", "Same as original": "Comme l'original", "Reset": "Réinitialiser", "Save copy": "Enregistrer une copie",
    "Drag the box or its corners. Double-click the image to reset the crop.":
        "Faites glisser le cadre ou ses coins. Double-cliquez sur l'image pour réinitialiser.",
    "{app} — drag a file, tap {key}": "{app} — glissez un fichier, appuyez sur {key}", "Convert files…": "Convertir des fichiers…",
    "How it works": "Mode d'emploi", "Settings…": "Paramètres…", "Quit {app}": "Quitter {app}",
    "Choose files to convert": "Choisir les fichiers à convertir",
    "{app} Settings": "Paramètres de {app}", "Language": "Langue", "App language": "Langue de l'application",
    "System default": "Langue du système", "Wheel keys — tap while dragging a file": "Touches de la roue — pendant le glisser",
    "File drags only (recommended)": "Glisser de fichiers uniquement (recommandé)", "Any mouse drag": "Tout glisser de souris",
    "Trigger on": "Déclencher sur", "Output": "Sortie", "Next to the original file": "À côté du fichier original",
    "Browse…": "Parcourir…", "Output folder": "Dossier de sortie", "Save to": "Enregistrer dans",
    "Start {app} when I sign in": "Lancer {app} à l'ouverture de session",
    "Add {app} to the Explorer right-click menu and Send To": "Ajouter {app} au clic droit et à « Envoyer vers »",
    "Ctrl + Alt + Space opens the wheel for files selected in Explorer":
        "Ctrl + Alt + Espace ouvre la roue pour les fichiers sélectionnés",
    "found": "trouvé", "not found — DOCX/PPTX/XLS conversions need Microsoft Office or LibreOffice":
        "introuvable — DOCX/PPTX/XLS nécessitent Microsoft Office ou LibreOffice",
    "{c}+ conversions · {t}+ tools · 8 actions": "{c}+ conversions · {t}+ outils · 8 actions",
    "Everything runs locally — nothing is uploaded.": "Tout fonctionne en local — rien n'est envoyé.",
    "Save": "Enregistrer", "Each wheel needs a different key.": "Chaque roue doit avoir une touche différente.",
    "Couldn't update Windows integration:": "Impossible de mettre à jour l'intégration Windows :",
    "{app} — How it works": "{app} — Mode d'emploi",
    "HELP_HTML": (
        "<b>Faites glisser un fichier</b> dans l'Explorateur ou sur le bureau et, bouton maintenu :<br><br>"
        "• appuyez sur <b>{convert}</b> pour la roue de conversion<br>"
        "• appuyez sur <b>{tool}</b> pour les outils (compresser, rogner, couper, fusionner…)<br>"
        "• appuyez sur <b>{action}</b> pour les actions (copier, déplacer, terminal, flottant…)<br><br>"
        "Déposez sur une part pour l'appliquer, au centre pour annuler.<br><br>"
        "<b>Sans glisser :</b> sélectionnez des fichiers puis <b>Ctrl+Alt+Espace</b>, ou clic droit → <i>{app}</i>.<br><br>"
        "Les résultats sont enregistrés à côté de l'original. Rien ne quitte votre PC."),
}

# --------------------------------------------------------------------------- Spanish
T["es"] = {
    "About": "Acerca de",
    "Appearance": "Apariencia",
    "Dark": "Oscuro",
    "Donate": "Donar",
    "Drag a file, tap a key, drop it on the wheel.": "Arrastra un archivo, pulsa una tecla y suéltalo en la rueda.",
    "Free and open source (MIT License)": "Gratis y de código abierto (licencia MIT)",
    "GitHub page": "Página de GitHub",
    "Last checked: {when}": "Última comprobación: {when}",
    "Light": "Claro",
    "Made by {who}": "Hecho por {who}",
    "Privacy policy": "Política de privacidad",
    "Report a problem": "Informar de un problema",
    "Settings": "Configuración",
    "Theme": "Tema",
    "Version {v}": "Versión {v}",
    "never": "nunca",
    "Cancel: {what} — {name}": "Cancelar: {what} — {name}",
    "Cancel all ({n})": "Cancelar todo ({n})",
    "Cancelled": "Cancelado",
    "Cancelling…": "Cancelando…",
    "Check for updates automatically (once a day)": "Buscar actualizaciones automáticamente (una vez al día)",
    "Check for updates…": "Buscar actualizaciones…",
    "Check now": "Comprobar",
    "Checking for updates…": "Buscando actualizaciones…",
    "Couldn't check for updates": "No se pudieron buscar actualizaciones",
    "Couldn't download the update": "No se pudo descargar la actualización",
    "Couldn't start the installer": "No se pudo iniciar el instalador",
    "Download && install": "Descargar e instalar",
    "Downloading update…": "Descargando actualización…",
    "E-book": "Libro electrónico",
    "Installing update…": "Instalando actualización…",
    "Later": "Más tarde",
    "Nothing was saved.": "No se guardó nada.",
    "Open release page": "Abrir página de la versión",
    "Skip this version": "Omitir esta versión",
    "The only connection is the update check to GitHub.": "La única conexión es la búsqueda de actualizaciones en GitHub.",
    "The update was not downloaded.": "La actualización no se descargó.",
    "Updates": "Actualizaciones",
    "You have {v}.": "Tienes la {v}.",
    "You're up to date": "Estás al día",
    "smaller file": "archivo más pequeño",
    "{app} update": "Actualización de {app}",
    "Finish the steps in the setup window.": "Completa los pasos en la ventana de instalación.",
    "{app} {v} is available": "{app} {v} está disponible",
    "{app} {v} is the latest version.": "{app} {v} es la última versión.",
    "Scroll the mouse wheel while dragging to open the wheel and move between slices": "Girar la rueda del ratón al arrastrar para abrir la rueda y moverse entre secciones",
    "HELP_SCROLL": "<b>Rueda del ratón:</b> mientras arrastras, gira para abrir la rueda, sigue girando para moverte entre secciones y suelta para aplicar la resaltada. Esc cancela.",
    "Couldn't read the dragged file": "No se pudo leer el archivo arrastrado",
    "Try again, or select it and press Ctrl+Alt+Space": "Inténtalo de nuevo, o selecciónalo y pulsa Ctrl+Alt+Espacio",
    "needs WinRAR": "requiere WinRAR",
    "Convert": "Convertir", "Tools": "Herramientas", "Actions": "Acciones", "CapsLock": "Bloq Mayús",
    "Image": "Imagen", "Video": "Vídeo", "Audio": "Audio", "Document": "Documento", "Slides": "Presentación",
    "Spreadsheet": "Hoja de cálculo", "Subtitles": "Subtítulos", "Archive": "Archivo comprimido", "Folder": "Carpeta",
    "Files": "Archivos", "File": "Archivo",
    "Compress": "Comprimir", "Crop & Resize…": "Recortar y redim.…", "Rotate 90°": "Girar 90°", "Flip": "Voltear",
    "Grayscale": "Escala de grises", "Strip metadata": "Quitar metadatos", "Combine PDF": "Unir en PDF",
    "Trim…": "Recortar…", "Mute": "Silenciar", "Snapshot…": "Captura…", "Speed 2×": "Velocidad 2×", "Merge": "Unir",
    "Normalize": "Normalizar", "Mono": "Mono", "Fade in/out": "Fundido", "Split pages": "Separar páginas",
    "Extract pages…": "Extraer páginas…", "Extract images": "Extraer imágenes", "Password…": "Contraseña…",
    "Zip": "Zip", "Extract": "Extraer",
    "Copy": "Copiar", "Copy path": "Copiar ruta", "Move to…": "Mover a…", "Copy to…": "Copiar a…",
    "Terminal": "Terminal", "Float": "Flotante", "Show": "Mostrar", "Open with…": "Abrir con…",
    "to clipboard": "al portapapeles", "open here": "abrir aquí", "in Explorer": "en el Explorador",
    "audio only": "solo audio", "No conversions": "Sin conversiones", "try Tools or Actions": "prueba Herramientas o Acciones",
    "Cancel": "Cancelar", "drop here": "suelta aquí", "move to read file": "mueve para leer el archivo",
    "{n} files": "{n} archivos",
    "Start": "Inicio", "End": "Fin", "At time": "En el tiempo", "Pages (e.g. 1-3,5)": "Páginas (ej. 1-3,5)",
    "Password": "Contraseña", "seconds, m:ss or h:mm:ss": "segundos, m:ss o h:mm:ss", "Apply": "Aplicar", "OK": "Aceptar",
    "Copied to clipboard": "Copiado al portapapeles", "{n} item(s) — paste anywhere": "{n} elemento(s) — pega donde quieras",
    "Path copied": "Ruta copiada", "{n} paths": "{n} rutas", "Move to": "Mover a", "Moved": "Movido",
    "Copy to": "Copiar a", "Copied": "Copiado", "{n} items saved": "{n} elementos guardados",
    "Converting to {fmt}…": "Convirtiendo a {fmt}…", "Converted to {fmt}": "Convertido a {fmt}", "Done": "Listo",
    "{what} failed": "Falló: {what}", "Couldn't do that": "No se pudo hacer", "Couldn't open image": "No se pudo abrir la imagen",
    "Nothing selected": "Nada seleccionado",
    "Select files in File Explorer, then press Ctrl+Alt+Space": "Selecciona archivos en el Explorador y pulsa Ctrl+Alt+Espacio",
    "Running in the tray. Drag a file and tap {key}.": "En la bandeja. Arrastra un archivo y pulsa {key}.",
    "Drag to move · drag ⠿ to drop the file · double-click to open · scroll to resize":
        "Arrastra para mover · arrastra ⠿ para soltar el archivo · doble clic para abrir · rueda para cambiar tamaño",
    "Open": "Abrir", "Show in Explorer": "Mostrar en el Explorador", "Close": "Cerrar",
    "Crop & Resize": "Recortar y redimensionar", "Aspect ratio": "Proporción", "Free": "Libre", "Original": "Original",
    "Rotate & flip": "Girar y voltear", "Rotate left": "Girar a la izquierda", "Rotate right": "Girar a la derecha",
    "Flip horizontal": "Voltear horizontal", "Flip vertical": "Voltear vertical", "Crop": "Recorte",
    "Output size": "Tamaño final", "Width": "Ancho", "Height": "Alto", "Keep proportions": "Mantener proporciones",
    "Save as": "Guardar como", "Same as original": "Igual que el original", "Reset": "Restablecer", "Save copy": "Guardar copia",
    "Drag the box or its corners. Double-click the image to reset the crop.":
        "Arrastra el marco o sus esquinas. Doble clic en la imagen para restablecer.",
    "{app} — drag a file, tap {key}": "{app} — arrastra un archivo, pulsa {key}", "Convert files…": "Convertir archivos…",
    "How it works": "Cómo funciona", "Settings…": "Configuración…", "Quit {app}": "Salir de {app}",
    "Choose files to convert": "Elige archivos para convertir",
    "{app} Settings": "Configuración de {app}", "Language": "Idioma", "App language": "Idioma de la aplicación",
    "System default": "Idioma del sistema", "Wheel keys — tap while dragging a file": "Teclas de la rueda — pulsa mientras arrastras",
    "File drags only (recommended)": "Solo arrastre de archivos (recomendado)", "Any mouse drag": "Cualquier arrastre",
    "Trigger on": "Activar con", "Output": "Salida", "Next to the original file": "Junto al archivo original",
    "Browse…": "Examinar…", "Output folder": "Carpeta de salida", "Save to": "Guardar en",
    "Start {app} when I sign in": "Iniciar {app} al iniciar sesión",
    "Add {app} to the Explorer right-click menu and Send To": "Añadir {app} al clic derecho y a «Enviar a»",
    "Ctrl + Alt + Space opens the wheel for files selected in Explorer":
        "Ctrl + Alt + Espacio abre la rueda para los archivos seleccionados",
    "found": "encontrado", "not found — DOCX/PPTX/XLS conversions need Microsoft Office or LibreOffice":
        "no encontrado — DOCX/PPTX/XLS requieren Microsoft Office o LibreOffice",
    "{c}+ conversions · {t}+ tools · 8 actions": "{c}+ conversiones · {t}+ herramientas · 8 acciones",
    "Everything runs locally — nothing is uploaded.": "Todo funciona en local — no se sube nada.",
    "Save": "Guardar", "Each wheel needs a different key.": "Cada rueda necesita una tecla distinta.",
    "Couldn't update Windows integration:": "No se pudo actualizar la integración con Windows:",
    "{app} — How it works": "{app} — Cómo funciona",
    "HELP_HTML": (
        "<b>Arrastra cualquier archivo</b> en el Explorador o el escritorio y, sin soltar el ratón:<br><br>"
        "• pulsa <b>{convert}</b> para la rueda de conversión<br>"
        "• pulsa <b>{tool}</b> para herramientas (comprimir, recortar, cortar, unir…)<br>"
        "• pulsa <b>{action}</b> para acciones (copiar, mover, terminal, flotante…)<br><br>"
        "Suelta sobre una sección para aplicarla, o en el centro para cancelar.<br><br>"
        "<b>Sin arrastrar:</b> selecciona archivos y pulsa <b>Ctrl+Alt+Espacio</b>, o clic derecho → <i>{app}</i>.<br><br>"
        "Los resultados se guardan junto al original. Nada sale de tu PC."),
}

# --------------------------------------------------------------------------- Turkish
T["tr"] = {
    "About": "Hakkında",
    "Appearance": "Görünüm",
    "Dark": "Koyu",
    "Donate": "Bağış yap",
    "Drag a file, tap a key, drop it on the wheel.": "Bir dosya sürükleyin, bir tuşa basın, tekerleğe bırakın.",
    "Free and open source (MIT License)": "Ücretsiz ve açık kaynak (MIT Lisansı)",
    "GitHub page": "GitHub sayfası",
    "Last checked: {when}": "Son denetim: {when}",
    "Light": "Açık",
    "Made by {who}": "Geliştiren: {who}",
    "Privacy policy": "Gizlilik politikası",
    "Report a problem": "Sorun bildir",
    "Settings": "Ayarlar",
    "Theme": "Tema",
    "Version {v}": "Sürüm {v}",
    "never": "hiç",
    "Cancel: {what} — {name}": "İptal: {what} — {name}",
    "Cancel all ({n})": "Tümünü iptal et ({n})",
    "Cancelled": "İptal edildi",
    "Cancelling…": "İptal ediliyor…",
    "Check for updates automatically (once a day)": "Güncellemeleri otomatik denetle (günde bir kez)",
    "Check for updates…": "Güncellemeleri denetle…",
    "Check now": "Şimdi denetle",
    "Checking for updates…": "Güncellemeler denetleniyor…",
    "Couldn't check for updates": "Güncellemeler denetlenemedi",
    "Couldn't download the update": "Güncelleme indirilemedi",
    "Couldn't start the installer": "Kurulum başlatılamadı",
    "Download && install": "İndir ve kur",
    "Downloading update…": "Güncelleme indiriliyor…",
    "E-book": "E-kitap",
    "Installing update…": "Güncelleme kuruluyor…",
    "Later": "Daha sonra",
    "Nothing was saved.": "Hiçbir şey kaydedilmedi.",
    "Open release page": "Sürüm sayfasını aç",
    "Skip this version": "Bu sürümü atla",
    "The only connection is the update check to GitHub.": "Tek bağlantı GitHub'daki güncelleme denetimidir.",
    "The update was not downloaded.": "Güncelleme indirilmedi.",
    "Updates": "Güncellemeler",
    "You have {v}.": "Sizdeki sürüm: {v}.",
    "You're up to date": "Güncelsiniz",
    "smaller file": "daha küçük dosya",
    "{app} update": "{app} güncellemesi",
    "Finish the steps in the setup window.": "Kurulum penceresindeki adımları tamamlayın.",
    "{app} {v} is available": "{app} {v} yayımlandı",
    "{app} {v} is the latest version.": "{app} {v} en son sürüm.",
    "Scroll the mouse wheel while dragging to open the wheel and move between slices": "Sürüklerken fare tekerleğini çevirerek tekerleği aç ve dilimler arasında geç",
    "HELP_SCROLL": "<b>Fare tekerleği:</b> sürüklerken tekerleği açmak için kaydırın, dilimler arasında geçmek için kaydırmaya devam edin, vurgulananı uygulamak için bırakın. Esc iptal eder.",
    "Couldn't read the dragged file": "Sürüklenen dosya okunamadı",
    "Try again, or select it and press Ctrl+Alt+Space": "Tekrar deneyin veya seçip Ctrl+Alt+Boşluk'a basın",
    "needs WinRAR": "WinRAR gerekir",
    "Convert": "Dönüştür", "Tools": "Araçlar", "Actions": "Eylemler", "CapsLock": "Caps Lock",
    "Image": "Görsel", "Video": "Video", "Audio": "Ses", "Document": "Belge", "Slides": "Sunum",
    "Spreadsheet": "Tablo", "Subtitles": "Altyazı", "Archive": "Arşiv", "Folder": "Klasör", "Files": "Dosyalar", "File": "Dosya",
    "Compress": "Sıkıştır", "Crop & Resize…": "Kırp ve boyutlandır…", "Rotate 90°": "90° döndür", "Flip": "Aynala",
    "Grayscale": "Gri tonlama", "Strip metadata": "Meta verileri sil", "Combine PDF": "PDF'de birleştir",
    "Trim…": "Kırp…", "Mute": "Sessiz", "Snapshot…": "Kare al…", "Speed 2×": "Hız 2×", "Merge": "Birleştir",
    "Normalize": "Normalleştir", "Mono": "Mono", "Fade in/out": "Geçiş efekti", "Split pages": "Sayfaları ayır",
    "Extract pages…": "Sayfa çıkar…", "Extract images": "Görselleri çıkar", "Password…": "Parola…",
    "Zip": "Zip", "Extract": "Ayıkla",
    "Copy": "Kopyala", "Copy path": "Yolu kopyala", "Move to…": "Taşı…", "Copy to…": "Kopyala…",
    "Terminal": "Terminal", "Float": "Yüzen", "Show": "Göster", "Open with…": "Birlikte aç…",
    "to clipboard": "panoya", "open here": "burada aç", "in Explorer": "Gezgin'de", "audio only": "yalnızca ses",
    "No conversions": "Dönüştürme yok", "try Tools or Actions": "Araçlar veya Eylemler'i deneyin",
    "Cancel": "İptal", "drop here": "buraya bırak", "move to read file": "dosyayı okumak için hareket ettirin",
    "{n} files": "{n} dosya",
    "Start": "Başlangıç", "End": "Bitiş", "At time": "Zaman", "Pages (e.g. 1-3,5)": "Sayfalar (örn. 1-3,5)",
    "Password": "Parola", "seconds, m:ss or h:mm:ss": "saniye, d:ss veya s:dd:ss", "Apply": "Uygula", "OK": "Tamam",
    "Copied to clipboard": "Panoya kopyalandı", "{n} item(s) — paste anywhere": "{n} öğe — istediğiniz yere yapıştırın",
    "Path copied": "Yol kopyalandı", "{n} paths": "{n} yol", "Move to": "Taşı", "Moved": "Taşındı",
    "Copy to": "Kopyala", "Copied": "Kopyalandı", "{n} items saved": "{n} öğe kaydedildi",
    "Converting to {fmt}…": "{fmt} biçimine dönüştürülüyor…", "Converted to {fmt}": "{fmt} biçimine dönüştürüldü",
    "Done": "Tamam", "{what} failed": "Başarısız: {what}", "Couldn't do that": "Yapılamadı", "Couldn't open image": "Görsel açılamadı",
    "Nothing selected": "Seçim yok",
    "Select files in File Explorer, then press Ctrl+Alt+Space": "Dosya Gezgini'nde dosya seçin, ardından Ctrl+Alt+Boşluk",
    "Running in the tray. Drag a file and tap {key}.": "Sistem tepsisinde çalışıyor. Bir dosya sürükleyip {key} tuşuna basın.",
    "Drag to move · drag ⠿ to drop the file · double-click to open · scroll to resize":
        "Taşımak için sürükleyin · dosyayı bırakmak için ⠿ sürükleyin · açmak için çift tıklayın · boyut için kaydırın",
    "Open": "Aç", "Show in Explorer": "Gezgin'de göster", "Close": "Kapat",
    "Crop & Resize": "Kırp ve boyutlandır", "Aspect ratio": "En-boy oranı", "Free": "Serbest", "Original": "Orijinal",
    "Rotate & flip": "Döndür ve aynala", "Rotate left": "Sola döndür", "Rotate right": "Sağa döndür",
    "Flip horizontal": "Yatay aynala", "Flip vertical": "Dikey aynala", "Crop": "Kırpma", "Output size": "Çıktı boyutu",
    "Width": "Genişlik", "Height": "Yükseklik", "Keep proportions": "Oranı koru", "Save as": "Farklı biçimde kaydet",
    "Same as original": "Orijinalle aynı", "Reset": "Sıfırla", "Save copy": "Kopya kaydet",
    "Drag the box or its corners. Double-click the image to reset the crop.":
        "Kutuyu veya köşelerini sürükleyin. Kırpmayı sıfırlamak için görsele çift tıklayın.",
    "{app} — drag a file, tap {key}": "{app} — dosya sürükleyin, {key} basın", "Convert files…": "Dosya dönüştür…",
    "How it works": "Nasıl çalışır", "Settings…": "Ayarlar…", "Quit {app}": "{app} uygulamasından çık",
    "Choose files to convert": "Dönüştürülecek dosyaları seçin",
    "{app} Settings": "{app} Ayarları", "Language": "Dil", "App language": "Uygulama dili", "System default": "Sistem dili",
    "Wheel keys — tap while dragging a file": "Tekerlek tuşları — sürüklerken basın",
    "File drags only (recommended)": "Yalnızca dosya sürükleme (önerilen)", "Any mouse drag": "Her fare sürüklemesi",
    "Trigger on": "Tetikleyici", "Output": "Çıktı", "Next to the original file": "Orijinal dosyanın yanına",
    "Browse…": "Gözat…", "Output folder": "Çıktı klasörü", "Save to": "Kaydet",
    "Start {app} when I sign in": "Oturum açınca {app} başlat",
    "Add {app} to the Explorer right-click menu and Send To": "{app} uygulamasını sağ tık menüsüne ve Gönder'e ekle",
    "Ctrl + Alt + Space opens the wheel for files selected in Explorer":
        "Ctrl + Alt + Boşluk, Gezgin'de seçili dosyalar için tekerleği açar",
    "found": "bulundu", "not found — DOCX/PPTX/XLS conversions need Microsoft Office or LibreOffice":
        "bulunamadı — DOCX/PPTX/XLS için Microsoft Office veya LibreOffice gerekir",
    "{c}+ conversions · {t}+ tools · 8 actions": "{c}+ dönüştürme · {t}+ araç · 8 eylem",
    "Everything runs locally — nothing is uploaded.": "Her şey yerelde çalışır — hiçbir şey yüklenmez.",
    "Save": "Kaydet", "Each wheel needs a different key.": "Her tekerlek farklı bir tuş gerektirir.",
    "Couldn't update Windows integration:": "Windows entegrasyonu güncellenemedi:",
    "{app} — How it works": "{app} — Nasıl çalışır",
    "HELP_HTML": (
        "Gezgin'de veya masaüstünde <b>bir dosyayı sürükleyin</b> ve fareyi bırakmadan:<br><br>"
        "• dönüştürme tekerleği için <b>{convert}</b><br>"
        "• araçlar için <b>{tool}</b> (sıkıştır, kırp, kes, birleştir…)<br>"
        "• eylemler için <b>{action}</b> (kopyala, taşı, terminal, yüzen…)<br><br>"
        "Uygulamak için bir dilimin üzerine, iptal için ortaya bırakın.<br><br>"
        "<b>Sürüklemeden:</b> dosyaları seçip <b>Ctrl+Alt+Boşluk</b>'a basın veya sağ tık → <i>{app}</i>.<br><br>"
        "Sonuçlar orijinalin yanına kaydedilir. Hiçbir şey bilgisayarınızdan çıkmaz."),
}

# --------------------------------------------------------------------------- German
T["de"] = {
    "About": "Über",
    "Appearance": "Darstellung",
    "Dark": "Dunkel",
    "Donate": "Spenden",
    "Drag a file, tap a key, drop it on the wheel.": "Datei ziehen, Taste tippen, auf dem Rad ablegen.",
    "Free and open source (MIT License)": "Kostenlos und Open Source (MIT-Lizenz)",
    "GitHub page": "GitHub-Seite",
    "Last checked: {when}": "Zuletzt geprüft: {when}",
    "Light": "Hell",
    "Made by {who}": "Entwickelt von {who}",
    "Privacy policy": "Datenschutzerklärung",
    "Report a problem": "Problem melden",
    "Settings": "Einstellungen",
    "Theme": "Design",
    "Version {v}": "Version {v}",
    "never": "nie",
    "Cancel: {what} — {name}": "Abbrechen: {what} — {name}",
    "Cancel all ({n})": "Alle abbrechen ({n})",
    "Cancelled": "Abgebrochen",
    "Cancelling…": "Wird abgebrochen…",
    "Check for updates automatically (once a day)": "Automatisch nach Updates suchen (einmal täglich)",
    "Check for updates…": "Nach Updates suchen…",
    "Check now": "Jetzt prüfen",
    "Checking for updates…": "Suche nach Updates…",
    "Couldn't check for updates": "Update-Prüfung fehlgeschlagen",
    "Couldn't download the update": "Update konnte nicht geladen werden",
    "Couldn't start the installer": "Installer konnte nicht gestartet werden",
    "Download && install": "Herunterladen und installieren",
    "Downloading update…": "Update wird geladen…",
    "E-book": "E-Book",
    "Installing update…": "Update wird installiert…",
    "Later": "Später",
    "Nothing was saved.": "Es wurde nichts gespeichert.",
    "Open release page": "Release-Seite öffnen",
    "Skip this version": "Diese Version überspringen",
    "The only connection is the update check to GitHub.": "Die einzige Verbindung ist die Update-Prüfung bei GitHub.",
    "The update was not downloaded.": "Das Update wurde nicht geladen.",
    "Updates": "Updates",
    "You have {v}.": "Installiert: {v}.",
    "You're up to date": "Alles aktuell",
    "smaller file": "kleinere Datei",
    "{app} update": "{app}-Update",
    "Finish the steps in the setup window.": "Schließen Sie die Schritte im Setup-Fenster ab.",
    "{app} {v} is available": "{app} {v} ist verfügbar",
    "{app} {v} is the latest version.": "{app} {v} ist die neueste Version.",
    "Scroll the mouse wheel while dragging to open the wheel and move between slices": "Beim Ziehen mit dem Mausrad das Rad öffnen und zwischen Segmenten wechseln",
    "HELP_SCROLL": "<b>Mausrad:</b> beim Ziehen scrollen, um das Rad zu öffnen, weiter scrollen, um zwischen Segmenten zu wechseln, dann loslassen, um das markierte anzuwenden. Esc bricht ab.",
    "Couldn't read the dragged file": "Gezogene Datei konnte nicht gelesen werden",
    "Try again, or select it and press Ctrl+Alt+Space": "Erneut versuchen oder auswählen und Strg+Alt+Leertaste drücken",
    "needs WinRAR": "benötigt WinRAR",
    "Convert": "Umwandeln", "Tools": "Werkzeuge", "Actions": "Aktionen", "Ctrl": "Strg", "CapsLock": "Feststell",
    "Image": "Bild", "Video": "Video", "Audio": "Audio", "Document": "Dokument", "Slides": "Präsentation",
    "Spreadsheet": "Tabelle", "Subtitles": "Untertitel", "Archive": "Archiv", "Folder": "Ordner", "Files": "Dateien", "File": "Datei",
    "Compress": "Komprimieren", "Crop & Resize…": "Zuschneiden…", "Rotate 90°": "90° drehen", "Flip": "Spiegeln",
    "Grayscale": "Graustufen", "Strip metadata": "Metadaten entfernen", "Combine PDF": "Zu PDF kombinieren",
    "Trim…": "Kürzen…", "Mute": "Stumm", "Snapshot…": "Standbild…", "Speed 2×": "Tempo 2×", "Merge": "Zusammenfügen",
    "Normalize": "Normalisieren", "Mono": "Mono", "Fade in/out": "Ein-/Ausblenden", "Split pages": "Seiten trennen",
    "Extract pages…": "Seiten extrahieren…", "Extract images": "Bilder extrahieren", "Password…": "Passwort…",
    "Zip": "Zip", "Extract": "Entpacken",
    "Copy": "Kopieren", "Copy path": "Pfad kopieren", "Move to…": "Verschieben…", "Copy to…": "Kopieren nach…",
    "Terminal": "Terminal", "Float": "Schwebend", "Show": "Zeigen", "Open with…": "Öffnen mit…",
    "to clipboard": "in Zwischenablage", "open here": "hier öffnen", "in Explorer": "im Explorer", "audio only": "nur Audio",
    "No conversions": "Keine Umwandlung", "try Tools or Actions": "Werkzeuge oder Aktionen probieren",
    "Cancel": "Abbrechen", "drop here": "hier ablegen", "move to read file": "bewegen, um Datei zu lesen",
    "{n} files": "{n} Dateien",
    "Start": "Anfang", "End": "Ende", "At time": "Zeitpunkt", "Pages (e.g. 1-3,5)": "Seiten (z. B. 1-3,5)",
    "Password": "Passwort", "seconds, m:ss or h:mm:ss": "Sekunden, m:ss oder h:mm:ss", "Apply": "Anwenden",
    "Copied to clipboard": "In die Zwischenablage kopiert", "{n} item(s) — paste anywhere": "{n} Element(e) — überall einfügen",
    "Path copied": "Pfad kopiert", "{n} paths": "{n} Pfade", "Move to": "Verschieben nach", "Moved": "Verschoben",
    "Copy to": "Kopieren nach", "Copied": "Kopiert", "{n} items saved": "{n} Elemente gespeichert",
    "Converting to {fmt}…": "Umwandeln in {fmt}…", "Converted to {fmt}": "In {fmt} umgewandelt", "Done": "Fertig",
    "{what} failed": "Fehlgeschlagen: {what}", "Couldn't do that": "Nicht möglich", "Couldn't open image": "Bild konnte nicht geöffnet werden",
    "Nothing selected": "Nichts ausgewählt",
    "Select files in File Explorer, then press Ctrl+Alt+Space": "Dateien im Explorer auswählen, dann Strg+Alt+Leertaste",
    "Running in the tray. Drag a file and tap {key}.": "Läuft im Infobereich. Datei ziehen und {key} tippen.",
    "Drag to move · drag ⠿ to drop the file · double-click to open · scroll to resize":
        "Ziehen zum Verschieben · ⠿ ziehen, um die Datei abzulegen · Doppelklick zum Öffnen · Scrollen für Größe",
    "Open": "Öffnen", "Show in Explorer": "Im Explorer zeigen", "Close": "Schließen",
    "Crop & Resize": "Zuschneiden & Größe ändern", "Aspect ratio": "Seitenverhältnis", "Free": "Frei", "Original": "Original",
    "Rotate & flip": "Drehen & Spiegeln", "Rotate left": "Links drehen", "Rotate right": "Rechts drehen",
    "Flip horizontal": "Horizontal spiegeln", "Flip vertical": "Vertikal spiegeln", "Crop": "Zuschnitt",
    "Output size": "Ausgabegröße", "Width": "Breite", "Height": "Höhe", "Keep proportions": "Proportionen beibehalten",
    "Save as": "Speichern als", "Same as original": "Wie Original", "Reset": "Zurücksetzen", "Save copy": "Kopie speichern",
    "Drag the box or its corners. Double-click the image to reset the crop.":
        "Rahmen oder Ecken ziehen. Doppelklick auf das Bild setzt den Zuschnitt zurück.",
    "{app} — drag a file, tap {key}": "{app} — Datei ziehen, {key} tippen", "Convert files…": "Dateien umwandeln…",
    "How it works": "So funktioniert's", "Settings…": "Einstellungen…", "Quit {app}": "{app} beenden",
    "Choose files to convert": "Dateien zum Umwandeln wählen",
    "{app} Settings": "{app}-Einstellungen", "Language": "Sprache", "App language": "App-Sprache", "System default": "Systemsprache",
    "Wheel keys — tap while dragging a file": "Rad-Tasten — beim Ziehen tippen",
    "File drags only (recommended)": "Nur Datei-Ziehen (empfohlen)", "Any mouse drag": "Jedes Ziehen mit der Maus",
    "Trigger on": "Auslösen bei", "Output": "Ausgabe", "Next to the original file": "Neben der Originaldatei",
    "Browse…": "Durchsuchen…", "Output folder": "Ausgabeordner", "Save to": "Speichern in",
    "Start {app} when I sign in": "{app} bei der Anmeldung starten",
    "Add {app} to the Explorer right-click menu and Send To": "{app} zum Rechtsklick-Menü und „Senden an“ hinzufügen",
    "Ctrl + Alt + Space opens the wheel for files selected in Explorer":
        "Strg + Alt + Leertaste öffnet das Rad für im Explorer gewählte Dateien",
    "found": "gefunden", "not found — DOCX/PPTX/XLS conversions need Microsoft Office or LibreOffice":
        "nicht gefunden — DOCX/PPTX/XLS benötigen Microsoft Office oder LibreOffice",
    "{c}+ conversions · {t}+ tools · 8 actions": "{c}+ Umwandlungen · {t}+ Werkzeuge · 8 Aktionen",
    "Everything runs locally — nothing is uploaded.": "Alles läuft lokal — nichts wird hochgeladen.",
    "Save": "Speichern", "Each wheel needs a different key.": "Jedes Rad braucht eine andere Taste.",
    "Couldn't update Windows integration:": "Windows-Integration konnte nicht aktualisiert werden:",
    "{app} — How it works": "{app} — So funktioniert's",
    "HELP_HTML": (
        "<b>Ziehen Sie eine Datei</b> im Explorer oder auf dem Desktop und tippen Sie bei gedrückter Maustaste:<br><br>"
        "• <b>{convert}</b> für das Umwandlungsrad<br>"
        "• <b>{tool}</b> für Werkzeuge (komprimieren, zuschneiden, kürzen, zusammenfügen…)<br>"
        "• <b>{action}</b> für Aktionen (kopieren, verschieben, Terminal, schwebend…)<br><br>"
        "Auf einem Segment ablegen zum Anwenden, in der Mitte zum Abbrechen.<br><br>"
        "<b>Ohne Ziehen:</b> Dateien wählen und <b>Strg+Alt+Leertaste</b> drücken oder Rechtsklick → <i>{app}</i>.<br><br>"
        "Ergebnisse werden neben dem Original gespeichert. Nichts verlässt Ihren PC."),
}


# --------------------------------------------------------------------------- more languages (locales/*.py)
from locales import ru, zh, ja, pt, it, hi, fa, ur  # noqa: E402  (explicit imports so PyInstaller bundles them)

for _code, _mod in (("ru", ru), ("zh", zh), ("ja", ja), ("pt", pt), ("it", it), ("hi", hi), ("fa", fa), ("ur", ur)):
    T[_code] = _mod.T
    LANGUAGES.append((_code, _mod.NAME))
    if _mod.RTL:
        RTL.add(_code)

# --------------------------------------------------------------------------- strings added in 1.1.5
for _code, (_a, _b) in {
    "ar": ("لا توجد أدوات", "جرّب التحويل أو الإجراءات"), "fr": ("Aucun outil", "essayez Convertir ou Actions"),
    "es": ("Sin herramientas", "prueba Convertir o Acciones"), "tr": ("Araç yok", "Dönüştür veya Eylemler'i deneyin"),
    "de": ("Keine Werkzeuge", "Umwandeln oder Aktionen probieren"), "ru": ("Нет инструментов", "попробуйте Конвертировать или Действия"),
    "zh": ("无可用工具", "试试转换或操作"), "ja": ("ツールはありません", "変換かアクションをお試しください"),
    "pt": ("Sem ferramentas", "experimente Converter ou Ações"), "it": ("Nessuno strumento", "prova Converti o Azioni"),
    "hi": ("कोई टूल नहीं", "बदलें या कार्य आज़माएँ"), "fa": ("ابزاری وجود ندارد", "تبدیل یا کارها را امتحان کنید"),
    "ur": ("کوئی ٹول نہیں", "تبدیل کریں یا افعال آزمائیں"),
}.items():
    T[_code].update({"No tools": _a, "try Convert or Actions": _b})

# --------------------------------------------------------------------------- strings added in 1.2 (Float)
_F12 = {
    "ar": ("مسار الصوت", "إيقاف", "المسار {n}", "تشغيل الفيديو والموسيقى فور فتحها في النافذة العائمة"),
    "fr": ("Piste audio", "Désactivés", "Piste {n}", "Lire les vidéos et la musique dès leur ouverture en mode flottant"),
    "es": ("Pista de audio", "Desactivados", "Pista {n}", "Reproducir vídeos y música en cuanto se abran en flotante"),
    "tr": ("Ses parçası", "Kapalı", "Parça {n}", "Videoları ve müziği yüzen pencerede açılır açılmaz oynat"),
    "de": ("Tonspur", "Aus", "Spur {n}", "Videos und Musik sofort abspielen, wenn sie schwebend geöffnet werden"),
    "ru": ("Звуковая дорожка", "Выкл.", "Дорожка {n}", "Сразу воспроизводить видео и музыку, открытые поверх окон"),
    "zh": ("音轨", "关闭", "轨道 {n}", "在置顶浮窗中打开视频和音乐时立即播放"),
    "ja": ("音声トラック", "オフ", "トラック {n}", "最前面に固定したビデオや音楽をすぐに再生する"),
    "pt": ("Faixa de áudio", "Desativadas", "Faixa {n}", "Reproduzir vídeos e música assim que abrirem no modo flutuante"),
    "it": ("Traccia audio", "Disattivati", "Traccia {n}", "Riproduci video e musica appena si aprono in modalità fluttuante"),
    "hi": ("ऑडियो ट्रैक", "बंद", "ट्रैक {n}", "ऊपर टिकाए जाने पर वीडियो और संगीत तुरंत चलाएँ"),
    "fa": ("ترک صدا", "خاموش", "ترک {n}", "پخش ویدیو و موسیقی به‌محض باز شدن در حالت شناور"),
    "ur": ("آڈیو ٹریک", "بند", "ٹریک {n}", "اوپر رکھے جانے پر ویڈیو اور موسیقی فوراً چلائیں"),
}
for _code, (_a, _b, _c, _d) in _F12.items():
    T[_code].update({"Audio track": _a, "Off": _b, "Track {n}": _c,
                     "Play videos and music as soon as they open in Float": _d})

from locales import images12 as _im12  # noqa: E402

for _code, _vals in _im12.T.items():
    assert len(_vals) == len(_im12.KEYS), _code
    T[_code].update(dict(zip(_im12.KEYS, _vals)))

for _code, _v in {"ar": "حفظ صورة الحافظة هنا", "fr": "Enregistrer l'image du presse-papiers ici",
                  "es": "Guardar aquí la imagen del portapapeles", "tr": "Panodaki görüntüyü buraya kaydet",
                  "de": "Bild aus der Zwischenablage hier speichern", "ru": "Сохранить сюда изображение из буфера",
                  "zh": "将剪贴板图片保存到这里", "ja": "クリップボードの画像をここに保存",
                  "pt": "Salvar aqui a imagem da área de transferência", "it": "Salva qui l'immagine degli appunti",
                  "hi": "क्लिपबोर्ड की छवि यहाँ सहेजें", "fa": "ذخیرهٔ تصویر کلیپ‌بورد در اینجا",
                  "ur": "کلپ بورڈ کی تصویر یہاں محفوظ کریں"}.items():
    T[_code]["Save clipboard image here"] = _v
for _code, _v in {"ar": "يجب أن يكون وقت النهاية بعد البداية", "fr": "La fin doit être après le début",
                  "es": "El final debe ser posterior al inicio", "tr": "Bitiş, başlangıçtan sonra olmalı",
                  "de": "Das Ende muss nach dem Anfang liegen", "ru": "Конец должен быть позже начала",
                  "zh": "结束时间必须晚于开始时间", "ja": "終了は開始より後にしてください",
                  "pt": "O fim deve ser depois do início", "it": "La fine deve essere dopo l'inizio",
                  "hi": "अंत, शुरुआत के बाद होना चाहिए", "fa": "پایان باید بعد از شروع باشد",
                  "ur": "اختتام آغاز کے بعد ہونا چاہیے"}.items():
    T[_code]["End must be after Start"] = _v

from locales import media12 as _md12  # noqa: E402

for _code, _vals in _md12.T.items():
    assert len(_vals) == len(_md12.KEYS), _code
    T[_code].update(dict(zip(_md12.KEYS, _vals)))

from locales import speech12 as _sp12  # noqa: E402

for _code, _vals in _sp12.T.items():
    assert len(_vals) == len(_sp12.KEYS), _code
    T[_code].update(dict(zip(_sp12.KEYS, _vals)))

from locales import float12b as _f12b  # noqa: E402

for _code, _vals in _f12b.T.items():
    assert len(_vals) == len(_f12b.KEYS), _code
    T[_code].update(dict(zip(_f12b.KEYS, _vals)))
    if "Compress" in T[_code]:
        T[_code].setdefault("Compress…", T[_code]["Compress"] + "…")

from locales import float12c as _f12c  # noqa: E402

for _code, _vals in _f12c.T.items():
    assert len(_vals) == len(_f12c.KEYS), _code
    T[_code].update(dict(zip(_f12c.KEYS, _vals)))

from locales import subs12 as _s12  # noqa: E402

for _code, _vals in _s12.T.items():
    assert len(_vals) == len(_s12.KEYS), _code
    T[_code].update(dict(zip(_s12.KEYS, _vals)))

from locales import update12 as _u12  # noqa: E402

for _code, _vals in _u12.T.items():
    assert len(_vals) == len(_u12.KEYS), _code
    T[_code].update(dict(zip(_u12.KEYS, _vals)))

from locales import mine12 as _m12  # noqa: E402

for _code, _vals in _m12.T.items():
    assert len(_vals) == len(_m12.KEYS), _code
    T[_code].update(dict(zip(_m12.KEYS, _vals)))

from locales import ux12 as _x12  # noqa: E402

for _code, _vals in _x12.T.items():
    assert len(_vals) == len(_x12.KEYS), _code
    T[_code].update(dict(zip(_x12.KEYS, _vals)))

for _code, _live in {"ar": "مباشر", "fr": "EN DIRECT", "es": "EN DIRECTO", "tr": "CANLI", "de": "LIVE", "ru": "ПРЯМОЙ ЭФИР",
                     "zh": "直播", "ja": "ライブ", "pt": "AO VIVO", "it": "IN DIRETTA", "hi": "लाइव", "fa": "زنده",
                     "ur": "براہ راست"}.items():
    T[_code]["LIVE"] = _live

from locales import pdf12 as _p12  # noqa: E402

for _code, _vals in _p12.T.items():
    assert len(_vals) == len(_p12.KEYS), _code
    T[_code].update(dict(zip(_p12.KEYS, _vals)))

from locales import pdf12b as _p12b  # noqa: E402

for _code, _vals in _p12b.T.items():
    assert len(_vals) == len(_p12b.KEYS), _code
    T[_code].update(dict(zip(_p12b.KEYS, _vals)))

from locales import pdf12c as _p12c  # noqa: E402

for _code, _vals in _p12c.T.items():
    assert len(_vals) == len(_p12c.KEYS), _code
    T[_code].update(dict(zip(_p12c.KEYS, _vals)))

from locales import comic12 as _c12  # noqa: E402

for _code, _vals in _c12.T.items():
    assert len(_vals) == len(_c12.KEYS), _code
    T[_code].update(dict(zip(_c12.KEYS, _vals)))

from locales import files12 as _f12f  # noqa: E402

for _code, _vals in _f12f.T.items():
    assert len(_vals) == len(_f12f.KEYS), (_code, len(_vals), len(_f12f.KEYS))
    T[_code].update(dict(zip(_f12f.KEYS, _vals)))

from locales import share12 as _sh12  # noqa: E402

for _code, _vals in _sh12.T.items():
    assert len(_vals) == len(_sh12.KEYS), _code
    T[_code].update(dict(zip(_sh12.KEYS, _vals)))

from locales import share12b as _sh12b  # noqa: E402

for _code, _vals in _sh12b.T.items():
    assert len(_vals) == len(_sh12b.KEYS), _code
    T[_code].update(dict(zip(_sh12b.KEYS, _vals)))

from locales import stream12 as _st12  # noqa: E402

for _code, _vals in _st12.T.items():
    assert len(_vals) == len(_st12.KEYS), _code
    T[_code].update(dict(zip(_st12.KEYS, _vals)))

from locales import send12 as _sd12  # noqa: E402

for _code, _vals in _sd12.T.items():
    assert len(_vals) == len(_sd12.KEYS), (_code, len(_vals))
    T[_code].update(dict(zip(_sd12.KEYS, _vals)))

from locales import send12b as _sd12b  # noqa: E402

for _code, _vals in _sd12b.T.items():
    assert len(_vals) == len(_sd12b.KEYS), _code
    T[_code].update(dict(zip(_sd12b.KEYS, _vals)))
