[Setup]
AppName=Luz
#ifndef AppVersion
  #define AppVersion "dev"
#endif
AppVersion={#AppVersion}
AppPublisher=Elabsurdo984
AppPublisherURL=https://elabsurdo984.github.io/luzlang/
AppSupportURL=https://github.com/Elabsurdo984/luzlang/issues
AppUpdatesURL=https://github.com/Elabsurdo984/luzlang/releases
DefaultDirName={autopf}\Luz
DefaultGroupName=Luz
AllowNoIcons=yes
OutputDir=..\installer_output
OutputBaseFilename=luz-setup
SetupIconFile=..\img\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\luz.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\ray.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\libs\*"; DestDir: "{app}\luz_modules"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Luz REPL"; Filename: "{app}\luz.exe"
Name: "{group}\Uninstall Luz"; Filename: "{uninstallexe}"

[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; \
    Check: NeedsAddPath('{app}')
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: string; ValueName: "LUZ_HOME"; \
    ValueData: "{app}"

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(
    HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;
