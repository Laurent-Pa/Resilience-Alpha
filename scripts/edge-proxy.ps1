<#
.SYNOPSIS
  Pilote le proxy L4 de bord (nginx pour Windows) qui expose le 443 du PC Hôte
  et transmet l'IP réelle des clients au WAF (PROXY protocol). Voir edge/nginx.conf.

.EXAMPLE
  .\scripts\edge-proxy.ps1 start     # démarre (après un test de la configuration)
  .\scripts\edge-proxy.ps1 status    # processus + port 443 à l'écoute
  .\scripts\edge-proxy.ps1 reload    # recharge edge/nginx.conf
  .\scripts\edge-proxy.ps1 stop

.NOTES
  nginx.exe : tools\nginx\nginx.exe par défaut (zip officiel nginx.org décompressé,
  dossier tools\ gitignoré), ou chemin donné par -NginxExe / la variable NGINX_EXE.
#>
param(
    [ValidateSet('start', 'stop', 'reload', 'status', 'test')]
    [string]$Action = 'start',
    [string]$NginxExe = $env:NGINX_EXE
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $NginxExe) { $NginxExe = Join-Path $root 'tools\nginx\nginx.exe' }
if (-not (Test-Path $NginxExe)) {
    throw "nginx.exe introuvable ($NginxExe). Décompresser le zip Windows de nginx.org dans tools\nginx (README, étape 3)."
}

# nginx accepte les barres obliques sous Windows ; elles évitent les pièges d'échappement.
$prefix = ((Join-Path $root 'edge') -replace '\\', '/') + '/'
$conf = $prefix + 'nginx.conf'
New-Item -ItemType Directory -Force (Join-Path $root 'edge\logs') | Out-Null

function Invoke-Nginx([string[]]$NginxArgs) {
    & $NginxExe -p $prefix -c $conf @NginxArgs
    if ($LASTEXITCODE -ne 0) { throw "nginx $($NginxArgs -join ' ') a échoué (code $LASTEXITCODE)." }
}

switch ($Action) {
    'test' {
        Invoke-Nginx @('-t')
    }
    'start' {
        Invoke-Nginx @('-t')
        $nginxDir = Split-Path -Parent $NginxExe
        Start-Process -FilePath $NginxExe -ArgumentList @('-p', $prefix, '-c', $conf) `
            -WorkingDirectory $nginxDir -WindowStyle Hidden
        Start-Sleep -Seconds 1
        if (-not (Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue)) {
            throw "Le port 443 n'est pas à l'écoute : voir edge\logs\error.log."
        }
        Write-Host "Proxy de bord démarré : 443 -> 127.0.0.1:8443 (PROXY protocol)."
    }
    'reload' {
        Invoke-Nginx @('-t')
        Invoke-Nginx @('-s', 'reload')
        Write-Host 'Configuration rechargée.'
    }
    'stop' {
        Invoke-Nginx @('-s', 'quit')
        Write-Host 'Proxy de bord arrêté.'
    }
    'status' {
        Get-Process nginx -ErrorAction SilentlyContinue | Format-Table Id, Path -AutoSize
        Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue |
            Format-Table LocalAddress, LocalPort, OwningProcess -AutoSize
    }
}
