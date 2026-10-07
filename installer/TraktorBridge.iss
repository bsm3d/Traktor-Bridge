; Benoit Saint-Moulin
; Traktor Bridge : Inno Setup script, per-user install of the portable build
; Build: ISCC.exe installer\TraktorBridge.iss   (after python build.py)

#define AppName "Traktor Bridge"
#ifndef AppVersion
  #define AppVersion "3.5.1"
#endif
; the file version needs four numeric parts, so it is not derived from AppVersion
#ifndef AppFileVersion
  #define AppFileVersion "3.5.1.0"
#endif
#define AppExe "TraktorBridge.exe"

[Setup]
AppId={{6B0E5C2A-3F7D-4C1B-9A58-2E41D7B3A9C4}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Benoit Saint-Moulin
AppPublisherURL=https://www.traktorbridge.com
AppSupportURL=https://www.traktorbridge.com
AppUpdatesURL=https://www.traktorbridge.com
VersionInfoVersion={#AppFileVersion}
; Settings and log live next to the exe, so the program goes in a folder the user can write to
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=notice.txt
SetupIconFile=..\traktor_bridge\ui\res\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename=TraktorBridge-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; a file left by an older version would be reported as unexpected by the startup check,
; so the program folder is emptied first. Settings and log sit next to the exe, not in runtime
[InstallDelete]
Type: filesandordirs; Name: "{app}\runtime"

[Files]
Source: "..\dist\TraktorBridge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\traktor_bridge.log"
Type: files; Name: "{app}\traktor_bridge.json"