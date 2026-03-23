# -*- coding: utf-8 -*-
"""Dashboard Streamlit (v2) – Consumo × Carga × Horas

Este dashboard complementa o TCC permitindo demonstrar, na prática:
- correlação entre consumo e desempenho (carga efetiva)
- relação horas de uso × consumo × desempenho
- trade-off energia–desempenho

Execução:
  streamlit run dashboard_monitor_tcc_v2.py
"""

import os
import io
import datetime as dt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------
# Configuração da página
# -----------------------------

st.set_page_config(page_title='Dashboard – Consumo × Carga', page_icon=':bar_chart:', layout='wide')
st.title('📊 Consumo × Carga × Horas (TCC)')

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

def list_csvs(root: str):
    if not os.path.isdir(root):
        return []
    return [os.path.join(root, f) for f in os.listdir(root) if f.lower().endswith('.csv')]

def summarize(df: pd.DataFrame, filename: str):
    host_id = df['host_id'].iloc[0] if 'host_id' in df.columns and not df.empty else 'desconhecido'
    phase = df['phase'].iloc[0] if 'phase' in df.columns and not df.empty else ''

    if 'timestamp_utc' in df.columns and df['timestamp_utc'].notna().any():
        total_hours = (df['timestamp_utc'].max() - df['timestamp_utc'].min()).total_seconds() / 3600.0
    elif 'interval_s' in df.columns:
        total_hours = df['interval_s'].sum() / 3600.0
    else:
        total_hours = float('nan')

    if 'active_flag' in df.columns and 'interval_s' in df.columns:
        active_hours = df.loc[df['active_flag'] == 1, 'interval_s'].sum() / 3600.0
    else:
        active_hours = float('nan')

    if 'energy_Wh_est' in df.columns:
        energy_kWh = df['energy_Wh_est'].sum() / 1000.0
    elif 'energy_kWh_cum' in df.columns and not df.empty:
        energy_kWh = df['energy_kWh_cum'].max()
    else:
        energy_kWh = float('nan')

    mean_load = df['load_effective'].mean() if 'load_effective' in df.columns else float('nan')
    p95_load = df['load_effective'].quantile(0.95) if 'load_effective' in df.columns else float('nan')

    return {
        'arquivo': os.path.basename(filename),
        'host_id': host_id,
        'phase': phase,
        'total_hours': total_hours,
        'active_hours': active_hours,
        'energy_kWh_est': energy_kWh,
        'mean_load': mean_load,
        'p95_load': p95_load,
        'df': df
    }

def download_df(df: pd.DataFrame, filename: str, label: str):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button(label, buf.getvalue(), file_name=filename, mime='text/csv')

def scatter_with_fit(x, y, xname, yname, title):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x2, y2 = x[mask], y[mask]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x2, y=y2, mode='markers', name='observações'))
    if len(x2) >= 2:
        m, b = np.polyfit(x2, y2, 1)
        xs = np.linspace(x2.min(), x2.max(), 50)
        ys = m*xs + b
        fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', name='tendência (OLS)'))
        fig.update_layout(title=f"{title} | inclinação={m:.4f}")
    else:
        fig.update_layout(title=title)
    fig.update_layout(xaxis_title=xname, yaxis_title=yname)
    return fig

# -----------------------------
# Sidebar – seleção de diretório/arquivos
# -----------------------------

st.sidebar.header('📁 Fonte de dados')
root = st.sidebar.text_input('Diretório com CSVs', value=os.path.join(os.path.abspath('.'), 'data'))

files = list_csvs(root)
if not files:
    st.warning('Nenhum CSV encontrado. Gere dados com o agente v2 ou ajuste o caminho.')
    st.stop()

selected = st.sidebar.multiselect('Selecione arquivos', options=files, default=files[:min(10, len(files))])
if not selected:
    st.stop()

# -----------------------------
# Carga dos arquivos
# -----------------------------

summaries = [summarize(load_csv(f), f) for f in selected]
summary_df = pd.DataFrame([{k:v for k,v in s.items() if k != 'df'} for s in summaries])

st.subheader('📌 Sumário por arquivo')
st.dataframe(summary_df, use_container_width=True)
download_df(summary_df, 'sumario_consumo_carga.csv', '⬇️ Baixar sumário')

# -----------------------------
# Correlações
# -----------------------------

st.subheader('🔗 Correlações (por arquivo)')
cols = ['energy_kWh_est','mean_load','p95_load','total_hours','active_hours']
pear = summary_df[cols].corr(method='pearson')
spear = summary_df[cols].corr(method='spearman')

c1, c2 = st.columns(2)
with c1:
    st.markdown('**Pearson**')
    st.plotly_chart(px.imshow(pear, text_auto=True, aspect='auto'), use_container_width=True)
with c2:
    st.markdown('**Spearman**')
    st.plotly_chart(px.imshow(spear, text_auto=True, aspect='auto'), use_container_width=True)

# -----------------------------
# Dispersões
# -----------------------------

st.subheader('📉 Dispersões e trade-off')
fig1 = scatter_with_fit(summary_df['mean_load'], summary_df['energy_kWh_est'],
                        'Carga efetiva média (0–1)', 'Energia estimada (kWh)', 'Energia × Carga')
fig2 = scatter_with_fit(summary_df['active_hours'], summary_df['energy_kWh_est'],
                        'Horas de uso (h)', 'Energia estimada (kWh)', 'Energia × Horas de uso')
fig3 = scatter_with_fit(summary_df['active_hours'], summary_df['mean_load'],
                        'Horas de uso (h)', 'Carga efetiva média (0–1)', 'Carga × Horas de uso')

r1, r2 = st.columns(2)
with r1:
    st.plotly_chart(fig1, use_container_width=True)
    st.plotly_chart(fig2, use_container_width=True)
with r2:
    st.plotly_chart(fig3, use_container_width=True)

# -----------------------------
# Séries temporais (opcional)
# -----------------------------

with st.expander('⏱️ Ver séries temporais (amostras)'):
    combined = pd.concat([s['df'].assign(__file=s['arquivo']) for s in summaries], ignore_index=True)
    if 'timestamp_utc' in combined.columns:
        xcol = 'timestamp_utc'
    else:
        combined = combined.reset_index().rename(columns={'index':'amostra'})
        xcol = 'amostra'

    pct_cols = [c for c in ['cpu (%)','ram (%)','mem_available (%)','swap (%)'] if c in combined.columns]
    if pct_cols:
        st.plotly_chart(px.line(combined, x=xcol, y=pct_cols, color='__file', title='Percentuais'), use_container_width=True)
    extra_cols = [c for c in ['load_effective','power_w_est','energy_kWh_cum'] if c in combined.columns]
    if extra_cols:
        st.plotly_chart(px.line(combined, x=xcol, y=extra_cols, color='__file', title='Carga/Consumo'), use_container_width=True)

st.caption(f"© {dt.datetime.now().year} – Dashboard v2")
