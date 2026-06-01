# Guia do Executavel Portavel (Windows)

Este documento explica:
- onde esta o executavel gerado do agente
- como instalar em outros computadores
- como gerar novamente o executavel
- o que e necessario para executar em segundo plano

## 1. Onde o executavel esta

No computador onde o build foi feito, existem dois caminhos importantes:

- Artefato de build do PyInstaller:
  - `dist\\agent_monitor_tcc.exe`
- Copia pronta para uso no sistema:
  - `C:\\MonitorTCC\\agent_monitor_tcc.exe`

## 2. Como instalar em outro computador (portavel)

O executavel e portavel no sentido de nao exigir Python instalado no computador destino.

Passos recomendados:

1. Copie o arquivo `agent_monitor_tcc.exe` para o computador destino.
2. Crie as pastas de execucao (ou deixe o script criar a pasta de dados):
   - `C:\\MonitorTCC`
   - `C:\\MonitorTCC\\data`
3. Execute manualmente para validar:

```powershell
C:\MonitorTCC\agent_monitor_tcc.exe --salt TCC2026 --outdir C:\MonitorTCC\data
```

4. Verifique se o CSV foi criado em `C:\\MonitorTCC\\data`.

## 3. O que e necessario para executar

Requisitos no computador destino:

- Windows 10/11 (x64)
- Permissao de escrita no diretorio de saida (`--outdir`)
- Antivírus/EDR nao pode bloquear o executavel
- Para iniciar no boot via Task Scheduler com trigger de startup: privilegios de administrador

Observacoes:

- O parametro `--salt` deve ser definido (ex.: `TCC2026`) para manter a pseudonimizacao consistente.
- O agente grava por padrao em ciclo continuo (`--duration 0`) quando nao for informado outro valor.
- O arquivo CSV e separado por dia/fase/host e e gravado incrementalmente.

## 4. Como gerar novamente o executavel

No projeto, em Windows PowerShell:

```powershell
# 1) Ativar ambiente virtual (opcional se usar caminho completo do Python)
.\.venv\Scripts\Activate.ps1

# 2) Instalar dependencias e pyinstaller
python -m pip install -r requirements.txt pyinstaller

# 3) Gerar executavel unico e sem console
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name agent_monitor_tcc agent_monitor_tcc.py
```

Resultado:

- `dist\\agent_monitor_tcc.exe`

Passo obrigatorio apos o build:

1. Copie o executavel gerado em `dist\\agent_monitor_tcc.exe` para `C:\\MonitorTCC\\agent_monitor_tcc.exe`.
2. Somente depois execute a configuracao da tarefa do passo 5.

## 5. Configurar para iniciar com o Windows (opcional)

Com PowerShell em modo Administrador:

```powershell
$taskName = "MonitorTCC_Agent"
$exeTarget = "C:\MonitorTCC\agent_monitor_tcc.exe"

$action = New-ScheduledTaskAction -Execute $exeTarget -Argument "--salt TCC2026 --outdir C:\MonitorTCC\data"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Start-ScheduledTask -TaskName $taskName
```

Este bloco cria a tarefa sem restricao de bateria, executa no boot e inicia imediatamente.
