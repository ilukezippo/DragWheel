; DragWheel installer (NSIS 3, Modern UI 2)
; Installs for all users into C:\Program Files\DragWheel. Installer and uninstaller run as administrator.
; Build:  makensis installer\dragwheel.nsi     (expects ..\dist\DragWheel\ from PyInstaller)

Unicode true
; 64-bit installer when this NSIS has 64-bit stubs (Linux/MSYS builds do); otherwise a 32-bit
; installer, which still installs the 64-bit app into C:\Program Files (see SetRegView below).
!if /FileExists "${NSISDIR}/Stubs/lzma_solid-amd64-unicode"
  Target amd64-unicode
!endif
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!define APPNAME      "DragWheel"
!define APPVERSION   "1.2.1"
!define PUBLISHER    "ilukezippo"
!define EXE          "DragWheel.exe"
!define UNINST_KEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
!define SETTINGS_KEY "Software\DragWheel\DragWheel"
!ifndef DISTDIR
  !define DISTDIR "..\dist\DragWheel"
!endif

Name "${APPNAME}"
OutFile "..\dist\DragWheel-Setup-${APPVERSION}.exe"
InstallDir "$PROGRAMFILES64\${APPNAME}"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
BrandingText "${APPNAME} ${APPVERSION}"

VIProductVersion "${APPVERSION}.0"
VIAddVersionKey "ProductName"     "${APPNAME}"
VIAddVersionKey "FileDescription" "${APPNAME} Setup"
VIAddVersionKey "FileVersion"     "${APPVERSION}"
VIAddVersionKey "ProductVersion"  "${APPVERSION}"
VIAddVersionKey "CompanyName"     "${PUBLISHER}"
VIAddVersionKey "LegalCopyright"  "MIT License"

!include "MUI2.nsh"
!include "FileFunc.nsh"

!define MUI_ICON   "..\assets\dragwheel.ico"
!define MUI_UNICON "..\assets\dragwheel.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP   "wizard.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "wizard.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "header.bmp"
!define MUI_ABORTWARNING
!define MUI_COMPONENTSPAGE_SMALLDESC
!define MUI_LANGDLL_ALLLANGUAGES
!define MUI_LANGDLL_REGISTRY_ROOT "HKCU"
!define MUI_LANGDLL_REGISTRY_KEY "${SETTINGS_KEY}"
!define MUI_LANGDLL_REGISTRY_VALUENAME "InstallerLanguage"
!define MUI_CUSTOMFUNCTION_GUIINIT SetupGuiInit

Var OldVersion   ; version already installed ("" on a fresh install)
Var WelcomeHead
Var WelcomeBody
!define MUI_WELCOMEPAGE_TITLE "$WelcomeHead"
!define MUI_WELCOMEPAGE_TEXT "$WelcomeBody"

!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchAsUser
!define MUI_FINISHPAGE_RUN_TEXT "$(RunNow)"
!define MUI_FINISHPAGE_TEXT "$(FinishText)"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_COMPONENTS
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Arabic"
!insertmacro MUI_LANGUAGE "French"
!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "German"
!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "PortugueseBR"
!insertmacro MUI_LANGUAGE "Turkish"
!insertmacro MUI_LANGUAGE "Russian"
!insertmacro MUI_LANGUAGE "Farsi"
!insertmacro MUI_LANGUAGEEX "lang" "Urdu"        ; NSIS has no Urdu: our own files in installer\lang
!insertmacro MUI_LANGUAGE "Hindi"
!insertmacro MUI_LANGUAGE "Japanese"
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_RESERVEFILE_LANGDLL

; ---------------------------------------------------------------------------
!include "LogicLib.nsh"
!include "x64.nsh"

; The installer runs elevated. Starting the app from it would make the app elevated too, and
; Windows blocks drag-and-drop from Explorer into elevated windows — so launch it through
; Explorer, which starts it as the normal signed-in user.
Function LaunchAsUser
  Exec '"$WINDIR\explorer.exe" "$INSTDIR\${EXE}"'
FunctionEnd

!macro RequireAdmin
  UserInfo::GetAccountType
  Pop $0
  ${If} $0 != "admin"
    MessageBox MB_OK|MB_ICONSTOP "$(NeedAdmin)"
    SetErrorLevel 740
    Quit
  ${EndIf}
!macroend

; Close DragWheel. No /T here: when the app's built-in updater started this installer, the installer
; is DragWheel's child, and /T (kill the whole process tree) would kill the installer too.
!macro StopDragWheel
  ; Ask the running DragWheel to get ready first: it warns about unfinished jobs (the user can say
  ; "not now"), saves the open floats so they reopen after the update, and closes cleanly.
  ${If} ${FileExists} "$INSTDIR\${EXE}"
    ExecWait '"$INSTDIR\${EXE}" --prepare-update' $0
    ${If} $0 == 1
      MessageBox MB_OK|MB_ICONINFORMATION "$(UpdateNotNow)"
      Quit
    ${EndIf}
  ${EndIf}
  nsExec::Exec 'taskkill /F /IM ${EXE}'
  Pop $0
  Sleep 800
!macroend

Section "!$(SecCoreName)" SecCore
  SectionIn RO
  !insertmacro StopDragWheel

  ; remove an older per-user copy (it lived in %LOCALAPPDATA%\Programs\DragWheel)
  SetShellVarContext current
  ${If} ${FileExists} "$LOCALAPPDATA\Programs\${APPNAME}\Uninstall.exe"
    ExecWait '"$LOCALAPPDATA\Programs\${APPNAME}\Uninstall.exe" /S _?=$LOCALAPPDATA\Programs\${APPNAME}'
    RMDir /r "$LOCALAPPDATA\Programs\${APPNAME}"
    DeleteRegKey HKCU "${UNINST_KEY}"
  ${EndIf}
  ; remove DragWheel's early test build, which was called "Satsuma"
  nsExec::Exec 'taskkill /F /IM Satsuma.exe'
  Pop $0
  ${If} ${FileExists} "$LOCALAPPDATA\Programs\Satsuma\Uninstall.exe"
    ExecWait '"$LOCALAPPDATA\Programs\Satsuma\Uninstall.exe" /S _?=$LOCALAPPDATA\Programs\Satsuma'
  ${EndIf}
  RMDir /r "$LOCALAPPDATA\Programs\Satsuma"
  DeleteRegKey HKCU "Software\Classes\*\shell\Satsuma"
  DeleteRegKey HKCU "Software\Classes\Directory\shell\Satsuma"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Satsuma"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Satsuma"
  Delete "$SENDTO\Satsuma.lnk"
  SetShellVarContext all

  ; Send to phone: let phones on the home Wi-Fi reach DragWheel's sharing page (it only listens while
  ; the sharing window is open, behind a random link)
  nsExec::Exec 'netsh advfirewall firewall delete rule name=all program="$INSTDIR\${EXE}"'
  Pop $0
  nsExec::Exec 'netsh advfirewall firewall delete rule name="DragWheel (Send to phone)"'
  Pop $0
  nsExec::Exec 'netsh advfirewall firewall add rule name="DragWheel (Send to phone)" dir=in action=allow protocol=TCP program="$INSTDIR\${EXE}" profile=private,public enable=yes'
  Pop $0

  ; updating: remove the old version first (settings in the registry are kept)
  ${If} $OldVersion != ""
    DetailPrint "$(RemovingOld)"
    RMDir /r "$INSTDIR\_internal"
    Delete "$INSTDIR\${EXE}"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir /r "$SMPROGRAMS\${APPNAME}"
  ${EndIf}

  SetOutPath "$INSTDIR"
  RMDir /r "$INSTDIR\_internal"
  File /r "${DISTDIR}\*.*"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; "dragwheel" command for scripts (this folder is on every user's PATH in Windows 10 and 11)
  CreateDirectory "$LOCALAPPDATA\Microsoft\WindowsApps"
  FileOpen $0 "$LOCALAPPDATA\Microsoft\WindowsApps\dragwheel.cmd" w
  FileWrite $0 '@echo off$\r$\nrem DragWheel from the command line: dragwheel help$\r$\nstart "" /wait "$INSTDIR\${EXE}" --cli %*$\r$\nexit /b %errorlevel%$\r$\n'
  FileClose $0

  ; Start Menu
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk" "$INSTDIR\Uninstall.exe"

  ; Apps & features entry
  WriteRegStr   HKLM "${UNINST_KEY}" "DisplayName"     "${APPNAME}"
  WriteRegStr   HKLM "${UNINST_KEY}" "DisplayVersion"  "${APPVERSION}"
  WriteRegStr   HKLM "${UNINST_KEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr   HKLM "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\${EXE},0"
  WriteRegStr   HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKLM "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegStr   HKLM "${UNINST_KEY}" "URLInfoAbout"    "https://github.com/ilukezippo"
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" "$0"

  ; tell the app the installer already decided about the Explorer menu
  WriteRegStr HKCU "${SETTINGS_KEY}" "installer" "1"
  ; the app speaks the language you picked in Setup (a silent update keeps the one chosen in Settings)
  ${IfNot} ${Silent}
    ${If} $LANGUAGE == ${LANG_ARABIC}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "ar"
    ${ElseIf} $LANGUAGE == ${LANG_FRENCH}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "fr"
    ${ElseIf} $LANGUAGE == ${LANG_SPANISH}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "es"
    ${ElseIf} $LANGUAGE == ${LANG_GERMAN}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "de"
    ${ElseIf} $LANGUAGE == ${LANG_ITALIAN}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "it"
    ${ElseIf} $LANGUAGE == ${LANG_PORTUGUESEBR}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "pt"
    ${ElseIf} $LANGUAGE == ${LANG_TURKISH}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "tr"
    ${ElseIf} $LANGUAGE == ${LANG_RUSSIAN}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "ru"
    ${ElseIf} $LANGUAGE == ${LANG_FARSI}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "fa"
    ${ElseIf} $LANGUAGE == ${LANG_URDU}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "ur"
    ${ElseIf} $LANGUAGE == ${LANG_HINDI}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "hi"
    ${ElseIf} $LANGUAGE == ${LANG_JAPANESE}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "ja"
    ${ElseIf} $LANGUAGE == ${LANG_SIMPCHINESE}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "zh"
    ${Else}
      WriteRegStr HKCU "${SETTINGS_KEY}" "language" "en"
    ${EndIf}
  ${EndIf}
SectionEnd

Section "$(SecMenuName)" SecMenu
  WriteRegStr HKCU "Software\Classes\*\shell\DragWheel" "MUIVerb" "DragWheel"
  WriteRegStr HKCU "Software\Classes\*\shell\DragWheel" "Icon" "$INSTDIR\${EXE},0"
  WriteRegStr HKCU "Software\Classes\*\shell\DragWheel" "MultiSelectModel" "Player"
  WriteRegStr HKCU "Software\Classes\*\shell\DragWheel\command" "" '"$INSTDIR\${EXE}" --open "%1"'
  WriteRegStr HKCU "Software\Classes\Directory\shell\DragWheel" "MUIVerb" "DragWheel"
  WriteRegStr HKCU "Software\Classes\Directory\shell\DragWheel" "Icon" "$INSTDIR\${EXE},0"
  WriteRegStr HKCU "Software\Classes\Directory\shell\DragWheel" "MultiSelectModel" "Player"
  WriteRegStr HKCU "Software\Classes\Directory\shell\DragWheel\command" "" '"$INSTDIR\${EXE}" --open "%1"'
  ; desktop / empty folder space: DragWheel > Save clipboard image here
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel" "MUIVerb" "DragWheel"
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel" "Icon" "$INSTDIR\${EXE},0"
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel" "SubCommands" ""
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel\shell\paste" "MUIVerb" "$(PasteHere)"
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel\shell\paste" "Icon" "imageres.dll,-5302"
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel\shell\paste\command" "" '"$INSTDIR\${EXE}" --paste-here "%V"'
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel\shell\zlink" "MUIVerb" "$(PlayLink)"
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel\shell\zlink" "Icon" "imageres.dll,-1004"
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel\shell\zlink\command" "" '"$INSTDIR\${EXE}" --play-link'
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel\shell\zzfloat" "MUIVerb" "$(OpenFloat)"
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel\shell\zzfloat" "Icon" "$INSTDIR\${EXE},0"
  WriteRegStr HKCU "Software\Classes\Directory\Background\shell\DragWheel\shell\zzfloat\command" "" '"$INSTDIR\${EXE}" --open-float'
  SetShellVarContext current           ; Send To is per user
  Delete "$SENDTO\${APPNAME}.lnk"
  Delete "$SENDTO\Send to Phone using ${APPNAME}.lnk"
  CreateShortcut "$SENDTO\Send to Phone using ${APPNAME}.lnk" "$INSTDIR\${EXE}" "--send-phone" "$INSTDIR\${EXE}" 0
  SetShellVarContext all
SectionEnd

Section "$(SecStartupName)" SecStartup
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}" '"$INSTDIR\${EXE}" --tray'
SectionEnd

; Optional downloads: DragWheel fetches the ticked ones by itself right after it starts (with a progress card),
; so the installer stays small and a failed download can simply be retried from the app.
SectionGroup "$(SecDlGroup)" SecDl
  Section /o "$(SecDlBg)" SecDlBg
    WriteRegStr HKCU "${SETTINGS_KEY}\predownload" "isnet" "1"
  SectionEnd
  Section /o "$(SecDlSpeech)" SecDlSpeech
    WriteRegStr HKCU "${SETTINGS_KEY}\predownload" "whisper-small" "1"
  SectionEnd
  Section /o "$(SecDlLinks)" SecDlLinks
    WriteRegStr HKCU "${SETTINGS_KEY}\predownload" "yt-dlp" "1"
  SectionEnd
SectionGroupEnd

Section /o "$(SecDesktopName)" SecDesktop
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCore}    "$(SecCoreDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMenu}    "$(SecMenuDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartup} "$(SecStartupDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "$(SecDesktopDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDl}      "$(SecDlDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDlBg}    "$(SecDlBgDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDlSpeech} "$(SecDlSpeechDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDlLinks} "$(SecDlLinksDesc)"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "$(Need64)"
    Quit
  ${EndIf}
  SetRegView 64
  !insertmacro RequireAdmin
  SetShellVarContext all
  !insertmacro MUI_LANGDLL_DISPLAY
  ; refuse to run twice at the same time
  System::Call 'kernel32::CreateMutex(p 0, i 0, t "DragWheelSetupMutex") p .r1 ?e'
  Pop $R0
  StrCmp $R0 0 +3
    MessageBox MB_OK|MB_ICONEXCLAMATION "$(AlreadyRunning)"
    Abort
FunctionEnd

; Runs after the language is chosen and loaded (texts in .onInit are always in the first language),
; so the "already installed" question and the welcome page are in the language you picked.
Function SetupGuiInit
  ; already installed? -> this is an update
  ReadRegStr $OldVersion HKLM "${UNINST_KEY}" "DisplayVersion"
  ${If} $OldVersion == ""
  ${AndIf} ${FileExists} "$INSTDIR\${EXE}"
    StrCpy $OldVersion "?"
  ${EndIf}
  ${If} $OldVersion == ""
    StrCpy $WelcomeHead "$(WelcomeTitle)"
    StrCpy $WelcomeBody "$(WelcomeText)"
  ${Else}
    StrCpy $WelcomeHead "$(UpdateTitle)"
    StrCpy $WelcomeBody "$(UpdateText)"
  ${EndIf}

  ; the same version is already installed: reinstall it, or uninstall it?
  ${If} $OldVersion == "${APPVERSION}"
  ${AndIfNot} ${Silent}
    MessageBox MB_YESNOCANCEL|MB_ICONQUESTION "$(SameVersion)" IDYES same_reinstall IDNO same_uninstall
    Quit
    same_uninstall:
      ${If} ${FileExists} "$INSTDIR\Uninstall.exe"
        Exec '"$INSTDIR\Uninstall.exe"'
      ${EndIf}
      Quit
    same_reinstall:
      StrCpy $WelcomeHead "$(ReinstallTitle)"
      StrCpy $WelcomeBody "$(ReinstallText)"
  ${EndIf}
FunctionEnd

; ---------------------------------------------------------------------------
Function un.onInit
  SetRegView 64
  !insertmacro RequireAdmin
  SetShellVarContext all
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd

Section "!un.$(UnSecApp)" UnSecApp
  SectionIn RO
  SetShellVarContext current
  Delete "$LOCALAPPDATA\Microsoft\WindowsApps\dragwheel.cmd"
  SetShellVarContext all
  !insertmacro StopDragWheel
  nsExec::Exec 'netsh advfirewall firewall delete rule name="DragWheel (Send to phone)"'
  Pop $0

  DeleteRegKey   HKCU "Software\Classes\*\shell\DragWheel"
  DeleteRegKey   HKCU "Software\Classes\Directory\shell\DragWheel"
  DeleteRegKey   HKCU "Software\Classes\Directory\Background\shell\DragWheel"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}"
  DeleteRegKey   HKLM "${UNINST_KEY}"

  SetShellVarContext all
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  SetShellVarContext current
  Delete "$SENDTO\${APPNAME}.lnk"
  Delete "$SENDTO\Send to Phone using ${APPNAME}.lnk"
  Delete "$DESKTOP\${APPNAME}.lnk"

  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd

; unticked = kept, so reinstalling later brings everything back as it was
Section /o "un.$(UnSecSettings)" UnSecSettings
  DeleteRegKey HKCU "Software\DragWheel"
  SetShellVarContext current
  RMDir /r "$LOCALAPPDATA\DragWheel\crash"
  Delete "$LOCALAPPDATA\DragWheel\*.*"
  RMDir "$LOCALAPPDATA\DragWheel"
  SetShellVarContext all
SectionEnd

Section /o "un.$(UnSecDownloads)" UnSecDownloads
  SetShellVarContext current
  RMDir /r "$LOCALAPPDATA\DragWheel\models"
  RMDir "$LOCALAPPDATA\DragWheel"
  SetShellVarContext all
SectionEnd

!insertmacro MUI_UNFUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${UnSecApp}       "$(UnSecAppDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${UnSecSettings}  "$(UnSecSettingsDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${UnSecDownloads} "$(UnSecDownloadsDesc)"
!insertmacro MUI_UNFUNCTION_DESCRIPTION_END

; ---------------------------------------------------------------------------
; Strings
LangString WelcomeTitle   ${LANG_ENGLISH} "Welcome to ${APPNAME}"
LangString WelcomeTitle   ${LANG_ARABIC}  "مرحبًا بك في ${APPNAME}"
LangString WelcomeText    ${LANG_ENGLISH} "Drag a file, tap a key, drop it on the wheel.$\r$\n$\r$\nTap Shift to convert, Ctrl for file tools (compress, crop, trim…) or Alt for file actions.$\r$\n$\r$\nEverything runs on your PC — nothing is uploaded.$\r$\n$\r$\n${APPNAME} will be installed for all users in Program Files.$\r$\n$\r$\nClick Next to continue."
LangString WelcomeText    ${LANG_ARABIC}  "اسحب ملفًا، اضغط مفتاحًا، ثم أفلته على العجلة.$\r$\n$\r$\nاضغط Shift للتحويل، وCtrl لأدوات الملفات (ضغط، قص، تقطيع…)، وAlt لإجراءات الملفات.$\r$\n$\r$\nكل شيء يعمل على جهازك — لا يتم رفع أي ملف.$\r$\n$\r$\nسيتم تثبيت ${APPNAME} لجميع المستخدمين في مجلد Program Files.$\r$\n$\r$\nاضغط التالي للمتابعة."
LangString PasteHere      ${LANG_ENGLISH} "Save clipboard image here"
LangString PasteHere      ${LANG_ARABIC}  "حفظ صورة الحافظة هنا"
LangString OpenFloat      ${LANG_ENGLISH} "Open Float"
LangString OpenFloat      ${LANG_ARABIC}  "فتح نافذة عائمة"
LangString PlayLink       ${LANG_ENGLISH} "Paste link to Float"
LangString PlayLink       ${LANG_ARABIC}  "لصق رابط في النافذة العائمة"
LangString UpdateNotNow   ${LANG_ENGLISH} "The update was cancelled so your running jobs can finish. Run setup again when they're done."
LangString UpdateNotNow   ${LANG_ARABIC}  "أُلغي التحديث حتى تنتهي المهام الجارية. شغّل الإعداد مرة أخرى عند انتهائها."
LangString UpdateTitle    ${LANG_ENGLISH} "Update ${APPNAME}"
LangString UpdateTitle    ${LANG_ARABIC}  "تحديث ${APPNAME}"
LangString UpdateText     ${LANG_ENGLISH} "${APPNAME} $OldVersion is installed on this PC.$\r$\n$\r$\nSetup will close it, remove the old version and install ${APPNAME} ${APPVERSION}. Your settings are kept.$\r$\n$\r$\nClick Next to continue."
LangString UpdateText     ${LANG_ARABIC}  "الإصدار $OldVersion من ${APPNAME} مثبّت على هذا الجهاز.$\r$\n$\r$\nسيغلقه برنامج الإعداد ويزيل الإصدار القديم ثم يثبّت ${APPNAME} ${APPVERSION}. ستبقى إعداداتك كما هي.$\r$\n$\r$\nاضغط التالي للمتابعة."
LangString SameVersion    ${LANG_ENGLISH} "${APPNAME} ${APPVERSION} is already installed on this PC.$\r$\n$\r$\nYes — reinstall it (your settings are kept)$\r$\nNo — uninstall it$\r$\nCancel — close Setup"
LangString SameVersion    ${LANG_ARABIC}  "الإصدار ${APPVERSION} من ${APPNAME} مثبّت على هذا الجهاز بالفعل.$\r$\n$\r$\nنعم — إعادة تثبيته (ستبقى إعداداتك)$\r$\nلا — إلغاء تثبيته$\r$\nإلغاء الأمر — إغلاق برنامج الإعداد"
LangString ReinstallTitle ${LANG_ENGLISH} "Reinstall ${APPNAME} ${APPVERSION}"
LangString ReinstallTitle ${LANG_ARABIC}  "إعادة تثبيت ${APPNAME} ${APPVERSION}"
LangString ReinstallText  ${LANG_ENGLISH} "Setup will close ${APPNAME} and install ${APPVERSION} again. Your settings are kept.$\r$\n$\r$\nClick Next to continue."
LangString ReinstallText  ${LANG_ARABIC}  "سيغلق برنامج الإعداد ${APPNAME} ويثبّت الإصدار ${APPVERSION} من جديد. ستبقى إعداداتك كما هي.$\r$\n$\r$\nاضغط التالي للمتابعة."
LangString RemovingOld    ${LANG_ENGLISH} "Removing ${APPNAME} $OldVersion…"
LangString RemovingOld    ${LANG_ARABIC}  "جارٍ إزالة ${APPNAME} $OldVersion…"
LangString RunNow         ${LANG_ENGLISH} "Start ${APPNAME} now"
LangString RunNow         ${LANG_ARABIC}  "تشغيل ${APPNAME} الآن"
LangString FinishText     ${LANG_ENGLISH} "${APPNAME} lives in the system tray.$\r$\n$\r$\nDrag any file and tap Shift to try it."
LangString FinishText     ${LANG_ARABIC}  "يعمل ${APPNAME} من شريط المهام.$\r$\n$\r$\nاسحب أي ملف واضغط Shift لتجربته."
LangString UnSecApp       ${LANG_ENGLISH} "${APPNAME} (the app, its menus and shortcuts)"
LangString UnSecApp       ${LANG_ARABIC}  "${APPNAME} (التطبيق وقوائمه واختصاراته)"
LangString UnSecSettings  ${LANG_ENGLISH} "Also remove my settings"
LangString UnSecSettings  ${LANG_ARABIC}  "إزالة إعداداتي أيضًا"
LangString UnSecDownloads ${LANG_ENGLISH} "Also remove downloaded AI models and tools"
LangString UnSecDownloads ${LANG_ARABIC}  "إزالة نماذج الذكاء الاصطناعي والأدوات المنزّلة أيضًا"
LangString UnSecAppDesc   ${LANG_ENGLISH} "Removes ${APPNAME} from this PC."
LangString UnSecAppDesc   ${LANG_ARABIC}  "يزيل ${APPNAME} من هذا الجهاز."
LangString UnSecSettingsDesc ${LANG_ENGLISH} "Your settings, presets, chains, saved links, watch folders and the log. Leave it unticked to keep them for when you install ${APPNAME} again."
LangString UnSecSettingsDesc ${LANG_ARABIC}  "إعداداتك والإعدادات المسبقة والسلاسل والروابط المحفوظة ومجلدات المراقبة والسجل. اتركه دون تحديد للاحتفاظ بها عند تثبيت ${APPNAME} مرة أخرى."
LangString UnSecDownloadsDesc ${LANG_ENGLISH} "The AI models and yt-dlp downloaded after installing (they can be several hundred MB)."
LangString UnSecDownloadsDesc ${LANG_ARABIC}  "نماذج الذكاء الاصطناعي وأداة yt-dlp التي نُزّلت بعد التثبيت (قد تبلغ عدة مئات من الميغابايت)."
LangString SecDlGroup     ${LANG_ENGLISH} "Optional downloads"
LangString SecDlGroup     ${LANG_ARABIC}  "تنزيلات اختيارية"
LangString SecDlBg        ${LANG_ENGLISH} "Remove background — AI model (178 MB)"
LangString SecDlBg        ${LANG_ARABIC}  "إزالة الخلفية — نموذج ذكاء اصطناعي (178 ميغابايت)"
LangString SecDlSpeech    ${LANG_ENGLISH} "Speech to text — AI model (190 MB)"
LangString SecDlSpeech    ${LANG_ARABIC}  "تحويل الكلام إلى نص — نموذج ذكاء اصطناعي (190 ميغابايت)"
LangString SecDlLinks     ${LANG_ENGLISH} "Play YouTube and other links — yt-dlp (18 MB)"
LangString SecDlLinks     ${LANG_ARABIC}  "تشغيل روابط يوتيوب وغيرها — yt-dlp (18 ميغابايت)"
LangString SecDlDesc      ${LANG_ENGLISH} "Parts that are downloaded once instead of being inside the installer. ${APPNAME} downloads the ticked ones right after it starts. Anything you skip is offered the first time you use it."
LangString SecDlDesc      ${LANG_ARABIC}  "أجزاء تُنزَّل مرة واحدة بدلًا من وجودها داخل برنامج التثبيت. يُنزّل ${APPNAME} المحدَّد منها فور تشغيله، وما تتركه يُعرض عليك عند أول استخدام."
LangString SecDlBgDesc    ${LANG_ENGLISH} "Removes the background of photos (Tools → Remove background, and in Crop & Resize). Runs offline."
LangString SecDlBgDesc    ${LANG_ARABIC}  "يزيل خلفية الصور (الأدوات ← إزالة الخلفية، وفي القص وتغيير الحجم). يعمل دون إنترنت."
LangString SecDlSpeechDesc ${LANG_ENGLISH} "Turns speech in videos and recordings into subtitles and text, Arabic included (Tools → Transcribe). Runs offline."
LangString SecDlSpeechDesc ${LANG_ARABIC}  "يحوّل الكلام في الفيديو والتسجيلات إلى ترجمة ونص، بما فيها العربية (الأدوات ← تفريغ). يعمل دون إنترنت."
LangString SecDlLinksDesc ${LANG_ENGLISH} "Lets Float play links from YouTube and about 1,800 other sites (Paste link to Float)."
LangString SecDlLinksDesc ${LANG_ARABIC}  "يتيح للنافذة العائمة تشغيل روابط يوتيوب ونحو 1800 موقع آخر (تشغيل الرابط المنسوخ)."
LangString SecCoreName    ${LANG_ENGLISH} "${APPNAME} (required)"
LangString SecCoreName    ${LANG_ARABIC}  "${APPNAME} (مطلوب)"
LangString SecMenuName    ${LANG_ENGLISH} "Explorer right-click menu and Send To"
LangString SecMenuName    ${LANG_ARABIC}  "قائمة الزر الأيمن و«إرسال إلى»"
LangString SecStartupName ${LANG_ENGLISH} "Start with Windows"
LangString SecStartupName ${LANG_ARABIC}  "التشغيل مع Windows"
LangString SecDesktopName ${LANG_ENGLISH} "Desktop shortcut"
LangString SecDesktopName ${LANG_ARABIC}  "اختصار على سطح المكتب"
LangString SecCoreDesc    ${LANG_ENGLISH} "The ${APPNAME} app and Start Menu shortcut."
LangString SecCoreDesc    ${LANG_ARABIC}  "تطبيق ${APPNAME} واختصار قائمة ابدأ."
LangString SecMenuDesc    ${LANG_ENGLISH} "Adds ${APPNAME} when you right-click files or folders, and a Send To entry."
LangString SecMenuDesc    ${LANG_ARABIC}  "يضيف ${APPNAME} عند النقر بزر الفأرة الأيمن على الملفات أو المجلدات، وإلى «إرسال إلى»."
LangString SecStartupDesc ${LANG_ENGLISH} "Starts ${APPNAME} in the tray when you sign in, so drag-and-tap always works."
LangString SecStartupDesc ${LANG_ARABIC}  "يشغّل ${APPNAME} في شريط المهام عند تسجيل الدخول ليعمل السحب والضغط دائمًا."
LangString SecDesktopDesc ${LANG_ENGLISH} "Puts a ${APPNAME} shortcut on the desktop."
LangString SecDesktopDesc ${LANG_ARABIC}  "يضع اختصارًا لـ ${APPNAME} على سطح المكتب."
LangString AlreadyRunning ${LANG_ENGLISH} "The ${APPNAME} installer is already running."
LangString AlreadyRunning ${LANG_ARABIC}  "مثبّت ${APPNAME} قيد التشغيل بالفعل."
LangString NeedAdmin      ${LANG_ENGLISH} "${APPNAME} Setup needs administrator rights. Right-click it and choose 'Run as administrator'."
LangString NeedAdmin      ${LANG_ARABIC}  "يحتاج مثبّت ${APPNAME} إلى صلاحيات المسؤول. انقر عليه بزر الفأرة الأيمن واختر «تشغيل كمسؤول»."
LangString Need64         ${LANG_ENGLISH} "${APPNAME} needs 64-bit Windows 10 or 11."
LangString Need64         ${LANG_ARABIC}  "يتطلب ${APPNAME} نظام Windows 10 أو 11 بإصدار 64 بت."

!include "lang\strings.nsh"
