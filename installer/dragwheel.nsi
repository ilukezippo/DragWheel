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
!define APPVERSION   "1.1.0"
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

!define MUI_WELCOMEPAGE_TITLE "$(WelcomeTitle)"
!define MUI_WELCOMEPAGE_TEXT "$(WelcomeText)"

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
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Arabic"
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

!macro StopDragWheel
  nsExec::Exec 'taskkill /F /T /IM ${EXE}'
  Pop $0
  Sleep 400
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
  SetShellVarContext all

  SetOutPath "$INSTDIR"
  RMDir /r "$INSTDIR\_internal"          ; clean upgrade
  File /r "${DISTDIR}\*.*"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

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
  ; app language follows the installer language (can be changed in Settings)
  StrCmp $LANGUAGE ${LANG_ARABIC} 0 +3
    WriteRegStr HKCU "${SETTINGS_KEY}" "language" "ar"
    Goto +2
    WriteRegStr HKCU "${SETTINGS_KEY}" "language" "en"
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
  SetShellVarContext current           ; Send To is per user
  CreateShortcut "$SENDTO\${APPNAME}.lnk" "$INSTDIR\${EXE}" "--open" "$INSTDIR\${EXE}" 0
  SetShellVarContext all
SectionEnd

Section "$(SecStartupName)" SecStartup
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}" '"$INSTDIR\${EXE}" --tray'
SectionEnd

Section /o "$(SecDesktopName)" SecDesktop
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCore}    "$(SecCoreDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMenu}    "$(SecMenuDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartup} "$(SecStartupDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "$(SecDesktopDesc)"
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

; ---------------------------------------------------------------------------
Function un.onInit
  SetRegView 64
  !insertmacro RequireAdmin
  SetShellVarContext all
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd

Section "Uninstall"
  !insertmacro StopDragWheel

  DeleteRegKey   HKCU "Software\Classes\*\shell\DragWheel"
  DeleteRegKey   HKCU "Software\Classes\Directory\shell\DragWheel"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}"
  DeleteRegKey   HKLM "${UNINST_KEY}"
  DeleteRegKey   HKCU "Software\DragWheel"

  SetShellVarContext all
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  SetShellVarContext current
  Delete "$SENDTO\${APPNAME}.lnk"
  Delete "$DESKTOP\${APPNAME}.lnk"

  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd

; ---------------------------------------------------------------------------
; Strings
LangString WelcomeTitle   ${LANG_ENGLISH} "Welcome to ${APPNAME}"
LangString WelcomeTitle   ${LANG_ARABIC}  "مرحبًا بك في ${APPNAME}"
LangString WelcomeText    ${LANG_ENGLISH} "Drag a file, tap a key, drop it on the wheel.$\r$\n$\r$\nTap Shift to convert, Ctrl for file tools (compress, crop, trim…) or Alt for file actions.$\r$\n$\r$\nEverything runs on your PC — nothing is uploaded.$\r$\n$\r$\n${APPNAME} will be installed for all users in Program Files.$\r$\n$\r$\nClick Next to continue."
LangString WelcomeText    ${LANG_ARABIC}  "اسحب ملفًا، اضغط مفتاحًا، ثم أفلته على العجلة.$\r$\n$\r$\nاضغط Shift للتحويل، وCtrl لأدوات الملفات (ضغط، قص، تقطيع…)، وAlt لإجراءات الملفات.$\r$\n$\r$\nكل شيء يعمل على جهازك — لا يتم رفع أي ملف.$\r$\n$\r$\nسيتم تثبيت ${APPNAME} لجميع المستخدمين في مجلد Program Files.$\r$\n$\r$\nاضغط التالي للمتابعة."
LangString RunNow         ${LANG_ENGLISH} "Start ${APPNAME} now"
LangString RunNow         ${LANG_ARABIC}  "تشغيل ${APPNAME} الآن"
LangString FinishText     ${LANG_ENGLISH} "${APPNAME} lives in the system tray.$\r$\n$\r$\nDrag any file and tap Shift to try it."
LangString FinishText     ${LANG_ARABIC}  "يعمل ${APPNAME} من شريط المهام.$\r$\n$\r$\nاسحب أي ملف واضغط Shift لتجربته."
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
