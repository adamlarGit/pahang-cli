param()
$bin = 'C:\Program Files (x86)\FLIR Systems\FLIR Tools\bin'
$global:seen = @{}
[AppDomain]::CurrentDomain.add_AssemblyResolve({ param($s,$e)
  $n = ($e.Name -split ',')[0]
  if ($global:seen.ContainsKey($n)) { return $null }; $global:seen[$n] = 1
  $p = Join-Path $bin ($n + '.dll'); if (Test-Path $p) { return [Reflection.Assembly]::LoadFrom($p) }; return $null })
$env:PATH = "$bin;$env:PATH"
# Lists the public types and their public methods in Atlas's DocX engine.
foreach ($dll in 'Flir.Atlas.DocXEngine.dll', 'Flir.Atlas.DocXEngine.ProxyObjects.dll') {
  "== $dll"
  $a = [Reflection.Assembly]::LoadFrom("$bin\$dll")
  try { $types = $a.GetExportedTypes() } catch { $types = $_.Exception.InnerException.Types | Where-Object { $_ } }
  foreach ($t in $types | Sort-Object FullName) {
    "  type $($t.FullName)"
    $t.GetMethods([Reflection.BindingFlags]'Public,Instance,Static,DeclaredOnly') | Where-Object { -not $_.IsSpecialName } | ForEach-Object { "      $($_.ToString())" } | Select-Object -First 25
  }
}
