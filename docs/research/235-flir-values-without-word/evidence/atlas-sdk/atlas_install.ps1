# Records what of FLIR Atlas is installed: assemblies, versions, bitness, licence files.
$bin = 'C:\Program Files (x86)\FLIR Systems\FLIR Tools\bin'
"Atlas assemblies in FLIR Tools\bin:"
Get-ChildItem $bin -Filter 'Flir.Atlas*.dll' | ForEach-Object {
  $n = [Reflection.AssemblyName]::GetAssemblyName($_.FullName)
  "  $($_.Name)  assembly $($n.Version)  file $($_.VersionInfo.FileVersion)  arch $($n.ProcessorArchitecture)"
}
"Licence-related files under FLIR Systems (depth 3):"
Get-ChildItem 'C:\Program Files (x86)\FLIR Systems' -Recurse -Depth 3 -File | Where-Object { $_.Name -match 'licen|eula' -and $_.Name -notmatch '\.resources\.dll$' } | ForEach-Object { "  " + $_.FullName.Substring('C:\Program Files (x86)\FLIR Systems\'.Length) }
"licenses.html section headings:"
[regex]::Matches((Get-Content "$bin\licenses.html" -Raw), '<h2>([^<]*)') | ForEach-Object { "  " + $_.Groups[1].Value }
"Mentions of 'Atlas' in licenses.html: " + ([regex]::Matches((Get-Content "$bin\licenses.html" -Raw), 'Atlas')).Count
