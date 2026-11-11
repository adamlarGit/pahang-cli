$atlasPath = "C:\Program Files\FLIR\FLIR Thermal Studio\Flir.Atlas.Image.dll"
$asm = [Reflection.Assembly]::LoadFrom($atlasPath)

Write-Host "=== Flir.Atlas.Image.dll ==="
$asm.GetExportedTypes() | ForEach-Object {
    if ($_.Name -like "*Image*" -or $_.Name -like "*Measurement*" -or $_.Name -like "*Thermal*" -or $_.Name -like "*Spot*" -or $_.Name -like "*Palette*") {
        Write-Host "Type: $($_.FullName)"
        $methods = $_.GetMethods([Reflection.BindingFlags]"Public,Instance,Static,DeclaredOnly") | Select-Object -ExpandProperty Name -Unique
        if ($methods) {
            Write-Host "  Methods: $($methods -join ', ')"
        }
    }
}
