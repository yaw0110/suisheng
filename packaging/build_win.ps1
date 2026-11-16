# Windows 打包：PyInstaller → 放入 llama.cpp（CPU 版）→ Inno Setup 安装程序
# 用法（PowerShell 7）：pwsh packaging/build_win.ps1        可用环境变量 PYTHON 指定解释器
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$ver = & $py -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
$llama = "b12359"
$app = "dist\Suisheng"

Write-Host "==> 1/3 PyInstaller（版本 $ver）"
Remove-Item -Recurse -Force build\pyi, dist -ErrorAction SilentlyContinue
& $py -m PyInstaller --noconfirm --clean --log-level WARN --distpath dist --workpath build\pyi packaging\suisheng.spec
if ($LASTEXITCODE) { throw "PyInstaller 失败" }

Write-Host "==> 2/3 放入 llama.cpp $llama（win-cpu-x64，只取 llama-server 及其 dll）"
$zip = Join-Path $env:TEMP "llama-$llama-bin-win-cpu-x64.zip"
if (-not (Test-Path $zip)) {
  Invoke-WebRequest "https://github.com/ggml-org/llama.cpp/releases/download/$llama/llama-$llama-bin-win-cpu-x64.zip" -OutFile $zip
}
$x = Join-Path $env:TEMP "llama-x"
Remove-Item -Recurse -Force $x -ErrorAction SilentlyContinue
Expand-Archive $zip $x
$src = (Get-ChildItem $x -Recurse -Filter llama-server.exe | Select-Object -First 1).DirectoryName
New-Item -ItemType Directory -Force "$app\llama" | Out-Null
Copy-Item "$src\llama-server.exe" "$app\llama\"
Copy-Item "$src\*.dll" "$app\llama\"
Get-ChildItem $x -Recurse -Include LICENSE* | Select-Object -First 1 | ForEach-Object { Copy-Item $_.FullName "$app\llama\LICENSE" }
Set-Content -Path "$app\llama\VERSION" -Value $llama -Encoding utf8
& "$app\llama\llama-server.exe" --version
if ($LASTEXITCODE) { throw "llama-server 无法运行" }

Write-Host "==> 3/3 Inno Setup 安装程序"
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
  choco install innosetup -y --no-progress | Out-Null
  $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
}
& $iscc "/DAppVersion=$ver" packaging\installer.iss
if ($LASTEXITCODE) { throw "Inno Setup 失败" }
Get-ChildItem dist\*.exe | ForEach-Object { "完成：{0}（{1:N0} MB）" -f $_.Name, ($_.Length / 1MB) }
