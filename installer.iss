; Inno Setup script -> dist\BrainrotGoonMachine-Setup.exe
; GitHub Actions passes /DAppVersion=1.2.3 and /DAppURL=... from the tag.
; Local build.bat falls back to the defaults below.

#define AppName "Brainrot Goon Machine"
#define AppExe "BrainrotGoonMachine.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppURL
  #define AppURL "https://github.com/OFGD4/BrainrotGoonMachine"
#endif

[Setup]
AppId={{7B7FCF37-C37F-421A-8558-8B07A339C0AA}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=OFGD4
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
; per-user install (no admin): %LOCALAPPDATA%\Programs\BrainrotGoonMachine
PrivilegesRequired=lowest
DefaultDirName={autopf}\BrainrotGoonMachine
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=dist
OutputBaseFilename=BrainrotGoonMachine-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; in-app updater runs Setup with /SILENT /CLOSEAPPLICATIONS
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; wipe the old app files first so removed libraries don't linger after an update
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\BrainrotGoonMachine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; no "skipifsilent": after a silent in-app update the new version starts by itself
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\BrainrotGoonMachine\tmp"
Type: filesandordirs; Name: "{localappdata}\BrainrotGoonMachine\edge-profile"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent()) then
    if MsgBox('Also delete settings, history, downloaded tools and ear models?' + #13#10 +
              ExpandConstant('{localappdata}\BrainrotGoonMachine') + #13#10#13#10 +
              'Your videos in the goon cave folder are NOT deleted.',
              mbConfirmation, MB_YESNO) = IDYES then
      DelTree(ExpandConstant('{localappdata}\BrainrotGoonMachine'), True, True, True);
end;
