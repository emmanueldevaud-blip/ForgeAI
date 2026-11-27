$ErrorActionPreference = "Stop"
Set-Location "D:\ForgeAI"

$Log = "D:\ForgeAI\logs\startup.log"
New-Item -ItemType Directory -Force "D:\ForgeAI\logs" | Out-Null

function Log($Message) {
    Add-Content -Path $Log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $Message"
}

try {
    Log "Démarrage de ForgeAI"

    # Attendre Docker Desktop
    $DockerReady = $false
    for ($i = 0; $i -lt 60; $i++) {
        docker info *> $null
        if ($LASTEXITCODE -eq 0) {
            $DockerReady = $true
            break
        }
        Start-Sleep -Seconds 5
    }

    if (-not $DockerReady) {
        throw "Docker Desktop ne répond pas après 5 minutes."
    }

    Log "Docker est prêt"

    # Démarrer MySQL
    docker compose up -d mysql
    if ($LASTEXITCODE -ne 0) {
        throw "Impossible de démarrer MySQL."
    }

    # Attendre MySQL
    $MySQLReady = $false
    for ($i = 0; $i -lt 60; $i++) {
        $TcpReady = Test-NetConnection -ComputerName "127.0.0.1" -Port 3306 -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($TcpReady) {
            $MySQLReady = $true
            break
        }
        Start-Sleep -Seconds 5
    }

    if (-not $MySQLReady) {
        throw "MySQL ne répond pas après 5 minutes."
    }

    Log "MySQL est prêt"

    # Vérifier si ForgeAI tourne déjà
    $Existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($Existing) {
        Log "Le port 8000 est déjà occupé. Aucun second serveur lancé."
        exit 0
    }

    # Vérifier Python
    $Python = "D:\ForgeAI\.venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) {
        throw "Python de l'environnement virtuel introuvable."
    }

    # Démarrer Uvicorn en arrière-plan
    $Process = Start-Process -FilePath $Python `
        -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" `
        -WorkingDirectory "D:\ForgeAI" `
        -WindowStyle Hidden `
        -RedirectStandardOutput "D:\ForgeAI\logs\uvicorn.log" `
        -RedirectStandardError "D:\ForgeAI\logs\uvicorn-error.log" `
        -PassThru

    Log "Uvicorn lancé. PID=$($Process.Id)"
}
catch {
    Log "ERREUR : $_"
    exit 1
}

