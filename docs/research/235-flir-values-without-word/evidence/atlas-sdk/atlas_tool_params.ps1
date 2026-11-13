param([string]$samples)
$bin = 'C:\Program Files (x86)\FLIR Systems\FLIR Tools\bin'
$global:seen = @{}
[AppDomain]::CurrentDomain.add_AssemblyResolve({ param($s,$e)
  $n = ($e.Name -split ',')[0]
  if ($global:seen.ContainsKey($n)) { return $null }; $global:seen[$n] = 1
  $p = Join-Path $bin ($n + '.dll'); if (Test-Path $p) { return [Reflection.Assembly]::LoadFrom($p) }; return $null })
$env:PATH = "$bin;$env:PATH"
[void][Reflection.Assembly]::LoadFrom("$bin\Flir.Atlas.Image.dll")
# Prints, for every measurement in every sample, the object parameters Atlas
# applies to it (MeasurementParameters) next to the image's own.
foreach ($f in Get-ChildItem $samples -Recurse -Filter *.jpg | Sort-Object FullName) {
  "== " + $f.FullName.Substring((Resolve-Path $samples).Path.TrimEnd('\').Length + 1).Replace('\','/')
  $img = New-Object Flir.Atlas.Image.ThermalImageFile
  $img.Open($f.FullName)
  $img.TemperatureUnit = [Flir.Atlas.Image.TemperatureUnit]::Celsius
  $p = $img.ThermalParameters
  "   image E=$($p.Emissivity) D=$($p.Distance) Refl=$($p.ReflectedTemperature) Atm=$($p.AtmosphericTemperature) RH=$($p.RelativeHumidity) Tau=$($p.Transmission)"
  $m = $img.Measurements
  foreach ($s in @($m.MeasurementSpots) + @($m.MeasurementRectangles) + @($m.MeasurementEllipses) + @($m.MeasurementPolygons)) {
    if ($s -eq $null) { continue }
    $t = $s.ThermalParameters
    "   $($s.GetType().Name) $($s.Name) custom=$($t.UseCustomObjectParameters) E=$($t.Emissivity) D=$($t.Distance) Refl=$($t.ReflectedTemperature)"
  }
  $img.Close()
}
