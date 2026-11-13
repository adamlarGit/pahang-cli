param([string]$samples)
$bin = 'C:\Program Files (x86)\FLIR Systems\FLIR Tools\bin'
$global:seen = @{}
[AppDomain]::CurrentDomain.add_AssemblyResolve({ param($s,$e)
  $n = ($e.Name -split ',')[0]
  if ($global:seen.ContainsKey($n)) { return $null }; $global:seen[$n] = 1
  $p = Join-Path $bin ($n + '.dll'); if (Test-Path $p) { return [Reflection.Assembly]::LoadFrom($p) }; return $null })
$env:PATH = "$bin;$env:PATH"
[void][Reflection.Assembly]::LoadFrom("$bin\Flir.Atlas.Image.dll")
$first = $true
foreach ($f in Get-ChildItem $samples -Recurse -Filter *.jpg | Sort-Object FullName) {
  "== $($f.Directory.Name)/$($f.Name)"
  try {
    $img = New-Object Flir.Atlas.Image.ThermalImageFile
    $img.Open($f.FullName)
    $img.TemperatureUnit = [Flir.Atlas.Image.TemperatureUnit]::Celsius
    $m = $img.Measurements
    if ($first) { "   MeasurementCollection props: " + (($m.GetType().GetProperties() | % { $_.Name }) -join ', '); $first = $false }
    foreach ($s in $m.MeasurementSpots) { "   spot $($s.Name) at $($s.X),$($s.Y) value=$($s.Value.Value)  GetValueAt=$($img.GetValueAt((New-Object System.Drawing.Point $s.X,$s.Y)).Value)" }
    foreach ($r in $m.MeasurementRectangles) { "   rect $($r.Name) $($r.X),$($r.Y),$($r.Width),$($r.Height) avg=$($r.Average.Value) min=$($r.Min.Value) max=$($r.Max.Value)" }
    foreach ($p in $m.MeasurementPolygons) { "   polygon $($p.Name) avg=$($p.Average.Value)" }
    foreach ($d in $m.MeasurementDeltas) { "   delta $($d.Name) $($d.Measurement1)/$($d.ValueMember1) - $($d.Measurement2)/$($d.ValueMember2) value=$($d.Value.Value)" }
    $img.Close()
  } catch { "   ERROR: $($_.Exception.GetBaseException().Message)" }
}
