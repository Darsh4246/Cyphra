; -- Cyphra Inno Setup Script --
; Packages Cyphra into a professional Windows installer.
; Automatically sets up Desktop shortcuts, Start Menu entries,
; and associates .cyphra and .cyphra-vault files with logo.ico.

#define MyAppName "Cyphra"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Cyphra Security"
#define MyAppURL "https://github.com/Darsh4246/Cyphra"
#define MyAppExeName "Cyphra.exe"

[Setup]
AppId={{D97D84B0-C27B-4B39-9B2F-920E3E8BF312}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=Output
OutputBaseFilename=Cyphra-Setup-{#MyAppVersion}
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\logo.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "assoc_cyphra"; Description: "Associate .cyphra files (Encrypted Containers) with Cyphra"; GroupDescription: "File Associations:"
Name: "assoc_vault"; Description: "Associate .cyphra-vault files (Encrypted Archives) with Cyphra"; GroupDescription: "File Associations:"

[Files]
; Core application code and modules
Source: "cyphra\*"; DestDir: "{app}\cyphra"; Excludes: "*\__pycache__\*,*.pyc"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "cyphra_gui\*"; DestDir: "{app}\cyphra_gui"; Excludes: "*\__pycache__\*,*.pyc"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "logo.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "main.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion

; If a compiled executable exists in dist\, install it as primary launcher:
; Source: "dist\Cyphra.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Launcher batch file for Python runtime execution
Source: "launcher.bat"; DestDir: "{app}"; DestName: "cyphra_launch.bat"; Flags: ignoreversion

[Icons]
; Start Menu and Desktop Shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\cyphra_launch.bat"; IconFilename: "{app}\logo.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\cyphra_launch.bat"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon

[Registry]
; -------------------------------------------------------------
; File Association: .cyphra (Cyphra Encrypted Container)
; -------------------------------------------------------------
Root: HKA; Subkey: "Software\Classes\.cyphra"; ValueType: string; ValueName: ""; ValueData: "Cyphra.EncryptedContainer"; Flags: uninsdeletevalue; Tasks: assoc_cyphra
Root: HKA; Subkey: "Software\Classes\.cyphra"; ValueType: string; ValueName: "Content Type"; ValueData: "application/x-cyphra"; Flags: uninsdeletevalue; Tasks: assoc_cyphra

Root: HKA; Subkey: "Software\Classes\Cyphra.EncryptedContainer"; ValueType: string; ValueName: ""; ValueData: "Cyphra Encrypted Container"; Flags: uninsdeletekey; Tasks: assoc_cyphra
Root: HKA; Subkey: "Software\Classes\Cyphra.EncryptedContainer"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "Cyphra Encrypted Container"; Flags: uninsdeletekey; Tasks: assoc_cyphra

; Assign custom logo.ico icon to all .cyphra files
Root: HKA; Subkey: "Software\Classes\Cyphra.EncryptedContainer\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\logo.ico,0"; Flags: uninsdeletekey; Tasks: assoc_cyphra

; Open command for .cyphra files
Root: HKA; Subkey: "Software\Classes\Cyphra.EncryptedContainer\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Cyphra Vault"; Flags: uninsdeletekey; Tasks: assoc_cyphra
Root: HKA; Subkey: "Software\Classes\Cyphra.EncryptedContainer\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\cyphra_launch.bat"" ""%1"""; Flags: uninsdeletekey; Tasks: assoc_cyphra

; -------------------------------------------------------------
; File Association: .cyphra-vault (Cyphra Encrypted Vault Archive)
; -------------------------------------------------------------
Root: HKA; Subkey: "Software\Classes\.cyphra-vault"; ValueType: string; ValueName: ""; ValueData: "Cyphra.VaultArchive"; Flags: uninsdeletevalue; Tasks: assoc_vault
Root: HKA; Subkey: "Software\Classes\.cyphra-vault"; ValueType: string; ValueName: "Content Type"; ValueData: "application/x-cyphra-vault"; Flags: uninsdeletevalue; Tasks: assoc_vault

Root: HKA; Subkey: "Software\Classes\Cyphra.VaultArchive"; ValueType: string; ValueName: ""; ValueData: "Cyphra Encrypted Vault Archive"; Flags: uninsdeletekey; Tasks: assoc_vault
Root: HKA; Subkey: "Software\Classes\Cyphra.VaultArchive"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "Cyphra Encrypted Vault Archive"; Flags: uninsdeletekey; Tasks: assoc_vault

; Assign custom logo.ico icon to all .cyphra-vault files
Root: HKA; Subkey: "Software\Classes\Cyphra.VaultArchive\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\logo.ico,0"; Flags: uninsdeletekey; Tasks: assoc_vault

; Open command for .cyphra-vault files
Root: HKA; Subkey: "Software\Classes\Cyphra.VaultArchive\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Cyphra Vault"; Flags: uninsdeletekey; Tasks: assoc_vault
Root: HKA; Subkey: "Software\Classes\Cyphra.VaultArchive\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\cyphra_launch.bat"" ""%1"""; Flags: uninsdeletekey; Tasks: assoc_vault

[Run]
Filename: "{app}\cyphra_launch.bat"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

