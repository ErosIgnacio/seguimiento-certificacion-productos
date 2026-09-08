param(
    [string]$PythonCommand = "python",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$PythonExecutable = (Get-Command $PythonCommand -ErrorAction Stop).Source
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$VersionFile = Join-Path $ProjectRoot "certificacion\version.py"
$VersionText = Get-Content -LiteralPath $VersionFile -Raw
$VersionMatch = [regex]::Match($VersionText, '__version__\s*=\s*"([^"]+)"')
if (-not $VersionMatch.Success) {
    throw "No se pudo obtener la version desde $VersionFile"
}
$AppVersion = $VersionMatch.Groups[1].Value

$DotNetCommand = Get-Command "dotnet.exe" -ErrorAction SilentlyContinue
$DotNetFallback = Join-Path $env:ProgramFiles "dotnet\dotnet.exe"
if ($DotNetCommand) {
    $DotNet = $DotNetCommand.Source
} elseif (Test-Path -LiteralPath $DotNetFallback -PathType Leaf) {
    $DotNet = $DotNetFallback
} else {
    throw "No se encontro .NET SDK 8. Instale Microsoft.DotNet.SDK.8."
}

$ConfigPath = Join-Path $ProjectRoot "config.json"
$IconPath = Join-Path $ProjectRoot "icon\certification.ico"
$SpecPath = Join-Path $ProjectRoot "certificacion_carga.spec"
$WixSource = Join-Path $ProjectRoot "installer\msi\CertificacionCarga.wxs"
$OutputDirectory = Join-Path $ProjectRoot "installer\output"
$MsiPath = Join-Path $OutputDirectory "CertificacionCarga-$AppVersion.msi"

foreach ($RequiredFile in @(
    $ConfigPath,
    $IconPath,
    $SpecPath,
    $WixSource
)) {
    if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
        throw "Falta un archivo requerido: $RequiredFile"
    }
}

$TempBase = [IO.Path]::GetFullPath(
    (Join-Path ([IO.Path]::GetTempPath()) "CertificacionCargaMsi")
)
$WorkPath = [IO.Path]::GetFullPath(
    (Join-Path $TempBase ([guid]::NewGuid().ToString("N")))
)
if (-not $WorkPath.StartsWith(
    $TempBase,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw "La ruta temporal calculada no es segura: $WorkPath"
}
$DistRoot = Join-Path $WorkPath "dist"
$BuildRoot = Join-Path $WorkPath "build"
New-Item -ItemType Directory -Path $WorkPath -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

Push-Location $ProjectRoot
try {
    Write-Host "Validando Python y Tcl/Tk..."
    & $PythonExecutable -B -c (
        "import struct, tkinter; " +
        "tcl = tkinter.Tcl(); " +
        "assert struct.calcsize('P') * 8 == 64; " +
        "print('Python/Tcl', tcl.eval('info patchlevel'))"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Python no tiene Tcl/Tk funcional en 64 bits."
    }

    & $PythonExecutable -B -c "import customtkinter, pymysql, PyInstaller"
    if ($LASTEXITCODE -ne 0) {
        throw "Faltan dependencias de construccion o ejecucion."
    }

    if (-not $SkipTests) {
        Write-Host "Ejecutando pruebas..."
        & $PythonExecutable -B -m unittest discover -s tests -p "test_*.py"
        if ($LASTEXITCODE -ne 0) {
            throw "Las pruebas fallaron. Se cancela la compilacion MSI."
        }
    }

    Write-Host "Construyendo aplicacion $AppVersion con PyInstaller..."
    & $PythonExecutable -B -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $DistRoot `
        --workpath $BuildRoot `
        $SpecPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller no pudo construir la aplicacion."
    }

    $AppDirectory = Join-Path $DistRoot "certificacion_carga"
    $Executable = Join-Path $AppDirectory "certificacion_carga.exe"
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw "No se genero el ejecutable esperado: $Executable"
    }
    $PlainConfigs = @(
        Get-ChildItem -LiteralPath $AppDirectory -Recurse -File |
            Where-Object { $_.Name -ieq "config.json" }
    )
    if ($PlainConfigs.Count -gt 0) {
        throw "Validacion de seguridad fallida: config.json quedo en la aplicacion."
    }

    Write-Host "Restaurando WiX Toolset 5.0.2..."
    & $DotNet tool restore
    if ($LASTEXITCODE -ne 0) {
        throw "No fue posible restaurar WiX Toolset."
    }

    Write-Host "Construyendo MSI por usuario..."
    & $DotNet tool run wix -- build `
        $WixSource `
        -arch x64 `
        -d "AppVersion=$AppVersion" `
        -d "AppSourceDir=$AppDirectory" `
        -d "ConfigPath=$ConfigPath" `
        -d "IconPath=$IconPath" `
        -pdbtype none `
        -o $MsiPath
    if ($LASTEXITCODE -ne 0) {
        throw "WiX no pudo construir el instalador MSI."
    }
    if (-not (Test-Path -LiteralPath $MsiPath -PathType Leaf)) {
        throw "No se encontro el MSI esperado: $MsiPath"
    }

    $Hash = Get-FileHash -Algorithm SHA256 -LiteralPath $MsiPath
    $HashPath = "$MsiPath.sha256"
    "$($Hash.Hash)  $([IO.Path]::GetFileName($MsiPath))" |
        Set-Content -LiteralPath $HashPath -Encoding ascii
    Write-Host "MSI creado en: $MsiPath"
    Write-Host "SHA-256 guardado en: $HashPath"
}
finally {
    Pop-Location
    if (
        (Test-Path -LiteralPath $WorkPath) -and
        $WorkPath.StartsWith(
            $TempBase,
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        try {
            Remove-Item -LiteralPath $WorkPath -Recurse -Force
        }
        catch {
            Write-Warning "No se pudo limpiar la carpeta temporal: $WorkPath"
        }
    }
}
