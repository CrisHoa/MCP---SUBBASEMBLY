param([string]$pktPath)

$sacDir = 'C:\Program Files\Autodesk\Subassembly Composer 2026'

$resolving = $false
[System.AppDomain]::CurrentDomain.add_AssemblyResolve({
    param($sender, $args)
    if ($resolving) { return $null }
    try {
        $resolving = $true
        $name = ($args.Name -split ',')[0]
        $targetPath = Join-Path $sacDir "$name.dll"
        if (Test-Path $targetPath) {
            return [System.Reflection.Assembly]::LoadFrom($targetPath)
        }
    } finally {
        $resolving = $false
    }
    return $null
})


Add-Type -AssemblyName 'System.Activities'
Add-Type -AssemblyName 'System.Activities.Presentation'
Add-Type -AssemblyName 'System.Xaml'
Add-Type -AssemblyName 'WindowsBase'
Add-Type -AssemblyName 'PresentationCore'
Add-Type -AssemblyName 'PresentationFramework'

$wfe = [System.Reflection.Assembly]::LoadFrom("$sacDir\WorkflowEditor.dll")
$docType = $wfe.GetType('Autodesk.SubassemblyComposer.WorkflowEditor.SubassemblyDocument')

try {
    Write-Host "Instantiating SubassemblyDocument('$pktPath')..."
    $doc = [System.Activator]::CreateInstance($docType, @($pktPath))
    Write-Host "SUCCESS! Workflow: $($doc.Workflow)"
    Write-Host "InputParameters count: $($doc.InputParameters.Count)"
    Write-Host "TargetParameters count: $($doc.TargetParameters.Count)"
} catch {
    Write-Host "FAILED!"
    Write-Host "Exception: $($_.Exception.ToString())"
    if ($_.Exception.InnerException) {
        Write-Host "InnerException: $($_.Exception.InnerException.ToString())"
        if ($_.Exception.InnerException.InnerException) {
            Write-Host "Inner InnerException: $($_.Exception.InnerException.InnerException.ToString())"
        }
    }
}

