; Suisheng Windows 安装程序（Inno Setup 6）。由 packaging/build_win.ps1 调用：ISCC /DAppVersion=x.y.z installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8C1F6E2A-5B3D-4E7A-9F21-3D6C0B9A7E51}
AppName=Suisheng
AppVersion={#AppVersion}
AppVerName=Suisheng {#AppVersion}
AppPublisher=Suisheng contributors
AppPublisherURL=https://github.com/yaw0110/suisheng
AppSupportURL=https://github.com/yaw0110/suisheng/issues
; 装在用户自己的目录，不需要管理员权限
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Suisheng
DefaultGroupName=Suisheng
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Suisheng-{#AppVersion}-windows-x64-setup
SetupIconFile=AppIcon.ico
UninstallDisplayIcon={app}\Suisheng.exe
UninstallDisplayName=Suisheng
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
CloseApplications=yes

[Languages]
#ifexist "compiler:Languages\ChineseSimplified.isl"
Name: "zh"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#else
Name: "en"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Suisheng\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Suisheng"; Filename: "{app}\Suisheng.exe"
Name: "{group}\卸载 Suisheng"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Suisheng"; Filename: "{app}\Suisheng.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Suisheng.exe"; Description: "{cm:LaunchProgram,Suisheng}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM Suisheng.exe /F & taskkill /IM llama-server.exe /F"; Flags: runhidden; RunOnceId: "KillApp"
