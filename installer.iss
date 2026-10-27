; =====================================================================
; OmniStream Pro v2.6.0 — Inno Setup Script
; Pure Native Windows Installer (No PyInstaller, No Python, No _MEI)
; =====================================================================

#define MyAppName "OmniStream Pro"
#define MyAppVersion "2.6.0"
#define MyAppPublisher "XMON4U"
#define MyAppURL "https://github.com/Xmon4u/OmniStream-Pro-v2"
#define MyAppExeName "OmniStream_Pro.exe"

[Setup]
AppId={{9B7E31D4-8F51-4CE7-9F19-5F11F1D8A91B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=release_output
OutputBaseFilename=OmniStream_Pro_Setup
SetupIconFile=C++\app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern dark hidebevels
WizardSmallImageFile=C++\assets\images\installer_logo.png
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Main C++ Executable and DLLs
Source: "C++\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "C++\Qt6Core.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "C++\Qt6Gui.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "C++\Qt6Widgets.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "C++\Qt6Network.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "C++\Qt6Svg.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "C++\D3Dcompiler_47.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "C++\opengl32sw.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "C++\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "C++\README.md"; DestDir: "{app}"; Flags: ignoreversion

; Binaries (ffmpeg, N_m3u8DL-RE)
Source: "C++\bin\*"; DestDir: "{app}\bin"; Flags: ignoreversion recursesubdirs createallsubdirs

; Qt Runtime Plugins and Assets
Source: "C++\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C++\platforms\*"; DestDir: "{app}\platforms"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C++\styles\*"; DestDir: "{app}\styles"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C++\iconengines\*"; DestDir: "{app}\iconengines"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C++\imageformats\*"; DestDir: "{app}\imageformats"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C++\networkinformation\*"; DestDir: "{app}\networkinformation"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C++\tls\*"; DestDir: "{app}\tls"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C++\translations\*"; DestDir: "{app}\translations"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C++\generic\*"; DestDir: "{app}\generic"; Flags: ignoreversion recursesubdirs createallsubdirs

; Chrome / Edge Extension Files
Source: "extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "extension\*"; DestDir: "{userappdata}\OmniStream Pro\extension"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{autoprograms}\{#MyAppName}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\app_icon.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// After install, create uninstall.exe alias for unins000.exe
procedure CurStepChanged(CurStep: TSetupStep);
var
  UninsPath: String;
  AliasPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    UninsPath := ExpandConstant('{uninstallexe}');
    AliasPath := ExpandConstant('{app}\uninstall.exe');
    if FileExists(UninsPath) and not FileExists(AliasPath) then
    begin
      CopyFile(UninsPath, AliasPath, False);
    end;
  end;
end;
