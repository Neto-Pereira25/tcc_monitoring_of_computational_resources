# Green IT Monitor – Agente & Dashboard (TCC IFPE)

> Monitoramento leve de recursos de estações (CPU/RAM/SWAP/Disco) com **CSV por host** e **Dashboard Streamlit** para análise – desenhado para apoiar o TCC sobre **TI Verde / Green IS**.

## 🔎 Visão geral

Este projeto é composto por **dois componentes**:

1. **Agente de coleta** (`agent_monitor_tcc.py`)
   - Coleta **CPU** (média de 1s), **RAM**, **memória disponível**, **SWAP**;
   - Calcula **taxas de disco** (B/s) e **latência média** (ms/op) por **delta de contadores**;
   - Grava **CSV** com `timestamp_utc` e **pseudônimo do host** (`host_id`) – **LGPD-ready** (hash do hostname + SALT);
   - Parâmetros via CLI: `--interval`, `--duration`, `--outdir`, `--salt`.

2. **Dashboard de análise** (`dashboard_monitor_tcc.py`)
   - Lê um diretório com **arquivos CSV** do agente;
   - Exibe **séries temporais** (CPU/RAM/mem_available/SWAP; disco B/s e ms/op);
   - Calcula **média/p50/p75/p95** e **classifica** cada arquivo/host: *subutilizado / adequado / sobrecarregado*;
   - Permite **exportar** estatísticas e dados combinados (`.csv`).

> **Por que assim?**  
> - O agente usa `psutil.cpu_percent(interval=1.0)` para média real de CPU (~1s) e **deltas** de `disk_io_counters()` para transformar contadores cumulativos em **taxas por segundo** e **latência por operação** (métrica coerente entre *baseline* e *pós*).  
> - CSV + `timestamp_utc` viabiliza análises temporais; `host_id` atende **LGPD** sem perder rastreabilidade.

---

## 🧱 Arquitetura

```
Estações (ADM/LAB) ──> agent_monitor_tcc.py ──> data/YYYY_MM_DD_<host_id>.csv
                                                    │
                                                    ▼
                                         dashboard_monitor_tcc.py
```

---

## 🚀 Requisitos

- **Python 3.9+** (recomendado 3.10+)
- Bibliotecas: `psutil`, `pandas`, `plotly`, `streamlit`

Instalação rápida:

```bash
pip install psutil pandas plotly streamlit
```

---

## 👷 Agente – execução

Execução mínima (diretório `./data` por padrão):

```bash
# Windows (PowerShell)
$Env:AGENT_SALT = 'segredo_institucional_unico'
python agent_monitor_tcc.py --interval 300 --duration 0 --outdir data

# Linux/macOS
export AGENT_SALT='segredo_institucional_unico'
python3 agent_monitor_tcc.py --interval 300 --duration 0 --outdir data
```

### Parâmetros
- `--interval` (**segundos**) → período entre linhas no CSV (padrão `300`).  
  > Observação: dentro de cada ciclo o agente passa **~1s** medindo CPU para estabilizar a leitura.
- `--duration` (**segundos**) → duração total (use `0` para **contínuo**).
- `--outdir` → diretório de saída (padrão `data`).
- `--salt` → SALT para pseudonimização (ou defina `AGENT_SALT`).

### Esquema do CSV (colunas)

| coluna | descrição |
|---|---|
| `timestamp_utc` | data/hora (UTC, ISO‑8601) |
| `host_id` | pseudônimo do host (hash[hostname + SALT]) |
| `os`, `os_release` | sistema operacional e release |
| `cpu (%)` | uso médio no período de ~1s |
| `ram (%)` | uso de RAM |
| `mem_available (%)` | memória disponível / total |
| `swap (%)` | uso de SWAP |
| `disk_read_Bps`, `disk_write_Bps` | taxas de leitura/escrita (B/s) |
| `disk_ops_read`, `disk_ops_write` | operações de I/O no intervalo |
| `disk_avg_latency_ms` | latência média (ms/op) no intervalo |

> **LGPD:** o arquivo **não** contém o hostname; ele é preservado localmente e derivado em `host_id` (pseudônimo). Use um **SALT único** por instituição.

### Como parar o agente
- Execução **interativa**: pressione **`Ctrl+C`** (gera `KeyboardInterrupt`, o arquivo é fechado com segurança).
- Execução em **segundo plano**: encerre o processo (`taskkill` no Windows; `kill`/`pkill` no Linux).  
  *Dicas*: usar **Task Scheduler/Agendador** (Windows) ou **systemd** (Linux) para iniciar/parar por janela temporal.

---

## 📊 Dashboard – execução

```bash
streamlit run dashboard_monitor_tcc.py
```

- Na *sidebar*, informe o diretório com CSVs (padrão `./data`).
- Selecione múltiplos arquivos para análise.

### O que é exibido
- **Arquivos / Metadados**: `host_id`, SO e **classificação** do host (regras por p95 de CPU/RAM).  
  - *Subutilizado*: `p95_CPU < 30%` **e** `p95_RAM < 50%`  
  - *Sobrecarregado*: `p95_CPU ≥ 80%` **ou** `p95_RAM ≥ 85%`  
  - *Adequado*: demais casos
- **Séries temporais combinadas**: CPU, RAM, `mem_available`, SWAP; disco (**B/s**, **ms/op**) ao longo do **`timestamp_utc`**.
- **Estatísticas por arquivo**: `mean`, `p50`, `p75`, `p95` das métricas percentuais.
- **Correlação**: entre variáveis percentuais (CPU/RAM/mem_available/SWAP).
- **Exportações**: estatísticas por arquivo e dados combinados em `.csv`.

---

## 🧪 Como aplicar no TCC (baseline → intervenção → pós)

1. **Planeje as janelas**: colete **baseline** por 24–48h (ADM/LAB).  
2. **Aplique a intervenção**: políticas de energia (sleep/hibernação/desligamento), realocação de hosts etc.  
3. **Colete o pós**: novamente 24–48h nas mesmas máquinas.
4. **Analise no Dashboard**: selecione os CSVs das janelas e **exporte**:  
   - Estatísticas (p95 de CPU/RAM), **classificação** (sub/adequado/sobre);  
   - Séries e correlações para interpretar variações.
5. **Teste de hipóteses**:  
   - **H1 (Energia)**: converta kWh (medidos ou estimados) em CO₂e (fator oficial do SIN/MCTI);  
   - **H2 (Equilíbrio de carga)**: compare **proporções** de sub/sobreutilização **pré vs pós** (McNemar);  
   - **H3 (Conformidade)**: verifique adesão às políticas de TI Verde (sleep/hibernação etc.).
6. **Monte os artefatos do capítulo 4**: figuras (boxplots, linhas, barras) e tabelas (percentis, proporções, p‑valor, tamanho de efeito).

> Para energia: se não houver wattímetro/tomada inteligente, estime por **perfil de potência** (idle/ativo) × tempo no estado, e depois aplique o **fator de emissão** vigente para CO₂e.

---

## 🛠️ Dicas de implantação
- **Intervalo**: `--interval 300` (5 min) equilibra granularidade e overhead.
- **SALT**: defina **AGENT_SALT** diferente por instituição/campus (não versionar publicamente). 
- **Logs**: a periodicidade é previsível; problemas de permissão/caminho costumam ser a principal causa de falhas de escrita.

---

## ❓ FAQ
**1) Posso rodar contínuo?**  
Sim, use `--duration 0`. Pare com **Ctrl+C** (interativo) ou encerrando o processo.

**2) E se faltar `timestamp_utc`?**  
O dashboard usa o índice como fallback, mas as séries ficam menos interpretáveis. Prefira sempre o CSV gerado por esta versão do agente.

**3) O que é `mem_available (%)`?**  
Percentual de **memória disponível** (não “cache”); mede quanta RAM o sistema ainda pode usar.

**4) “Latência de disco” é acumulada?**  
Não. O agente calcula a **média por intervalo** usando **deltas** de contadores (ms/op).

---

## 📄 Licença
Definida pelo autor do TCC/repositório. (Sugestão: MIT ou CC BY-NC para materiais de texto.)

