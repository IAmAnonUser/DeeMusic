; DeeMusic Windows Installer Script
; Inno Setup Script for creating a professional Windows installer

#define MyAppName "DeeMusic"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "DeeMusic Team"
#define MyAppURL "https://github.com/IAmAnonUser/DeeMusic"
#define MyAppExeName "DeeMusic.exe"
#define MyAppDescription "Modern music streaming and downloading application"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
AppId={{3F5B9C2A-8D4E-4B6F-9A1C-2E8F7D3B5C9A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=
InfoBeforeFile=
InfoAfterFile=
OutputDir=installer_output
OutputBaseFilename=DeeMusic_Setup_v{#MyAppVersion}
SetupIconFile=src\ui\assets\logo.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 0,6.1
Name: "associatefiles"; Description: "Associate with music files (*.mp3, *.flac, *.m4a)"; GroupDescription: "File associations:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "src\ui\assets\logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion; DestName: "README.txt"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo.ico"
Name: "{group}\{cm:ProgramOnTheWeb,{#MyAppName}}"; Filename: "{#MyAppURL}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo.ico"; Tasks: quicklaunchicon

[Registry]
; File associations (only if user selected the task)
Root: HKCU; Subkey: "Software\Classes\.mp3"; ValueType: string; ValueName: ""; ValueData: "DeeMusic.AudioFile"; Flags: uninsdeletevalue; Tasks: associatefiles
Root: HKCU; Subkey: "Software\Classes\.flac"; ValueType: string; ValueName: ""; ValueData: "DeeMusic.AudioFile"; Flags: uninsdeletevalue; Tasks: associatefiles
Root: HKCU; Subkey: "Software\Classes\.m4a"; ValueType: string; ValueName: ""; ValueData: "DeeMusic.AudioFile"; Flags: uninsdeletevalue; Tasks: associatefiles
Root: HKCU; Subkey: "Software\Classes\DeeMusic.AudioFile"; ValueType: string; ValueName: ""; ValueData: "DeeMusic Audio File"; Flags: uninsdeletekey; Tasks: associatefiles
Root: HKCU; Subkey: "Software\Classes\DeeMusic.AudioFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\logo.ico"; Tasks: associatefiles
Root: HKCU; Subkey: "Software\Classes\DeeMusic.AudioFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associatefiles

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\DeeMusic"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%n[name] is a modern music streaming and downloading application for Deezer with an intuitive interface, comprehensive metadata management, and advanced download capabilities.%n%nIt is recommended that you close all other applications before continuing.

[Code]
function GetAppDataPath(Param: String): String;
begin
  Result := ExpandConstant('{userappdata}\DeeMusic');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDataDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    AppDataDir := ExpandConstant('{userappdata}\DeeMusic');
    // Create AppData directory for settings
    if not DirExists(AppDataDir) then
      ForceDirectories(AppDataDir);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataDir: String;
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    AppDataDir := ExpandConstant('{userappdata}\DeeMusic');
    if DirExists(AppDataDir) then
    begin
      if MsgBox('Do you want to remove your DeeMusic settings and data?', mbConfirmation, MB_YESNO) = IDYES then
      begin
        Exec('cmd.exe', '/c rmdir /s /q "' + AppDataDir + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      end;
    end;
  end;
end; 