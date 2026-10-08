; okuma.iss — Inno Setup 6 kurulum tarifi. Çalıştır: python packaging/build.py --kurulum
;
; Kullanıcı başına kurulum, yönetici izni istemez: %LOCALAPPDATA%\Programs\Okuma Atolyesi.
; Kitaplık (PDF kopyaları, notlar) kurulum klasöründe DEĞİL: %USERPROFILE%\OkumaAtolyesiVeri
; ve %APPDATA%\OkumaAtolyesi. Kaldırma onlara dokunmaz; yalnızca "Birlikte aç"
; kaydını (HKCU) temizler.

#ifndef Surum
  #define Surum "1.1.1"
#endif
#ifndef Kok
  #define Kok ".."
#endif

[Setup]
AppId={{0679A8AA-15CB-4EC9-AE87-54BB30EB8D2E}
AppName=Okuma Atölyesi
AppVersion={#Surum}
AppVerName=Okuma Atölyesi {#Surum}
AppPublisher=ledaronn
AppPublisherURL=https://github.com/ledaronn/okuma-atolyesi
AppSupportURL=https://github.com/ledaronn/okuma-atolyesi/issues
AppUpdatesURL=https://github.com/ledaronn/okuma-atolyesi/releases
DefaultDirName={autopf}\Okuma Atolyesi
DefaultGroupName=Okuma Atölyesi
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile={#Kok}\LICENSE
SetupIconFile={#Kok}\okuma.ico
UninstallDisplayIcon={app}\OkumaAtolyesi.exe
UninstallDisplayName=Okuma Atölyesi
OutputDir={#Kok}\dist
OutputBaseFilename=OkumaAtolyesi-Setup-{#Surum}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Kok}\dist\OkumaAtolyesi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Okuma Atölyesi"; Filename: "{app}\OkumaAtolyesi.exe"
Name: "{autodesktop}\Okuma Atölyesi"; Filename: "{app}\OkumaAtolyesi.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OkumaAtolyesi.exe"; Description: "{cm:LaunchProgram,Okuma Atölyesi}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\OkumaAtolyesi.exe"; Parameters: "--kayit-kaldir"; Flags: runhidden waituntilterminated; RunOnceId: "KayitKaldir"
