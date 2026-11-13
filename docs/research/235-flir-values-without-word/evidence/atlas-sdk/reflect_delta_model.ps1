# Lists the FLIR SDK's delta (Dt) model and every member that mentions an
# absolute or subtraction mode, in FLIR Tools+ and FLIR Word Reporting.
# Run in 32-bit PowerShell (C:\Windows\SysWOW64\WindowsPowerShell\v1.0).
$tools = 'C:\Program Files (x86)\FLIR Systems\FLIR Tools\bin'
$global:bin = $tools
$global:seen = @{}
[AppDomain]::CurrentDomain.add_AssemblyResolve({ param($s,$e)
  $n = ($e.Name -split ',')[0]
  if ($global:seen.ContainsKey($n)) { return $null }; $global:seen[$n] = 1
  $p = Join-Path $global:bin ($n + '.dll'); if (Test-Path $p) { return [Reflection.Assembly]::LoadFrom($p) }; return $null })
function TypesOf($path) {
  $a = [Reflection.Assembly]::LoadFrom($path)
  try { $a.GetTypes() } catch [Reflection.ReflectionTypeLoadException] { $_.Exception.Types | ? { $_ } }
}
"## Flir.Cronos.IR.Formats.DeltaT (Flir.FormatPlugin.IRSDK.dll)"
$d = TypesOf "$tools\Flir.FormatPlugin.IRSDK.dll" | ? { $_.FullName -eq 'Flir.Cronos.IR.Formats.DeltaT' }
$d.GetProperties() | % { "   $($_.PropertyType.Name) $($_.Name)" }
foreach ($n in 'DeltaType1','ValueMember1') { $pt = $d.GetProperty($n).PropertyType
  "   enum $($pt.FullName): " + (([Enum]::GetNames($pt) | % { "$_=$([int][Enum]::Parse($pt,$_))" }) -join ', ') }
"## Members named Absolute/Substraction, or typed SubstractionMode*"
$bf = [Reflection.BindingFlags]'Instance,Static,Public,NonPublic,DeclaredOnly'
foreach ($dll in 'Flir.Cronos.Common.dll','Flir.Atlas.Image.dll','Flir.Modules.Common.dll','Flir.FormatPlugin.IRSDK.dll') {
  foreach ($t in TypesOf "$tools\$dll") {
    if ($t.IsEnum -and ([Enum]::GetNames($t) -match 'Abs').Count) { "   $dll enum $($t.FullName): " + (([Enum]::GetNames($t) | % { "$_=$([int][Enum]::Parse($t,$_))" }) -join ', ') }
    try { $ms = @($t.GetProperties($bf)) + @($t.GetFields($bf)) } catch { continue }
    foreach ($m in $ms) { try { $tn = if ($m -is [Reflection.PropertyInfo]) { $m.PropertyType.Name } else { $m.FieldType.Name } } catch { continue }
      if (-not $t.IsEnum -and ($tn -match 'SubstractionMode|SubtractionMode' -or $m.Name -match 'Absolute|AbsValue')) { "   $dll $($t.FullName).$($m.Name) : $tn" } }
  }
}
