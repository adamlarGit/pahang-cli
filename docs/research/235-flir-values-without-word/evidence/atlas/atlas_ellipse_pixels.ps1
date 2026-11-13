param([string]$samples, [string]$out)
$bin = 'C:\Program Files (x86)\FLIR Systems\FLIR Tools\bin'
$global:seen = @{}
[AppDomain]::CurrentDomain.add_AssemblyResolve({ param($s,$e)
  $n = ($e.Name -split ',')[0]
  if ($global:seen.ContainsKey($n)) { return $null }; $global:seen[$n] = 1
  $p = Join-Path $bin ($n + '.dll'); if (Test-Path $p) { return [Reflection.Assembly]::LoadFrom($p) }; return $null })
$env:PATH = "$bin;$env:PATH"
[void][Reflection.Assembly]::LoadFrom("$bin\Flir.Atlas.Image.dll")
# Writes, for every ellipse tool, Atlas's own pixel values (GetValues) to
# <out>/<camera>_<folder>_<image>_<tool>.txt, one value per line, in Atlas's order.
New-Item -ItemType Directory -Force $out | Out-Null
$root = (Resolve-Path $samples).Path.TrimEnd('\')
foreach ($f in Get-ChildItem $samples -Recurse -Filter *.jpg | Sort-Object FullName) {
  $img = New-Object Flir.Atlas.Image.ThermalImageFile
  $img.Open($f.FullName)
  $img.TemperatureUnit = [Flir.Atlas.Image.TemperatureUnit]::Celsius
  foreach ($e in $img.Measurements.MeasurementEllipses) {
    $rel = $f.FullName.Substring($root.Length + 1).Replace('\', '/')
    $name = ($rel -replace '\.jpg$', '' -replace '[/ ]', '_') + "_$($e.Name).txt"
    $v = $e.GetValues()
    "$rel $($e.Name) rect=$($e.Rectangle) count=$($v.Count) avg=$($e.Average.Value) -> $name"
    [IO.File]::WriteAllLines((Join-Path $out $name), [string[]]($v | ForEach-Object { $_.ToString('R') }))
  }
  $img.Close()
}
