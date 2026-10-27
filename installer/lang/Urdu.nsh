;Language: Urdu (1056) — written for DragWheel; NSIS has no Urdu of its own

!insertmacro LANGFILE "Urdu" "Urdu" "اردو" "Urdu"

!ifdef MUI_WELCOMEPAGE
  ${LangFileString} MUI_TEXT_WELCOME_INFO_TITLE "$(^NameDA) سیٹ اپ میں خوش آمدید"
  ${LangFileString} MUI_TEXT_WELCOME_INFO_TEXT "سیٹ اپ $(^NameDA) کی انسٹالیشن میں آپ کی رہنمائی کرے گا۔$\r$\n$\r$\nسیٹ اپ شروع کرنے سے پہلے دوسری تمام ایپس بند کر دینا بہتر ہے۔$\r$\n$\r$\n$_CLICK"
!endif

!ifdef MUI_UNWELCOMEPAGE
  ${LangFileString} MUI_UNTEXT_WELCOME_INFO_TITLE "$(^NameDA) ان انسٹال میں خوش آمدید"
  ${LangFileString} MUI_UNTEXT_WELCOME_INFO_TEXT "سیٹ اپ $(^NameDA) کو ان انسٹال کرنے میں آپ کی رہنمائی کرے گا۔$\r$\n$\r$\nان انسٹال شروع کرنے سے پہلے یقینی بنائیں کہ $(^NameDA) چل نہیں رہا۔$\r$\n$\r$\n$_CLICK"
!endif

!ifdef MUI_LICENSEPAGE
  ${LangFileString} MUI_TEXT_LICENSE_TITLE "لائسنس معاہدہ"
  ${LangFileString} MUI_TEXT_LICENSE_SUBTITLE "$(^NameDA) انسٹال کرنے سے پہلے لائسنس کی شرائط پڑھ لیں۔"
  ${LangFileString} MUI_INNERTEXT_LICENSE_BOTTOM "اگر آپ معاہدے کی شرائط قبول کرتے ہیں تو جاری رکھنے کے لیے میں متفق ہوں پر کلک کریں۔ $(^NameDA) انسٹال کرنے کے لیے معاہدہ قبول کرنا ضروری ہے۔"
  ${LangFileString} MUI_INNERTEXT_LICENSE_BOTTOM_CHECKBOX "اگر آپ معاہدے کی شرائط قبول کرتے ہیں تو نیچے دیے گئے خانے پر کلک کریں۔ $(^NameDA) انسٹال کرنے کے لیے معاہدہ قبول کرنا ضروری ہے۔ $_CLICK"
  ${LangFileString} MUI_INNERTEXT_LICENSE_BOTTOM_RADIOBUTTONS "اگر آپ معاہدے کی شرائط قبول کرتے ہیں تو نیچے پہلا اختیار منتخب کریں۔ $(^NameDA) انسٹال کرنے کے لیے معاہدہ قبول کرنا ضروری ہے۔ $_CLICK"
!endif

!ifdef MUI_UNLICENSEPAGE
  ${LangFileString} MUI_UNTEXT_LICENSE_TITLE "لائسنس معاہدہ"
  ${LangFileString} MUI_UNTEXT_LICENSE_SUBTITLE "$(^NameDA) ان انسٹال کرنے سے پہلے لائسنس کی شرائط پڑھ لیں۔"
  ${LangFileString} MUI_UNINNERTEXT_LICENSE_BOTTOM "اگر آپ معاہدے کی شرائط قبول کرتے ہیں تو جاری رکھنے کے لیے میں متفق ہوں پر کلک کریں۔ $(^NameDA) ان انسٹال کرنے کے لیے معاہدہ قبول کرنا ضروری ہے۔"
  ${LangFileString} MUI_UNINNERTEXT_LICENSE_BOTTOM_CHECKBOX "اگر آپ معاہدے کی شرائط قبول کرتے ہیں تو نیچے دیے گئے خانے پر کلک کریں۔ $(^NameDA) ان انسٹال کرنے کے لیے معاہدہ قبول کرنا ضروری ہے۔ $_CLICK"
  ${LangFileString} MUI_UNINNERTEXT_LICENSE_BOTTOM_RADIOBUTTONS "اگر آپ معاہدے کی شرائط قبول کرتے ہیں تو نیچے پہلا اختیار منتخب کریں۔ $(^NameDA) ان انسٹال کرنے کے لیے معاہدہ قبول کرنا ضروری ہے۔ $_CLICK"
!endif

!ifdef MUI_LICENSEPAGE | MUI_UNLICENSEPAGE
  ${LangFileString} MUI_INNERTEXT_LICENSE_TOP "باقی معاہدہ دیکھنے کے لیے Page Down دبائیں۔"
!endif

!ifdef MUI_COMPONENTSPAGE
  ${LangFileString} MUI_TEXT_COMPONENTS_TITLE "اجزاء منتخب کریں"
  ${LangFileString} MUI_TEXT_COMPONENTS_SUBTITLE "منتخب کریں کہ $(^NameDA) کی کون سی خصوصیات انسٹال کرنی ہیں۔"
!endif

!ifdef MUI_UNCOMPONENTSPAGE
  ${LangFileString} MUI_UNTEXT_COMPONENTS_TITLE "اجزاء منتخب کریں"
  ${LangFileString} MUI_UNTEXT_COMPONENTS_SUBTITLE "منتخب کریں کہ $(^NameDA) کی کون سی خصوصیات ان انسٹال کرنی ہیں۔"
!endif

!ifdef MUI_COMPONENTSPAGE | MUI_UNCOMPONENTSPAGE
  ${LangFileString} MUI_INNERTEXT_COMPONENTS_DESCRIPTION_TITLE "تفصیل"
  !ifndef NSIS_CONFIG_COMPONENTPAGE_ALTERNATIVE
    ${LangFileString} MUI_INNERTEXT_COMPONENTS_DESCRIPTION_INFO "کسی جزو کی تفصیل دیکھنے کے لیے اس پر ماؤس لے جائیں۔"
  !else
    ${LangFileString} MUI_INNERTEXT_COMPONENTS_DESCRIPTION_INFO "کسی جزو کی تفصیل دیکھنے کے لیے اسے منتخب کریں۔"
  !endif
!endif

!ifdef MUI_DIRECTORYPAGE
  ${LangFileString} MUI_TEXT_DIRECTORY_TITLE "انسٹال کی جگہ منتخب کریں"
  ${LangFileString} MUI_TEXT_DIRECTORY_SUBTITLE "وہ فولڈر منتخب کریں جس میں $(^NameDA) انسٹال کرنا ہے۔"
!endif

!ifdef MUI_UNDIRECTORYPAGE
  ${LangFileString} MUI_UNTEXT_DIRECTORY_TITLE "ان انسٹال کی جگہ منتخب کریں"
  ${LangFileString} MUI_UNTEXT_DIRECTORY_SUBTITLE "وہ فولڈر منتخب کریں جس سے $(^NameDA) ان انسٹال کرنا ہے۔"
!endif

!ifdef MUI_INSTFILESPAGE
  ${LangFileString} MUI_TEXT_INSTALLING_TITLE "انسٹال ہو رہا ہے"
  ${LangFileString} MUI_TEXT_INSTALLING_SUBTITLE "براہ کرم انتظار کریں، $(^NameDA) انسٹال ہو رہا ہے۔"
  ${LangFileString} MUI_TEXT_FINISH_TITLE "انسٹالیشن مکمل"
  ${LangFileString} MUI_TEXT_FINISH_SUBTITLE "سیٹ اپ کامیابی سے مکمل ہو گیا۔"
  ${LangFileString} MUI_TEXT_ABORT_TITLE "انسٹالیشن روک دی گئی"
  ${LangFileString} MUI_TEXT_ABORT_SUBTITLE "سیٹ اپ کامیابی سے مکمل نہیں ہوا۔"
!endif

!ifdef MUI_UNINSTFILESPAGE
  ${LangFileString} MUI_UNTEXT_UNINSTALLING_TITLE "ان انسٹال ہو رہا ہے"
  ${LangFileString} MUI_UNTEXT_UNINSTALLING_SUBTITLE "براہ کرم انتظار کریں، $(^NameDA) ان انسٹال ہو رہا ہے۔"
  ${LangFileString} MUI_UNTEXT_FINISH_TITLE "ان انسٹالیشن مکمل"
  ${LangFileString} MUI_UNTEXT_FINISH_SUBTITLE "ان انسٹال کامیابی سے مکمل ہو گیا۔"
  ${LangFileString} MUI_UNTEXT_ABORT_TITLE "ان انسٹالیشن روک دی گئی"
  ${LangFileString} MUI_UNTEXT_ABORT_SUBTITLE "ان انسٹال کامیابی سے مکمل نہیں ہوا۔"
!endif

!ifdef MUI_FINISHPAGE
  ${LangFileString} MUI_TEXT_FINISH_INFO_TITLE "$(^NameDA) سیٹ اپ مکمل ہو رہا ہے"
  ${LangFileString} MUI_TEXT_FINISH_INFO_TEXT "$(^NameDA) آپ کے کمپیوٹر پر انسٹال ہو گیا ہے۔$\r$\n$\r$\nسیٹ اپ بند کرنے کے لیے ختم پر کلک کریں۔"
  ${LangFileString} MUI_TEXT_FINISH_INFO_REBOOT "$(^NameDA) کی انسٹالیشن مکمل کرنے کے لیے کمپیوٹر دوبارہ شروع کرنا ضروری ہے۔ کیا آپ ابھی دوبارہ شروع کرنا چاہتے ہیں؟"
!endif

!ifdef MUI_UNFINISHPAGE
  ${LangFileString} MUI_UNTEXT_FINISH_INFO_TITLE "$(^NameDA) ان انسٹال مکمل ہو رہا ہے"
  ${LangFileString} MUI_UNTEXT_FINISH_INFO_TEXT "$(^NameDA) آپ کے کمپیوٹر سے ان انسٹال ہو گیا ہے۔$\r$\n$\r$\nسیٹ اپ بند کرنے کے لیے ختم پر کلک کریں۔"
  ${LangFileString} MUI_UNTEXT_FINISH_INFO_REBOOT "$(^NameDA) کی ان انسٹالیشن مکمل کرنے کے لیے کمپیوٹر دوبارہ شروع کرنا ضروری ہے۔ کیا آپ ابھی دوبارہ شروع کرنا چاہتے ہیں؟"
!endif

!ifdef MUI_FINISHPAGE | MUI_UNFINISHPAGE
  ${LangFileString} MUI_TEXT_FINISH_REBOOTNOW "ابھی دوبارہ شروع کریں"
  ${LangFileString} MUI_TEXT_FINISH_REBOOTLATER "میں بعد میں خود دوبارہ شروع کروں گا"
  ${LangFileString} MUI_TEXT_FINISH_RUN "$(^NameDA) &چلائیں"
  ${LangFileString} MUI_TEXT_FINISH_SHOWREADME "&Readme دکھائیں"
  ${LangFileString} MUI_BUTTONTEXT_FINISH "&ختم"
!endif

!ifdef MUI_STARTMENUPAGE
  ${LangFileString} MUI_TEXT_STARTMENU_TITLE "اسٹارٹ مینو فولڈر منتخب کریں"
  ${LangFileString} MUI_TEXT_STARTMENU_SUBTITLE "$(^NameDA) کے شارٹ کٹس کے لیے اسٹارٹ مینو فولڈر منتخب کریں۔"
  ${LangFileString} MUI_INNERTEXT_STARTMENU_TOP "وہ اسٹارٹ مینو فولڈر منتخب کریں جس میں ایپ کے شارٹ کٹس بنانے ہیں۔ نیا فولڈر بنانے کے لیے نام بھی لکھ سکتے ہیں۔"
  ${LangFileString} MUI_INNERTEXT_STARTMENU_CHECKBOX "شارٹ کٹس نہ بنائیں"
!endif

!ifdef MUI_UNCONFIRMPAGE
  ${LangFileString} MUI_UNTEXT_CONFIRM_TITLE "$(^NameDA) ان انسٹال کریں"
  ${LangFileString} MUI_UNTEXT_CONFIRM_SUBTITLE "$(^NameDA) کو اپنے کمپیوٹر سے ہٹائیں۔"
!endif

!ifdef MUI_ABORTWARNING
  ${LangFileString} MUI_TEXT_ABORTWARNING "کیا آپ واقعی $(^Name) سیٹ اپ بند کرنا چاہتے ہیں؟"
!endif

!ifdef MUI_UNABORTWARNING
  ${LangFileString} MUI_UNTEXT_ABORTWARNING "کیا آپ واقعی $(^Name) ان انسٹال بند کرنا چاہتے ہیں؟"
!endif

!ifdef MULTIUSER_INSTALLMODEPAGE
  ${LangFileString} MULTIUSER_TEXT_INSTALLMODE_TITLE "صارفین منتخب کریں"
  ${LangFileString} MULTIUSER_TEXT_INSTALLMODE_SUBTITLE "منتخب کریں کہ $(^NameDA) کن صارفین کے لیے انسٹال کرنا ہے۔"
  ${LangFileString} MULTIUSER_INNERTEXT_INSTALLMODE_TOP "منتخب کریں کہ $(^NameDA) صرف اپنے لیے انسٹال کرنا ہے یا اس کمپیوٹر کے تمام صارفین کے لیے۔ $(^ClickNext)"
  ${LangFileString} MULTIUSER_INNERTEXT_INSTALLMODE_ALLUSERS "اس کمپیوٹر کے ہر صارف کے لیے انسٹال کریں"
  ${LangFileString} MULTIUSER_INNERTEXT_INSTALLMODE_CURRENTUSER "صرف میرے لیے انسٹال کریں"
!endif
