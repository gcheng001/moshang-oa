; 办公助手（摩尚OA v2）Windows 安装包脚本
; 编译：ISCC.exe installer.iss  产出：installer_output\MoshangOA-Setup.exe
; 装到 %LOCALAPPDATA%\Programs\办公助手（用户级，无需管理员权限，应用可读写 edge-profile/logs）

#define MyAppName "办公助手"
#define MyAppNameASCII "MoshangOA"
#define MyAppVersion "2.3.0"
#define MyAppPublisher "摩尚律师事务所"
#define MyAppExeName "办公助手"

[Setup]
AppId={{B7F2A1C6-3D4E-4F5B-9A8D-1C2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\AppIcon.ico
UninstallDisplayName={#MyAppName}
OutputDir=installer_output
OutputBaseFilename=MoshangOA-Setup
SetupIconFile=..\docs\appicon\AppIcon.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
LanguageDetectionMethod=none
ShowLanguageDialog=no
DisableDirPage=no
DisableReadyPage=yes

[Languages]
; 中文 ISL 暂不可用（镜像连不通），用默认英文向导；应用本身仍为中文
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\MoshangOA-Win\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Tasks]
Name: "desktopicon"; Description: "在桌面创建快捷方式"; GroupDescription: "附加选项:"
Name: "autostart"; Description: "登录 Windows 后自动启动并在系统托盘值守"; GroupDescription: "附加选项:"; Flags: checkedonce

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MoshangOfficeAssistant"; ValueData: """{app}\python\pythonw.exe"" ""{app}\app\backend\serve_win.py"""; Flags: uninsdeletevalue; Tasks: autostart

[Icons]
; 开始菜单 - 主入口（pythonw 无控制台，日常体验干净）
Name: "{group}\{#MyAppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "serve_win.py"; WorkingDir: "{app}\app\backend"; IconFilename: "{app}\AppIcon.ico"; Comment: "启动办公助手（摩尚OA v2）"
; 开始菜单 - 调试入口（python.exe 带控制台，启动失败可见错误）
Name: "{group}\{#MyAppName}（调试模式）"; Filename: "{app}\python\python.exe"; Parameters: "serve_win.py"; WorkingDir: "{app}\app\backend"; IconFilename: "{app}\AppIcon.ico"; Comment: "启动办公助手（带控制台，排错用）"
; 开始菜单 - 卸载
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"; Comment: "卸载办公助手"
; 桌面 - 主入口
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "serve_win.py"; WorkingDir: "{app}\app\backend"; IconFilename: "{app}\AppIcon.ico"; Tasks: desktopicon; Comment: "启动办公助手（摩尚OA v2）"

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "serve_win.py"; WorkingDir: "{app}\app\backend"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

; 卸载前请从系统托盘退出办公助手。不能按进程名 taskkill，
; 否则会误杀用户正在运行的其他 Python 程序。

[UninstallDelete]
Type: filesandordirs; Name: "{app}\edge-profile"
Type: filesandordirs; Name: "{app}\logs"
