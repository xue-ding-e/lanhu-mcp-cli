# lanhu CLI PowerShell 垫片:URL 含 & 也安全(cmd.exe 垫片会被 & 截断,PowerShell 里优先用本垫片)
# 用法: .\lanhu.ps1 interactions "https://lanhuapp.com/...&image_id=xxx"
$env:PYTHONIOENCODING = 'utf-8'
& "$PSScriptRoot\venv\Scripts\python.exe" "$PSScriptRoot\lanhu_cli.py" @args
exit $LASTEXITCODE
