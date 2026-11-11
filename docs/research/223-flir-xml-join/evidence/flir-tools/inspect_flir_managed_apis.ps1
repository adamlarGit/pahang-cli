param([string]$AssemblyPath, [string]$OutputPath)
$ErrorActionPreference = 'Stop'
$flirRoots = @(
    'C:\Program Files (x86)\FLIR Systems\FLIR Tools\bin',
    'C:\Program Files (x86)\FLIR Systems\FLIR Word Reporting\bin'
)
[AppDomain]::CurrentDomain.add_ReflectionOnlyAssemblyResolve({
    param($sender, $eventArgs)
    $shortName = ([Reflection.AssemblyName]::new($eventArgs.Name)).Name + '.dll'
    foreach ($dir in $flirRoots) {
        $candidatePath = Join-Path $dir $shortName
        if (Test-Path -LiteralPath $candidatePath) {
            return [Reflection.Assembly]::ReflectionOnlyLoadFrom($candidatePath)
        }
    }
    return [Reflection.Assembly]::ReflectionOnlyLoad($eventArgs.Name)
})
$assembly = [Reflection.Assembly]::ReflectionOnlyLoadFrom($AssemblyPath)
$typeErrors = @()
try { $types = $assembly.GetTypes() }
catch [Reflection.ReflectionTypeLoadException] {
    $types = $_.Exception.Types | Where-Object { $null -ne $_ }
    $typeErrors = @($_.Exception.LoaderExceptions | ForEach-Object { $_.Message })
}
$entries = foreach ($type in $types) {
    if (-not ($type.IsPublic -or $type.IsNestedPublic)) { continue }
    try {
        $methods = @($type.GetMethods([Reflection.BindingFlags]'Public,Instance,Static,DeclaredOnly') | ForEach-Object {
            $methodInfo = $_
            try {
                [ordered]@{
                    Name = $methodInfo.Name
                    Static = $methodInfo.IsStatic
                    ReturnType = $methodInfo.ReturnType.FullName
                    Parameters = @($methodInfo.GetParameters() | ForEach-Object { [ordered]@{Name=$_.Name;Type=$_.ParameterType.FullName;Out=$_.IsOut} })
                }
            } catch { [ordered]@{Name=$methodInfo.Name;Error=$_.Exception.Message} }
        })
        [ordered]@{
            Name = $type.FullName
            Base = $type.BaseType.FullName
            Constructors = @($type.GetConstructors() | ForEach-Object { $_.ToString() })
            Methods = $methods
        }
    } catch {
        [ordered]@{Name=$type.FullName;Error=$_.Exception.Message}
    }
}
$out = [ordered]@{
    Path = $AssemblyPath
    SHA256 = (Get-FileHash -LiteralPath $AssemblyPath -Algorithm SHA256).Hash
    AssemblyName = $assembly.FullName
    ReferencedAssemblies = @($assembly.GetReferencedAssemblies() | ForEach-Object { $_.FullName })
    Errors = $typeErrors
    Types = @($entries)
}
$out | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Write-Output ($assembly.GetName().Name + ': ' + @($entries).Count + ' exported types; loader errors ' + $typeErrors.Count)
