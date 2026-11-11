$flirBin = "C:\Program Files (x86)\FLIR Systems\FLIR Word Reporting\bin"

Write-Host "=== WizardClassLibrary.dll ==="
$wcl = [Reflection.Assembly]::LoadFrom("$flirBin\WizardClassLibrary.dll")
$wcl.GetExportedTypes() | ForEach-Object {
    Write-Host "Type: $($_.FullName)"
    $methods = $_.GetMethods([Reflection.BindingFlags]"Public,Instance,Static,DeclaredOnly") | Select-Object -ExpandProperty Name -Unique
    if ($methods) {
        Write-Host "  Methods: $($methods -join ', ')"
    }
    $props = $_.GetProperties([Reflection.BindingFlags]"Public,Instance,Static,DeclaredOnly") | Select-Object -ExpandProperty Name
    if ($props) {
        Write-Host "  Props: $($props -join ', ')"
    }
}
