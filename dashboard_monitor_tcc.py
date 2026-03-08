# -*- coding: utf-8 -*-
"""
Dashboard Streamlit para análise dos CSVs do agente (versão refatorada)
- Lê CSVs do diretório selecionado
- Faz parse de timestamp_utc e ordena
- Exibe séries temporais (CPU/RAM/mem_available/SWAP e disco)
- Calcula estatísticas (média, p50/p75/p95) por arquivo e por conjunto
- Classifica hosts (pré/pós) usando regras do TCC: 
  * subutilizado: p95_CPU < 30% e p95_RAM < 50%
  * sobrecarregado: p95_CPU >= 80% ou p95_RAM >= 85%
- Exporta sumários em CSV (download)

Como executar:
    streamlit run dashboard_monitor_tcc.py
"""

import os
import io
import platform
import datetime as dt
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st

# -----------------------------
# Configuração da página
# -----------------------------
st.set_page_config(
    page_title='Dashboard Monitoramento TCC',
    page_icon=':bar_chart:',
    layout='wide',
    initial_sidebar_state='expanded'
)

st.title('📊 Dashboard de Monitoramento – TCC')
st.write('Analise os CSVs gerados pelo agente de coleta (versão refatorada).')

# -----------------------------
# Helpers
# -----------------------------

@st.cache_data(show_spinner=False)
def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if 'timestamp_utc' in df.columns:
        df['timestamp_utc'] = pd.to_datetime(df['timestamp_utc'], utc=True, errors='coerce')
        df = df.sort_values('timestamp_utc').reset_index(drop=True)
    return df


def list_csvs(root: str) -> list:
    if not os.path.isdir(root):
        return []
    return [os.path.join(root, f) for f in os.listdir(root) if f.lower().endswith('.csv')]


def compute_basic_stats(df: pd.DataFrame) -> pd.DataFrame:
    cols_pct = [c for c in df.columns if c.lower() in ['cpu (%)', 'ram (%)', 'mem_available (%)', 'swap (%)']]
    if not cols_pct:
        return pd.DataFrame()
    res = pd.DataFrame({
        'mean': df[cols_pct].mean(),
        'p50': df[cols_pct].quantile(0.50),
        'p75': df[cols_pct].quantile(0.75),
        'p95': df[cols_pct].quantile(0.95)
    })
    return res


def classify_host(df: pd.DataFrame) -> str:
    # Regras do TCC baseadas em p95 de CPU/RAM
    if not set(['cpu (%)', 'ram (%)']).issubset(df.columns):
        return 'indefinido'
    p95_cpu = df['cpu (%)'].quantile(0.95)
    p95_ram = df['ram (%)'].quantile(0.95)
    if (p95_cpu < 30) and (p95_ram < 50):
        return 'subutilizado'
    if (p95_cpu >= 80) or (p95_ram >= 85):
        return 'sobrecarregado'
    return 'adequado'


def summarize_file(path: str) -> dict:
    df = load_csv(path)
    label = os.path.basename(path)
    host_id = df['host_id'].iloc[0] if 'host_id' in df.columns and not df.empty else 'desconhecido'
    os_name = df['os'].iloc[0] if 'os' in df.columns and not df.empty else ''
    os_rel  = df['os_release'].iloc[0] if 'os_release' in df.columns and not df.empty else ''
    cls = classify_host(df) if not df.empty else 'indefinido'
    stats = compute_basic_stats(df)
    return {
        'arquivo': label,
        'host_id': host_id,
        'os': os_name,
        'os_release': os_rel,
        'classificacao': cls,
        'stats': stats,
        'df': df
    }


def to_downloadable_csv(df: pd.DataFrame, filename: str, label: str):
    buf = io.StringIO()
    df.to_csv(buf, index=True)
    st.download_button(label=label, data=buf.getvalue(), file_name=filename, mime='text/csv')


# -----------------------------
# Sidebar – seleção de diretório/arquivos
# -----------------------------

st.sidebar.header('📁 Fonte de dados')
root_default = os.path.join(os.path.abspath('.'), 'data')
root = st.sidebar.text_input('Diretório com CSVs', value=root_default)

csvs = list_csvs(root)
if not csvs:
    st.warning('Nenhum CSV encontrado no diretório informado. Gere dados com o agente ou selecione outro caminho.')
    st.stop()

choices = st.sidebar.multiselect('Selecione os arquivos para análise', options=csvs, default=csvs[:min(5, len(csvs))])
if not choices:
    st.info('Selecione pelo menos um arquivo.')
    st.stop()

# -----------------------------
# Carga dos arquivos
# -----------------------------

summaries = [summarize_file(p) for p in choices]

# Tabela de cabeçalho (host, SO, classificação)
head_rows = []
for s in summaries:
    head_rows.append({
        'arquivo': s['arquivo'],
        'host_id': s['host_id'],
        'os': s['os'],
        'os_release': s['os_release'],
        'classificacao': s['classificacao']
    })
head_df = pd.DataFrame(head_rows)

st.subheader('📄 Arquivos / Metadados')
st.dataframe(head_df, use_container_width=True)

# -----------------------------
# Séries temporais combinadas
# -----------------------------

st.subheader('⏱️ Séries Temporais (combinadas)')

combined = pd.concat([s['df'].assign(__file=s['arquivo']) for s in summaries], ignore_index=True)

if 'timestamp_utc' in combined.columns:
    xcol = 'timestamp_utc'
else:
    combined = combined.reset_index().rename(columns={'index': 'amostra'})
    xcol = 'amostra'

cols_pct = [c for c in combined.columns if c.lower() in ['cpu (%)','ram (%)','mem_available (%)','swap (%)']]
if cols_pct:
    st.markdown('**CPU / RAM / Mem Available / SWAP**')
    fig_pct = px.line(combined, x=xcol, y=cols_pct, color='__file', title='Percentuais (por arquivo)')
    st.plotly_chart(fig_pct, use_container_width=True)

cols_disk = [c for c in ['disk_read_Bps','disk_write_Bps','disk_avg_latency_ms'] if c in combined.columns]
if cols_disk:
    st.markdown('**Disco – Taxas e Latência**')
    fig_dsk = px.line(combined, x=xcol, y=cols_disk, color='__file', title='Disco (B/s e ms/op)')
    st.plotly_chart(fig_dsk, use_container_width=True)

# -----------------------------
# Estatísticas por arquivo (média, p50/p75/p95) + download
# -----------------------------

st.subheader('📈 Estatísticas por arquivo')

stat_tables = []
for s in summaries:
    if s['stats'] is None or s['stats'].empty:
        continue
    tbl = s['stats'].copy()
    tbl.index.name = 'métrica'
    tbl.reset_index(inplace=True)
    tbl.insert(0, 'arquivo', s['arquivo'])
    tbl.insert(1, 'host_id', s['host_id'])
    tbl.insert(2, 'classificacao', s['classificacao'])
    stat_tables.append(tbl)

if stat_tables:
    stats_all = pd.concat(stat_tables, ignore_index=True)
    st.dataframe(stats_all, use_container_width=True)
    to_downloadable_csv(stats_all, 'estatisticas_por_arquivo.csv', '⬇️ Baixar estatísticas por arquivo')
else:
    st.info('Sem estatísticas disponíveis para as colunas de percentual.')

# -----------------------------
# Correlação (apenas percentuais para evitar interpretação equivocada)
# -----------------------------

st.subheader('🔗 Correlação entre percentuais')
if cols_pct:
    corr = combined[cols_pct].corr()
    st.plotly_chart(px.imshow(corr, text_auto=True, aspect='auto', title='Correlação'), use_container_width=True)
else:
    st.info('Não há colunas percentuais suficientes para correlação.')

# -----------------------------
# Export do combinado (opcional)
# -----------------------------

with st.expander('⬇️ Exportar dados combinados (CSV)'):
    to_downloadable_csv(combined, 'dados_combinados.csv', 'Baixar CSV combinado')

st.caption(f"© {dt.datetime.now().year} – Versão refatorada para o TCC")
