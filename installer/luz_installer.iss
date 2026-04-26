; ============================================================
;  Luz Language Installer
;  Built with Inno Setup 6 — https://jrsoftware.org/isinfo.php
; ============================================================

#ifndef AppVersion
  #define AppVersion "dev"
#endif

#define AppName        "Luz"
#define AppExeName     "luzc.exe"
#define AppPublisher   "Elabsurdo984"
#define AppURL         "https://elabsurdo984.github.io/luzlang/"
#define AppSupportURL  "https://github.com/Elabsurdo984/luzlang/issues"
#define AppUpdatesURL  "https://github.com/Elabsurdo984/luzlang/releases"

; ── [Setup] ──────────────────────────────────────────────────────────────────

[Setup]
AppId={{A3F7C2E1-84B6-4D9A-BB5F-2E3C1D8F04A7}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppSupportURL}
AppUpdatesURL={#AppUpdatesURL}
AppCopyright=Copyright (C) 2024-2026 {#AppPublisher}

; Directories
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Allow the user to change the install dir
DisableDirPage=no

; Output
OutputDir=..\installer_output
OutputBaseFilename=luz-{#AppVersion}-windows-x64
SetupIconFile=..\img\icon.ico

; Visuals
WizardStyle=modern
WizardResizable=yes
WizardSizePercent=120,120

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Privileges — offer both per-user and system-wide
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Environment
ChangesEnvironment=yes
ChangesAssociations=yes

; Uninstaller
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}

; Require Windows 10 or later
MinVersion=10.0

; 64-bit only
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Misc
DisableWelcomePage=no
DisableReadyPage=no
ShowLanguageDialog=auto
AllowCancelDuringInstall=yes
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=yes

; ── [Languages] ──────────────────────────────────────────────────────────────

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

; ── [Messages] ───────────────────────────────────────────────────────────────

[Messages]
; Override a few wizard page titles for a cleaner feel
WelcomeLabel1=Welcome to the Luz {#AppVersion} Installer
WelcomeLabel2=This will install Luz {#AppVersion} on your computer.%n%nLuz is a dynamically-typed, expressive programming language designed for clarity and speed of development.%n%nIt is recommended that you close all other applications before continuing.

; ── [Tasks] ──────────────────────────────────────────────────────────────────

[Tasks]
; PATH — on by default
Name: "addtopath";        Description: "Add Luz to the system &PATH (recommended)"; GroupDescription: "Environment:"; Flags: checkedonce
; .luz file association
Name: "fileassoc";        Description: "Associate .&luz files with the Luz compiler"; GroupDescription: "File associations:"; Flags: checkedonce
; Desktop / Start Menu shortcuts
Name: "desktopicon";      Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startmenuicon";    Description: "Create &Start Menu shortcuts"; GroupDescription: "Shortcuts:"; Flags: checkedonce
; Examples
Name: "installexamples";  Description: "Install example programs to Documents\Luz Examples"; GroupDescription: "Optional components:"; Flags: checkedonce

; ── [Files] ──────────────────────────────────────────────────────────────────

[Files]
; Core executables
Source: "..\dist\luzc.exe";   DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\luz_rt.c";   DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\ray.exe";    DestDir: "{app}"; Flags: ignoreversion

; Bundled TCC compiler (zero external dependencies)
Source: "..\dist\tcc\*"; DestDir: "{app}\tcc"; Flags: ignoreversion recursesubdirs createallsubdirs

; Standard library
Source: "..\libs\*"; DestDir: "{app}\luz_modules"; Flags: ignoreversion recursesubdirs createallsubdirs

; Icon for file association
Source: "..\img\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; Example programs (installed to user's Documents only if task selected)
Source: "..\examples\*"; DestDir: "{userdocs}\Luz Examples"; \
    Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist; \
    Tasks: installexamples

; License shown on the license page
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion isreadme

; ── [Dirs] ───────────────────────────────────────────────────────────────────

[Dirs]
; Ensure the modules directory exists even if libs is empty
Name: "{app}\luz_modules"

; ── [Icons] ──────────────────────────────────────────────────────────────────

[Icons]
; Start Menu
Name: "{group}\Luz Compiler (luzc)";  Filename: "{app}\luzc.exe"; \
    IconFilename: "{app}\icon.ico"; Comment: "Luz native compiler"; \
    Tasks: startmenuicon
Name: "{group}\Luz Documentation";    Filename: "{#AppURL}"; \
    Tasks: startmenuicon
Name: "{group}\Luz Examples";         Filename: "{userdocs}\Luz Examples"; \
    Tasks: startmenuicon installexamples
Name: "{group}\Uninstall Luz";        Filename: "{uninstallexe}"; \
    Tasks: startmenuicon

; Desktop shortcut (optional)
Name: "{autodesktop}\Luz Compiler";    Filename: "{app}\luzc.exe"; \
    IconFilename: "{app}\icon.ico"; Comment: "Luz native compiler"; \
    Tasks: desktopicon

; ── [Registry] ───────────────────────────────────────────────────────────────

[Registry]
; ── PATH ──
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; \
    Check: NeedsAddPath('{app}') and IsAdminInstallMode(); \
    Tasks: addtopath
Root: HKCU; Subkey: "Environment"; \
    ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; \
    Check: NeedsAddPath('{app}') and not IsAdminInstallMode(); \
    Tasks: addtopath

; ── LUZ_HOME ──
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: string; ValueName: "LUZ_HOME"; ValueData: "{app}"; \
    Check: IsAdminInstallMode()
Root: HKCU; Subkey: "Environment"; \
    ValueType: string; ValueName: "LUZ_HOME"; ValueData: "{app}"; \
    Check: not IsAdminInstallMode()

; ── .luz file association ──
; HKCU\Software\Classes is the per-user equivalent of HKCR — Windows merges
; them automatically, so this works for both admin and non-admin installs.
; Using HKA (auto) makes Inno Setup pick HKLM when admin, HKCU when not.

; Register the extension
Root: HKA; Subkey: "Software\Classes\.luz"; ValueType: string; ValueName: ""; \
    ValueData: "LuzScript"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.luz"; ValueType: string; ValueName: "Content Type"; \
    ValueData: "text/plain"; Flags: uninsdeletevalue; Tasks: fileassoc
; ProgID
Root: HKA; Subkey: "Software\Classes\LuzScript"; ValueType: string; ValueName: ""; \
    ValueData: "Luz Script"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\LuzScript\DefaultIcon"; ValueType: string; ValueName: ""; \
    ValueData: "{app}\icon.ico,0"; Tasks: fileassoc
; Open action (compile + run)
Root: HKA; Subkey: "Software\Classes\LuzScript\shell\open\command"; ValueType: string; ValueName: ""; \
    ValueData: """{app}\luzc.exe"" ""%1"" --run"; Tasks: fileassoc
; Edit action (opens with notepad as fallback)
Root: HKA; Subkey: "Software\Classes\LuzScript\shell\edit\command"; ValueType: string; ValueName: ""; \
    ValueData: "notepad.exe ""%1"""; Tasks: fileassoc
; Run action
Root: HKA; Subkey: "Software\Classes\LuzScript\shell\run"; ValueType: string; ValueName: ""; \
    ValueData: "Run with Luz"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\LuzScript\shell\run\command"; ValueType: string; ValueName: ""; \
    ValueData: """{app}\luzc.exe"" ""%1"" --run"; Tasks: fileassoc

; ── [Run] ────────────────────────────────────────────────────────────────────

[Run]
; Open a terminal in the install directory after setup
Filename: "{cmd}"; Parameters: "/k echo Luz {#AppVersion} installed. Run: luzc ^<file.luz^>"; \
    Description: "Open a terminal to try luzc"; \
    Flags: nowait postinstall skipifsilent unchecked

; Open the examples folder if examples were installed
Filename: "{userdocs}\Luz Examples"; Description: "Open Examples folder"; \
    Flags: postinstall shellexec skipifsilent unchecked; Tasks: installexamples

; ── [UninstallRun] ───────────────────────────────────────────────────────────

[UninstallRun]
; Broadcast WM_SETTINGCHANGE so Explorer refreshes PATH without a reboot
Filename: "{cmd}"; Parameters: "/c setx LUZ_HOME """""; \
    Flags: runhidden waituntilterminated; RunOnceId: "RemoveLuzHome"

; ── [UninstallDelete] ────────────────────────────────────────────────────────

[UninstallDelete]
; Remove the modules directory and bundled TCC
Type: filesandordirs; Name: "{app}\luz_modules"
Type: filesandordirs; Name: "{app}\tcc"

; ── [Code] ───────────────────────────────────────────────────────────────────

[Code]

// ── External Windows API declarations ────────────────────────────────────────

// SendMessageTimeout is not built into Inno Setup's Pascal — import it from
// user32.dll directly.  We use the Unicode (W) variant since Inno Setup 6
// compiles in Unicode mode.
function SendMessageTimeoutW(hWnd: HWND; Msg: UINT; wParam: UINT;
  lParam: string; fuFlags: UINT; uTimeout: UINT;
  var lpdwResult: DWORD): DWORD;
  external 'SendMessageTimeoutW@user32.dll stdcall';


// ── Helpers ──────────────────────────────────────────────────────────────────

// NeedsAddPath: returns True if {app} is not already on PATH.
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
  Key:      string;
begin
  if IsAdminInstallMode() then
    Key := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
  else
    Key := 'Environment';

  if not RegQueryStringValue(
    HKEY_LOCAL_MACHINE, Key, 'Path', OrigPath) then
  begin
    if not RegQueryStringValue(
      HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
    begin
      Result := True;
      exit;
    end;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

// BroadcastPathChange: tells running applications (Explorer, terminals) that
// the environment changed so they pick up the new PATH without a full reboot.
procedure BroadcastPathChange();
var
  Dummy: DWORD;
begin
  // $FFFF = HWND_BROADCAST, $001A = WM_SETTINGCHANGE, $0002 = SMTO_ABORTIFHUNG
  SendMessageTimeoutW($FFFF, $001A, 0, 'Environment', $0002, 5000, Dummy);
end;

// ── Install-time version conflict check ──────────────────────────────────────

// GetInstalledVersion: reads the version string written by a previous install.
function GetInstalledVersion(): string;
var
  Installed: string;
begin
  if RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A3F7C2E1-84B6-4D9A-BB5F-2E3C1D8F04A7}_is1',
    'DisplayVersion', Installed) then
    Result := Installed
  else
    Result := '';
end;

// InitializeSetup: called before any wizard page is shown.
function InitializeSetup(): Boolean;
var
  Installed: string;
  Msg:       string;
begin
  Result    := True;
  Installed := GetInstalledVersion();

  if (Installed <> '') and (Installed <> '{#AppVersion}') then
  begin
    Msg := 'Luz ' + Installed + ' is already installed.' + #13#10 +
           'This installer will upgrade it to version {#AppVersion}.' + #13#10#13#10 +
           'Continue?';
    if MsgBox(Msg, mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;

// ── Post-install ─────────────────────────────────────────────────────────────

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then
    BroadcastPathChange();
end;

// ── Post-uninstall ────────────────────────────────────────────────────────────

// RemoveFromPath: strips {app} from PATH in the registry on uninstall.
procedure RemoveFromPath(const AppPath: string);
var
  Key:      string;
  OrigPath: string;
  NewPath:  string;
  P:        Integer;
begin
  if IsAdminInstallMode() then
    Key := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
  else
    Key := 'Environment';

  if not RegQueryStringValue(HKLM, Key, 'Path', OrigPath) then
    if not RegQueryStringValue(HKCU, 'Environment', 'Path', OrigPath) then
      exit;

  NewPath := OrigPath;

  // Remove ';AppPath' or 'AppPath;' patterns
  P := Pos(';' + AppPath, NewPath);
  if P > 0 then
    Delete(NewPath, P, Length(';' + AppPath))
  else
  begin
    P := Pos(AppPath + ';', NewPath);
    if P > 0 then
      Delete(NewPath, P, Length(AppPath + ';'))
    else
    begin
      P := Pos(AppPath, NewPath);
      if P > 0 then
        Delete(NewPath, P, Length(AppPath));
    end;
  end;

  if NewPath <> OrigPath then
  begin
    if IsAdminInstallMode() then
      RegWriteStringValue(HKLM, Key, 'Path', NewPath)
    else
      RegWriteStringValue(HKCU, 'Environment', 'Path', NewPath);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RemoveFromPath(ExpandConstant('{app}'));
    BroadcastPathChange();
  end;
end;
