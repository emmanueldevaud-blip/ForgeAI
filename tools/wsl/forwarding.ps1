param(
    [int]$SshPort = 22,
    [int]$AppPort = 8000,
    [string]$WindowsIp = "192.168.100.2"
)

$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Ce script doit etre execute dans PowerShell en tant qu'administrateur."
}

$wslIp = (wsl.exe hostname -I).Trim().Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)[0]
if (-not $wslIp) {
    throw "Impossible de trouver l'adresse IP de WSL. Demarrez d'abord WSL."
}

if (-not (Get-NetIPAddress -IPAddress $WindowsIp -ErrorAction SilentlyContinue)) {
    throw "L'adresse IP Windows $WindowsIp n'est pas configuree sur ce PC."
}

foreach ($port in @($SshPort, $AppPort)) {
    netsh.exe interface portproxy delete v4tov4 listenaddress=192.168.100.100 listenport=$port | Out-Null

    $listenAddresses = @($WindowsIp)
    if ($port -ne 22) {
        $listenAddresses += "127.0.0.1"
    }

    foreach ($listenAddress in $listenAddresses) {
        netsh.exe interface portproxy delete v4tov4 listenaddress=$listenAddress listenport=$port | Out-Null
        netsh.exe interface portproxy add v4tov4 `
            listenaddress=$listenAddress listenport=$port connectaddress=$wslIp connectport=$port | Out-Null
    }

    $ruleName = "ForgeAI WSL TCP $port"
    Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $port -Profile Private | Out-Null
}

# Nettoie l'ancienne redirection SSH utilisee par la premiere version du script.
netsh.exe interface portproxy delete v4tov4 listenaddress=192.168.100.100 listenport=22 | Out-Null
netsh.exe interface portproxy delete v4tov4 listenaddress=127.0.0.1 listenport=2222 | Out-Null
netsh.exe interface portproxy delete v4tov4 listenaddress=$WindowsIp listenport=2222 | Out-Null

Write-Host "WSL ($wslIp) est accessible depuis Windows ($WindowsIp) :"
Write-Host "  SSH : ssh -p $SshPort <utilisateur>@$WindowsIp"
Write-Host "  App : http://localhost:$AppPort ou http://$WindowsIp`:$AppPort"
