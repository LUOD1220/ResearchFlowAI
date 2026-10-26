[Setup]
AppId={{E7379C9C-846A-49AB-A5AA-4B9A221A271F}
AppName=ResearchFlow AI
AppVersion=0.3.2-beta
AppPublisher=ResearchFlow AI Beta
DefaultDirName={localappdata}\Programs\ResearchFlowAI
DefaultGroupName=ResearchFlow AI
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19045
OutputDir=..\release-windows
OutputBaseFilename=ResearchFlowAI-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ResearchFlowAI.exe
CloseApplications=yes
SetupLogging=no
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\ResearchFlowAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "third-party-source\*"; DestDir: "{app}\third-party-source"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ResearchFlow AI"; Filename: "{app}\ResearchFlowAI.exe"
Name: "{group}\Uninstall ResearchFlow AI"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ResearchFlow AI"; Filename: "{app}\ResearchFlowAI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ResearchFlowAI.exe"; Description: "Launch ResearchFlow AI"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  StartupValue: String;
begin
  if CurUninstallStep = usUninstall then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'ResearchFlowAI', StartupValue) then
      if Pos(Lowercase(ExpandConstant('{app}\ResearchFlowAI.exe')), Lowercase(StartupValue)) > 0 then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'ResearchFlowAI');
end;
