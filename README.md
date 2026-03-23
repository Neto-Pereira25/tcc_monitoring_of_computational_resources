# Green IT Monitor – Agente & Dashboard (TCC IFPE)
>
> **Projeto atualizado**: agora existem **duas versões do agente e do dashboard**.
> A versão **v2** adiciona métricas de **carga efetiva (desempenho como uso real)**,
> **horas de uso** e **estimativa de consumo energético**, permitindo análises de
> **correlação consumo × carga × horas** e discussão do **trade-off energia–desempenho**.

---

## 🔎 Visão geral
O projeto é composto por **dois componentes principais**:

1. **Agente de Coleta** (`agent_monitor_tcc.py`)
   - Coleta **CPU** (média de 1s), **RAM**, **memória disponível**, **SWAP**;
   - Calcula **taxas de disco** (B/s) e **latência média** (ms/op) por **delta de contadores**;
   - Gera **CSV por host** com `timestamp_utc` e **host pseudonimizado** (`host_id` – LGPD);
   - Parâmetros CLI: `--interval`, `--duration`, `--outdir`, `--salt`.
   - Define **desempenho como carga efetiva (uso real)**:
     - `load_cpu`, `load_ram`, `load_disk`, `load_effective`;
   - Registra **tempo real entre coletas** (`interval_s`);
   - Identifica **uso ativo** (`active_flag`);
   - Estima **consumo energético**:
     - `power_w_est`, `energy_Wh_est`, `energy_kWh_cum`;
   - Diferencia **fase experimental** (`baseline` ou `post`);
   - Parâmetros adicionais:
     - `--phase` (`baseline|post`)
     - `--p-idle`, `--p-active`
     - `--w-cpu`, `--w-ram`, `--w-disk`
     - `--disk-norm-mbps`
     - `--active-threshold`

2. **Dashboard de Análise** (`dashboard_monitor_tcc.py`)
   - Séries temporais de CPU/RAM/SWAP/mem_available e disco;
   - Estatísticas (`mean`, `p50`, `p75`, `p95`);
   - Classificação de hosts (subutilizado / adequado / sobrecarregado).
   - Sumário por arquivo: carga média/p95, horas de uso e energia (kWh);
   - **Correlação Pearson e Spearman**:
     - consumo × carga efetiva
     - consumo × horas de uso
     - carga efetiva × horas de uso;
   - **Gráficos de dispersão** com linha de tendência (trade-off energia–desempenho).

---

## 🚀 Requisitos
- **Python 3.9+** (recomendado 3.10+)
- Bibliotecas: `psutil`, `pandas`, `plotly`, `streamlit`

```bash
pip install psutil pandas plotly streamlit
```

---

## 👷 Agente – execução

**Baseline (antes da intervenção):**
```bash
python agent_monitor_tcc_v2.py --interval 300 --duration 0 --phase baseline --outdir data
```

**Pós-intervenção:**
```bash
python agent_monitor_tcc_v2.py --interval 300 --duration 0 --phase post --outdir data
```

> Pare com `Ctrl+C` (modo interativo).

---

## 📊 Dashboard – execução

```bash
streamlit run dashboard_monitor_tcc.py
```

---

## 🧪 Uso no TCC (fluxo recomendado)
1. Coletar **baseline** com agente (24–48h);
2. Aplicar políticas de energia (ENERGY STAR);
3. Coletar **pós-intervenção** com agente;
4. Analisar no dashboard:
   - carga efetiva,
   - horas de uso,
   - consumo (kWh);
5. Avaliar correlação e discutir o **trade-off energia–desempenho**.

---

## 📄 Licença
Definida pelo autor do TCC/repositório.
