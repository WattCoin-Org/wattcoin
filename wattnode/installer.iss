; WattNode Installer Script for Inno Setup
; Download Inno Setup: https://jrsoftware.org/isdl.php

#define MyAppName "WattNode"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "WattCoin"
#define MyAppURL "https://wattcoin.org"
#define MyAppExeName "WattNode.exe"

[Setup]
AppId={{8E4A5B2C-9F3D-4E6A-B7C8-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Output settings
OutputDir=installer_output
OutputBaseFilename=WattNode-Setup-{#MyAppVersion}
; Visual settings
SetupIconFile=assets\icon.ico
WizardStyle=modern
WizardSizePercent=100
; Compression
Compression=lzma2/ultra64
SolidCompression=yes
; Privileges
PrivilegesRequired=lowest
; Uninstall
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start WattNode when Windows starts"; GroupDescription: "Startup Options:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Custom welcome page text
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
