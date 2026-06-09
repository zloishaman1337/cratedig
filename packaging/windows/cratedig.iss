; Inno Setup script — installs the PyInstaller onedir build of cratedig.
; Build:  iscc /DVersion=0.1.0 packaging\windows\cratedig.iss
; Output: packaging\windows\Output\cratedig-setup-<version>.exe
;
; User data (config.toml, db, downloads, saved) lives in %APPDATA%\cratedig and is
; created on first run — NOT under {app} — so uninstall never wipes the library.

#ifndef Version
  #define Version "0.1.0"
#endif

#define AppName "cratedig"
#define ExeName "cratedig.exe"
; Path is relative to this .iss file.
#define DistDir "..\..\dist\cratedig"

[Setup]
AppId={{A7C1F3E2-9B4D-4C2A-8F1E-CRATEDIG0001}
AppName={#AppName}
AppVersion={#Version}
AppPublisher=cratedig
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#ExeName}
OutputDir=Output
OutputBaseFilename=cratedig-setup-{#Version}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#ExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";     Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
