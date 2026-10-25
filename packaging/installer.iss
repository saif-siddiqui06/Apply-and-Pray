; Inno Setup script for the Windows installer. packaging\build.ps1 compiles it when Inno Setup 6 is installed.
; Installs for the current user only (no admin rights needed), adds Start menu / desktop shortcuts, and can start the app at the end.
; User data is NOT in the install folder (it's in %LOCALAPPDATA%\ApplyAndPray), so uninstalling or updating keeps it.

#define AppName "Apply & Pray"
#define AppVersion "2.1.0"
#define AppExe "ApplyAndPray.exe"

[Setup]
AppId={{C3E64F56-35DE-4F09-B0E8-55E511791D18}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Apply & Pray
DefaultDirName={localappdata}\Programs\Apply and Pray
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ApplyAndPray-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\ApplyAndPray\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent
