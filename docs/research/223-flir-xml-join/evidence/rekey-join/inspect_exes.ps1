$flirBin = "C:\Program Files (x86)\FLIR Systems\FLIR Word Reporting\bin"

foreach ($exe in @("RapidReportCreator.exe", "CreateNewTemplate.exe")) {
    Write-Host "`n=== $exe ==="
    try {
        $asm = [Reflection.Assembly]::LoadFrom("$flirBin\$exe")
        $asm.GetExportedTypes() | ForEach-Object {
            Write-Host "Type: $($_.FullName)"
            $methods = $_.GetMethods([Reflection.BindingFlags]"Public,Instance,Static,DeclaredOnly") | Select-Object -ExpandProperty Name -Unique
            if ($methods) {
                Write-Host "  Methods: $($methods -join ', ')"
            }
        }
    } catch {
        Write-Host "Error: $_"
    }
}
