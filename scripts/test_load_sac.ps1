param([string]$pktPath)

Add-Type -Path 'C:\Program Files\Autodesk\Subassembly Composer 2026\Subassembly.API.dll'
Add-Type -Path 'C:\Program Files\Autodesk\Subassembly Composer 2026\Subassembly.WorkflowEngine.dll'
Add-Type -Path 'C:\Program Files\Autodesk\Subassembly Composer 2026\Subassembly.ActivityLibrary.dll'
Add-Type -AssemblyName 'System.Activities'
Add-Type -AssemblyName 'System.Xaml'
Add-Type -AssemblyName 'System.IO.Compression.FileSystem'

$zip = [System.IO.Compression.ZipFile]::OpenRead($pktPath)
$xamlEntry = $zip.Entries | Where-Object { $_.Name -like '*.xaml' }
$stream = $xamlEntry.Open()
try {
    $streamReader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
    $act = [System.Activities.XamlIntegration.ActivityXamlServices]::Load($streamReader)
    Write-Host "SUCCESS: Loaded $pktPath! Type: $($act.GetType().FullName)"
} catch {
    Write-Host "ERROR loading $pktPath : $($_.Exception.ToString())"
} finally {
    if ($stream) { $stream.Close() }
    if ($zip) { $zip.Dispose() }
}
