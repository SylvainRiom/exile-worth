; Inno Setup script of Exile Worth. Built by packaging\build.ps1, which passes
; /DAppVersion from exile_worth/__init__.py.
;
; Per-user install (no administrator rights, no UAC prompt), so an update can
; replace the program on its own. User data lives in %LOCALAPPDATA%\ExileWorth,
; outside {app}: installing, updating and uninstalling never touch it.

#ifndef AppVersion
  #error Pass /DAppVersion=x.y.z (packaging\build.ps1 does)
#endif

[Setup]
; Never change AppId: it is how an update recognises the installed copy.
AppId={{75D656DD-DCCF-4D63-B538-5B47503BCED9}
AppName=Exile Worth
AppVersion={#AppVersion}
AppVerName=Exile Worth {#AppVersion}
AppPublisher=Sylvain Riom
AppPublisherURL=https://github.com/SylvainRiom/exile-worth
AppSupportURL=https://github.com/SylvainRiom/exile-worth/issues
AppUpdatesURL=https://github.com/SylvainRiom/exile-worth/releases
VersionInfoVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\ExileWorth
DisableProgramGroupPage=yes
DisableDirPage=auto
UninstallDisplayIcon={app}\ExileWorth.exe
UninstallDisplayName=Exile Worth
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; A running copy is closed through the Restart Manager before its files are
; replaced; the updater relaunches it itself (see [Run]).
CloseApplications=yes
RestartApplications=no
OutputDir=..\build\installer
OutputBaseFilename=ExileWorth-Setup-{#AppVersion}

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; The bundled libraries change between versions: drop the old ones rather than
; leaving a stale DLL beside the new build.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\build\dist\ExileWorth\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Exile Worth"; Filename: "{app}\ExileWorth.exe"
Name: "{autodesktop}\Exile Worth"; Filename: "{app}\ExileWorth.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ExileWorth.exe"; Description: "{cm:LaunchProgram,Exile Worth}"; Flags: nowait postinstall skipifsilent
; The in-app updater runs the installer with /SILENT /RELAUNCH=1.
Filename: "{app}\ExileWorth.exe"; Flags: nowait; Check: ShouldRelaunch

[Code]
function ShouldRelaunch: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;
