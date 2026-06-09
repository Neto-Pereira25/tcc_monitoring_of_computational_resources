# Guia do Executavel Portavel (Windows) - Cenario POST

Este documento explica:
- onde esta o executavel gerado do agente
- como instalar em outros computadores
- como gerar novamente o executavel
- o que e necessario para executar em segundo plano no cenario post-intervencao

Contexto do cenario POST:

- no TCC, o periodo post-intervencao considera a aplicacao de politicas de energia
- para esse cenario, o agente deve ser executado com `--phase post`
- as politicas podem ser aplicadas por linha de comando antes do agendamento

## 1. Onde o executavel esta

**Importante:** O mesmo executável funciona para baseline e post. A diferença é o parâmetro `--phase` na linha de comando.

No computador onde o build foi feito, existem dois caminhos importantes:

- Artefato de build do PyInstaller:
  - `dist\\agent_monitor_tcc.exe`
- Copia pronta para uso no sistema (para ambos os cenários):
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
2. Esse executável será usado tanto para baseline quanto para post (o comportamento é controlado pelo parâmetro `--phase`).
3. Somente depois execute a configuracao da tarefa do passo 5.

## 5. Configurar para iniciar com o Windows (opcional)

Com PowerShell em modo Administrador:

```powershell
$taskName = "MonitorTCC_Agent"
$exeTarget = "C:\MonitorTCC\agent_monitor_tcc.exe"

$action = New-ScheduledTaskAction -Execute $exeTarget -Argument "--interval 300 --duration 0 --phase post --salt TCC2026 --outdir C:\MonitorTCC\data"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Start-ScheduledTask -TaskName $taskName
```

Este bloco cria a tarefa sem restricao de bateria, executa no boot, inicia imediatamente e aplica retry no agendador (ate 3 reinicios, 1 minuto entre tentativas).

### Verificacao apos agendamento:

Confirme que a tarefa foi criada e esta em execucao:

```powershell
# Verificar se a tarefa existe e seu status
Get-ScheduledTask -TaskName "MonitorTCC_Agent" | Select-Object TaskName,State,LastRunTime,NextRunTime

# Verificar se o processo esta rodando
Get-Process | Where-Object { $_.ProcessName -eq "agent_monitor_tcc" }

# Verificar se o CSV foi criado
Get-ChildItem -Path "C:\MonitorTCC\data" -File | Select-Object Name,Length,LastWriteTime
```

## 6. Parar agente baseline (se estiver em execucao)

Caso o agente baseline esteja rodando como tarefa agendada, e voce queira migrar para o cenario post, e necessario parar o processo anterior.

PowerShell (Administrador):

```powershell
Write-Host "Parando agente baseline se estiver em execucao..."

# Para o processo agent_monitor_tcc (baseline)
Stop-Process -Name "agent_monitor_tcc" -ErrorAction SilentlyContinue
Write-Host "Processo baseline parado."

# Para a tarefa agendada baseline (se existir)
Stop-ScheduledTask -TaskName "MonitorTCC_Agent" -ErrorAction SilentlyContinue
Write-Host "Tarefa baseline parada."

# Aguarda um momento para garantir parada
Start-Sleep -Seconds 2
Write-Host "Pronto para passar para o cenario post."
```

## 7. Aplicar politicas de energia via linha de comando (POST)

As politicas de energia podem ser aplicadas por comando antes de registrar a tarefa do agente post.

PowerShell (Administrador):

```powershell
# Politicas para energia na tomada (AC)
powercfg /change monitor-timeout-ac 15
powercfg /change standby-timeout-ac 30
powercfg /change hibernate-timeout-ac 60
powercfg /change disk-timeout-ac 20

# Politicas para bateria (DC) - ajustar conforme necessidade institucional
powercfg /change monitor-timeout-dc 10
powercfg /change standby-timeout-dc 20
powercfg /change hibernate-timeout-dc 30
powercfg /change disk-timeout-dc 10
```

### Verificacao das politicas aplicadas:

Confirme que as politicas foram aplicadas corretamente:

```powershell
# Mostrar as politicas de energia ativas do plano atual
powercfg /query

# Alternativamente, mostrar apenas os timeouts de forma resumida
powercfg /query | Select-String "(monitor|standby|hibernate|disk)"
```

## 8. Script unico (parada + politicas + agendamento do agente POST)

Se quiser executar tudo de uma vez (recomendado):

```powershell
$taskName = "MonitorTCC_Agent"
$exeTarget = "C:\MonitorTCC\agent_monitor_tcc.exe"

# 0) Parar agente baseline se estiver em execucao
Write-Host "[0/5] Parando agente baseline..."
Stop-Process -Name "agent_monitor_tcc" -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host "[0/5] Agente baseline parado." `n

# 1) Aplicar politicas de energia
Write-Host "[1/5] Aplicando politicas de energia..."
powercfg /change monitor-timeout-ac 15
powercfg /change standby-timeout-ac 30
powercfg /change hibernate-timeout-ac 60
powercfg /change disk-timeout-ac 20
powercfg /change monitor-timeout-dc 10
powercfg /change standby-timeout-dc 20
powercfg /change hibernate-timeout-dc 30
powercfg /change disk-timeout-dc 10
Write-Host "[1/5] Politicas aplicadas. Verificando..." `n
powercfg /query | Select-String "(monitor|standby|hibernate|disk)"
Write-Host "`n"

# 2) Agendar agente em modo POST
Write-Host "[2/5] Registrando tarefa agendada..."
$action = New-ScheduledTaskAction -Execute $exeTarget -Argument "--interval 300 --duration 0 --phase post --salt TCC2026 --outdir C:\MonitorTCC\data"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Write-Host "[2/5] Tarefa registrada. Verificando..." `n
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
Write-Host "`n"

# 3) Iniciar tarefa imediatamente
Write-Host "[3/5] Iniciando agente..."
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
Write-Host "[3/5] Verificando se agente esta em execucao..." `n
Get-Process | Where-Object { $_.ProcessName -eq "agent_monitor_tcc" } | Select-Object ProcessName,Id,StartTime
Write-Host "`n"

# 4) Verificar saida do agente
Write-Host "[4/5] Verificando arquivo de saida..." `n
Get-ChildItem -Path "C:\MonitorTCC\data" -File | Select-Object Name,Length,LastWriteTime
Write-Host "`n"

# 5) Confirmacao final
Write-Host "[5/5] Setup concluido!"
Write-Host "Agente POST esta em execucao. Verifique o arquivo de saida em C:\MonitorTCC\data"
```