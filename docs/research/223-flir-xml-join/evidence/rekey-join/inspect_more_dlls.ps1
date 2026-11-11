$flirBin = "C:\Program Files (x86)\FLIR Systems\FLIR Word Reporting\bin"

foreach ($dll in @("Interop.WordAddin.dll", "Interop.IRViewer.dll", "ReporterSDK.dll", "IRField.dll")) {
    Write-Host "`n=== $dll ==="
    try {
        $asm = [Reflection.Assembly]::LoadFrom("$flirBin\$dll")
        $asm.GetExportedTypes() | ForEach-Object {
            Write-Host "Type: $($_.FullName) ($($_.BaseType.Name))"
            $methods = $_.GetMethods([Reflection.BindingFlags]"Public,Instance,Static,DeclaredOnly") | Select-Object -ExpandProperty Name -Unique
            if ($methods) {
                Write-Host "  Methods: $($methods -join ', ')"
            }
        }
    } catch {
        Write-Host "Error: $_"
    }
}
