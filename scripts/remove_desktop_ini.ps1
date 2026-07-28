param (
    [Parameter(Mandatory=$true, HelpMessage="Enter the folder path to scan")]
    [string]$FolderPath
)

if (Test-Path -Path $FolderPath) {
    Write-Host "Scanning for desktop.ini in '$FolderPath' and its subfolders..." -ForegroundColor Cyan
    
    # -Force is needed to find and remove hidden/system desktop.ini files
    $files = Get-ChildItem -Path $FolderPath -Filter "desktop.ini" -Recurse -Force -ErrorAction SilentlyContinue
    
    if ($files) {
        # Count the files. If it's a single file, $files.Count might be $null, so we wrap in array
        $fileArray = @($files)
        $fileArray | Remove-Item -Force -Verbose
        Write-Host "Successfully removed $($fileArray.Count) desktop.ini file(s)." -ForegroundColor Green
    } else {
        Write-Host "No desktop.ini files found." -ForegroundColor Yellow
    }
} else {
    Write-Host "The path '$FolderPath' does not exist. Please check the path and try again." -ForegroundColor Red
}
