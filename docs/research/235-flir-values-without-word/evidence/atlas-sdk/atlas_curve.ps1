param([string]$file)
$bin = 'C:\Program Files (x86)\FLIR Systems\FLIR Tools\bin'
$global:seen = @{}
[AppDomain]::CurrentDomain.add_AssemblyResolve({ param($s,$e)
  $n = ($e.Name -split ',')[0]
  if ($global:seen.ContainsKey($n)) { return $null }; $global:seen[$n] = 1
  $p = Join-Path $bin ($n + '.dll'); if (Test-Path $p) { return [Reflection.Assembly]::LoadFrom($p) }; return $null })
$env:PATH = "$bin;$env:PATH"
[void][Reflection.Assembly]::LoadFrom("$bin\Flir.Atlas.Image.dll")
$img = New-Object Flir.Atlas.Image.ThermalImageFile
$img.Open($file)
$img.TemperatureUnit = [Flir.Atlas.Image.TemperatureUnit]::Celsius
$tp = $img.ThermalParameters
$tp.GetType().GetProperties() | % { "PARAM $($_.Name)=$($_.GetValue($tp, $null))" }
foreach ($r in 12000,13000,14000,15000,15500,16000,17000,18000,20000) { "CURVE $r $($img.GetValueFromSignal($r))" }
$img.Close()
