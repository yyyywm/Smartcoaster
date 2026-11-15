param(
    [switch]$SkipInstall,
    [string]$CondaEnvironment = 'dsh_coaster'
)
$ErrorActionPreference = 'Stop'
Get-Command conda -ErrorAction Stop | Out-Null
# Use the requested existing environment and ignore user-site Python packages.
$pythonArguments = @('run', '--no-capture-output', '-n', $CondaEnvironment, 'python', '-s', '-X', 'utf8')
Push-Location $PSScriptRoot
try {
    if (-not $SkipInstall) {
        & conda @pythonArguments -m pip install -r requirements-build.txt
        if ($LASTEXITCODE -ne 0) { throw 'Installing build dependencies failed.' }
    }
    & conda @pythonArguments smart_coaster.py --selftest
    if ($LASTEXITCODE -ne 0) { throw 'Desktop tests failed; package not built.' }
    $releaseName = 'SmartCoaster-Windows-x64-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    $distributionDirectory = Join-Path $PSScriptRoot ('build\dist\' + $releaseName)
    & conda @pythonArguments -m PyInstaller --noconfirm --clean --distpath $distributionDirectory --workpath build SmartCoaster.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    $releaseDirectory = Join-Path $PSScriptRoot 'release'
    $packageDirectory = Join-Path $releaseDirectory $releaseName
    New-Item -ItemType Directory -Path $packageDirectory | Out-Null
    Copy-Item -LiteralPath (Join-Path $distributionDirectory 'SmartCoaster.exe') -Destination $packageDirectory
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'DISTRIBUTION.md') -Destination (Join-Path $packageDirectory 'README.txt')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '..\LICENSE') -Destination (Join-Path $packageDirectory 'LICENSE.txt')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '..\THIRD_PARTY_NOTICES.md') -Destination $packageDirectory
    & conda @pythonArguments -m pip freeze | Set-Content -LiteralPath (Join-Path $packageDirectory 'build-dependencies.txt') -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw 'Recording dependencies failed.' }
    $licenseScript = @'
from importlib.metadata import distribution
from pathlib import Path
import sys
dest = Path(sys.argv[1]) / 'licenses'
dest.mkdir()
for name in ('Pillow', 'pyserial', 'pystray', 'six'):
    dist = distribution(name)
    for file in dist.files or []:
        if 'license' in Path(str(file)).name.lower() or 'copying' in Path(str(file)).name.lower():
            source = Path(dist.locate_file(file))
            if source.is_file():
                (dest / (name + '-' + source.name)).write_bytes(source.read_bytes())
for filename in ('LICENSE_PYTHON.txt', 'LICENSE.txt'):
    python_license = Path(sys.base_prefix) / filename
    if python_license.is_file():
        (dest / 'Python-LICENSE.txt').write_bytes(python_license.read_bytes())
        break
for component in ('tcl8.6', 'tk8.6'):
    source = Path(sys.base_prefix) / 'Library' / 'lib' / component / 'license.terms'
    if source.is_file():
        (dest / (component + '-license.terms')).write_bytes(source.read_bytes())
'@
    $licenseScript | & conda @pythonArguments - $packageDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Collecting license files failed.' }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '..\LICENSES\pyserial-3.5.txt') -Destination (Join-Path $packageDirectory 'licenses')
    $digest = (Get-FileHash -LiteralPath (Join-Path $packageDirectory 'SmartCoaster.exe') -Algorithm SHA256).Hash
    "$digest  SmartCoaster.exe" | Set-Content -LiteralPath (Join-Path $packageDirectory 'SHA256.txt') -Encoding ASCII
    $archivePath = Join-Path $releaseDirectory ($releaseName + '.zip')
    Compress-Archive -LiteralPath $packageDirectory -DestinationPath $archivePath
    Write-Output "Package: $archivePath"
    Write-Output "Executable: $(Join-Path $packageDirectory 'SmartCoaster.exe')"
} finally {
    Pop-Location
}
