"""1.2: repeat/loop in Float, command line in Settings."""
KEYS = [
    "Command line", "Loop", "Loop all (the whole folder)", "Open a Command Prompt", "Repeat", "Repeat this one",
    "Use DragWheel in Command Prompt or in your own scripts, e.g. <b>dragwheel convert photo.heic --to jpg</b>. "
    "The button opens a Command Prompt in Downloads with the list of commands.",
]
T = {
    "ar": ["سطر الأوامر", "تكرار", "تكرار الكل (المجلد كاملًا)", "فتح موجه الأوامر", "التكرار", "تكرار هذا فقط",
           "استخدم DragWheel في موجه الأوامر أو في سكربتاتك، مثل <b>dragwheel convert photo.heic --to jpg</b>. "
           "يفتح الزر موجه الأوامر في مجلد التنزيلات مع قائمة الأوامر."],
    "fr": ["Ligne de commande", "En boucle", "Tout en boucle (tout le dossier)", "Ouvrir une invite de commandes", "Répéter", "Répéter celui-ci",
           "Utilisez DragWheel dans l'invite de commandes ou vos scripts, p. ex. <b>dragwheel convert photo.heic --to jpg</b>. "
           "Le bouton ouvre une invite de commandes dans Téléchargements avec la liste des commandes."],
    "es": ["Línea de comandos", "En bucle", "Todo en bucle (toda la carpeta)", "Abrir el símbolo del sistema", "Repetir", "Repetir este",
           "Usa DragWheel en el símbolo del sistema o en tus scripts, p. ej. <b>dragwheel convert photo.heic --to jpg</b>. "
           "El botón abre el símbolo del sistema en Descargas con la lista de comandos."],
    "tr": ["Komut satırı", "Döngü", "Hepsini döngüye al (tüm klasör)", "Komut İstemi'ni aç", "Tekrarla", "Bunu tekrarla",
           "DragWheel'i Komut İstemi'nde ya da kendi betiklerinizde kullanın; ör. <b>dragwheel convert photo.heic --to jpg</b>. "
           "Düğme, İndirilenler'de komut listesiyle bir Komut İstemi açar."],
    "de": ["Befehlszeile", "Endlos", "Alles endlos (ganzer Ordner)", "Eingabeaufforderung öffnen", "Wiederholen", "Diesen wiederholen",
           "DragWheel in der Eingabeaufforderung oder in eigenen Skripten nutzen, z. B. <b>dragwheel convert photo.heic --to jpg</b>. "
           "Die Schaltfläche öffnet eine Eingabeaufforderung in Downloads mit der Liste der Befehle."],
    "ru": ["Командная строка", "По кругу", "Всё по кругу (вся папка)", "Открыть командную строку", "Повтор", "Повторять этот",
           "Используйте DragWheel в командной строке или в своих скриптах, например <b>dragwheel convert photo.heic --to jpg</b>. "
           "Кнопка открывает командную строку в папке «Загрузки» со списком команд."],
    "zh": ["命令行", "循环", "全部循环（整个文件夹）", "打开命令提示符", "重复", "单曲重复",
           "在命令提示符或你自己的脚本中使用 DragWheel，例如 <b>dragwheel convert photo.heic --to jpg</b>。按钮会在“下载”中打开命令提示符并列出命令。"],
    "ja": ["コマンドライン", "ループ", "すべてループ（フォルダー全体）", "コマンド プロンプトを開く", "リピート", "この 1 つをリピート",
           "コマンド プロンプトや自作スクリプトで DragWheel を使えます。例: <b>dragwheel convert photo.heic --to jpg</b>。"
           "ボタンを押すと、ダウンロード フォルダーでコマンド一覧付きのコマンド プロンプトが開きます。"],
    "pt": ["Linha de comandos", "Em ciclo", "Tudo em ciclo (a pasta toda)", "Abrir a Linha de Comandos", "Repetir", "Repetir este",
           "Use o DragWheel na Linha de Comandos ou nos seus scripts, p. ex. <b>dragwheel convert photo.heic --to jpg</b>. "
           "O botão abre a Linha de Comandos nas Transferências com a lista de comandos."],
    "it": ["Riga di comando", "In loop", "Tutto in loop (l'intera cartella)", "Apri il prompt dei comandi", "Ripeti", "Ripeti questo",
           "Usa DragWheel nel prompt dei comandi o nei tuoi script, es. <b>dragwheel convert photo.heic --to jpg</b>. "
           "Il pulsante apre il prompt dei comandi in Download con l'elenco dei comandi."],
    "hi": ["कमांड लाइन", "लूप", "सब लूप करें (पूरा फ़ोल्डर)", "कमांड प्रॉम्प्ट खोलें", "दोहराएँ", "इसे दोहराएँ",
           "DragWheel को कमांड प्रॉम्प्ट या अपनी स्क्रिप्ट में इस्तेमाल करें, जैसे <b>dragwheel convert photo.heic --to jpg</b>। "
           "बटन Downloads में कमांड की सूची के साथ कमांड प्रॉम्प्ट खोलता है।"],
    "fa": ["خط فرمان", "حلقه", "حلقهٔ همه (کل پوشه)", "باز کردن خط فرمان", "تکرار", "تکرار همین یکی",
           "از DragWheel در خط فرمان یا اسکریپت‌های خودتان استفاده کنید، مثلاً <b>dragwheel convert photo.heic --to jpg</b>. "
           "این دکمه خط فرمان را در پوشهٔ دانلودها با فهرست فرمان‌ها باز می‌کند."],
    "ur": ["کمانڈ لائن", "لوپ", "سب کو لوپ کریں (پورا فولڈر)", "کمانڈ پرامپٹ کھولیں", "دہرائیں", "یہ والا دہرائیں",
           "DragWheel کو کمانڈ پرامپٹ یا اپنی اسکرپٹس میں استعمال کریں، مثلاً <b>dragwheel convert photo.heic --to jpg</b>۔ "
           "بٹن Downloads میں کمانڈز کی فہرست کے ساتھ کمانڈ پرامپٹ کھولتا ہے۔"],
}
