param(
    [string]$InputFile = (Join-Path $PSScriptRoot '..\作业报告.docx'),
    [string]$OutputFile = (Join-Path $PSScriptRoot '..\.work\report.pdf')
)
$ErrorActionPreference = 'Stop'
$wordApp = $null
$wordDocument = $null
try {
    $wordApp = New-Object -ComObject Word.Application
    $wordApp.Visible = $false
    $wordApp.DisplayAlerts = 0
    $wordDocument = $wordApp.Documents.Open([System.IO.Path]::GetFullPath($InputFile), $false, $true)
    $wordDocument.Fields.Update() | Out-Null
    $wordDocument.ExportAsFixedFormat([System.IO.Path]::GetFullPath($OutputFile), 17)
} finally {
    if ($null -ne $wordDocument) { $wordDocument.Close(0) }
    if ($null -ne $wordApp) { $wordApp.Quit() }
}
