param([string]$InnoCompiler = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    python tests.py
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    python tests_portable.py
    if ($LASTEXITCODE -ne 0) { throw 'Portable tests failed' }
    python -m PyInstaller --noconfirm --clean --windowed --hidden-import pystray._win32 --exclude-module macos_integration --name ResearchFlowAI --distpath ../dist --workpath ../build --specpath .. app.py
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed' }
    & $InnoCompiler installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
} finally { Pop-Location }
