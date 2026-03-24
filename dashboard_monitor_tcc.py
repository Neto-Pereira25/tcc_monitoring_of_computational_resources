# -*- coding: utf-8 -*-
"""Dashboard Streamlit (v3) – Consumo × Carga × Horas
Correções aplicadas:
- Mapa de correlação: escala de cores corrigida (azul escuro = +1)
- Removidos gráficos Energia×Tempo e Carga×Tempo (usavam interval_s fixo)
- Séries temporais separadas em 3 gráficos distintos por escala
- Aviso automático quando amostra é pequena (< 30 linhas)
- Títulos e descrições explicativas em cada seção
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
# Configuração
# -----------------------------
st.set_page_config(
    page_title='Dashboard TCC – Green IT',
    page_icon='🌱',
    layout='wide'
)
st.title('🌱 Green IT Monitor – Consumo × Carga × Horas')
st.caption('Dashboard v3 – TCC IFPE')

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
    fig.add_trace(go.Scatter(
        x=x2, y=y2, mode='markers', name='observações',
        marker=dict(size=8, opacity=0.7)
    ))

    if len(x2) >= 2:
        m, b = np.polyfit(x2, y2, 1)
        xs = np.linspace(x2.min(), x2.max(), 50)
        ys = m * xs + b
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode='lines', name='tendência linear',
            line=dict(width=2, dash='dash')
        ))

    fig.update_layout(
        title=title,
        xaxis_title=xname,
        yaxis_title=yname,
        legend=dict(orientation='h', y=-0.2)
    )
    return fig

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.header('📁 Fonte de dados')
root = st.sidebar.text_input(
    'Diretório com CSVs',
    value=os.path.join(os.path.abspath('.'), 'data')
)

files = list_csvs(root)
if not files:
    st.warning('Nenhum CSV encontrado.')
    st.stop()

selected = st.sidebar.multiselect(
    'Selecione arquivos',
    options=files,
    default=files[:min(5, len(files))]
)
if not selected:
    st.stop()

# -----------------------------
# Carregar dados
# -----------------------------
dfs = [load_csv(f).assign(__file=os.path.basename(f)) for f in selected]
combined = pd.concat(dfs, ignore_index=True)
if 'interval_s' in combined.columns:
    combined = combined[combined['interval_s'] > 10]
if 'timestamp_utc' in combined.columns:
    combined = combined.sort_values('timestamp_utc')

# -----------------------------
# AVISO DE AMOSTRA PEQUENA
# CORRIGIDO: antes não existia esse aviso.
# Com poucos dados, a correlação fica matematicamente instável —
# um único ponto fora do padrão distorce todo o resultado.
# Agora o dashboard avisa quando há menos de 30 amostras.
# -----------------------------
MIN_AMOSTRAS = 30
total_amostras = len(combined)

if total_amostras < MIN_AMOSTRAS:
    st.warning(
        f'⚠️ **Amostra pequena:** {total_amostras} leituras encontradas. '
        f'Para resultados confiáveis, colete pelo menos {MIN_AMOSTRAS} amostras '
        f'(≈ {MIN_AMOSTRAS * 5 // 60}h com --interval 300). '
        f'Correlações e dispersões podem estar distorcidas.'
    )

# -----------------------------
# SUMÁRIO
# -----------------------------
st.subheader('📌 Sumário por arquivo')
st.caption('Carga média: < 0.20 = ociosa  |  0.20–0.70 = adequada  |  > 0.70 = sobrecarregada')

summary = []
for df, f in zip(dfs, selected):
    load_mean = df['load_effective'].mean() if 'load_effective' in df.columns else None
    energy = df['energy_Wh_est'].sum() / 1000 if 'energy_Wh_est' in df.columns else None

    if load_mean is not None:
        if load_mean < 0.20:
            status = '🟡  Subutilizada'
        elif load_mean <= 0.70:
            status = '🟢 Adequada'
        else:
            status = '🔴 Sobrecarga'
    else:
        status = '—'

    summary.append({
        'arquivo': os.path.basename(f),
        'amostras': len(df),
        'carga_média': round(load_mean, 3) if load_mean is not None else '—',
        'energy_kWh': round(energy, 6) if energy is not None else '—',
        'status': status,
    })

summary_df = pd.DataFrame(summary)
st.dataframe(summary_df, use_container_width=True)
download_df(summary_df, 'sumario.csv', '⬇️ Baixar sumário')

# -----------------------------
# CORRELAÇÃO
# CORRIGIDO: antes usava px.imshow sem color_continuous_scale definido.
# O Plotly escolhia a escala automaticamente, e com valor negativo
# (-0.55) o azul escuro ficava no lado NEGATIVO — visualmente errado.
# Agora usa color_continuous_scale='RdBu' com zmin=-1 e zmax=1:
#   Azul escuro = +1 (correlação positiva forte) ← correto
#   Branco      =  0 (sem correlação)
#   Vermelho    = -1 (correlação negativa)
# Esse é o padrão usado em artigos científicos e TCCs.
# Também adicionei interpretação textual automática do valor.
# -----------------------------
st.subheader('🔗 Correlação: carga efetiva × energia')
st.caption(
    'Espera-se correlação positiva: máquinas mais carregadas tendem a consumir mais energia. '
    'Valores próximos de +1 indicam forte relação entre carga e consumo.'
)

cols_corr = ['load_effective', 'energy_Wh_est']

if all(c in combined.columns for c in cols_corr):
    corr = combined[cols_corr].corr()
    r = corr.loc['load_effective', 'energy_Wh_est']

    a = abs(r)
    sinal = 'positiva' if r > 0 else 'negativa'
    forca = 'forte' if a >= 0.7 else ('moderada' if a >= 0.4 else 'fraca')

    if r >= 0.7:
        st.success(f'Correlação {forca} e {sinal}: **{r:.4f}** ✅ Resultado esperado.')
    elif r >= 0.4:
        st.info(f'Correlação {forca} e {sinal}: **{r:.4f}** — Aceitável, colete mais dados.')
    else:
        st.warning(
            f'Correlação {forca} e {sinal}: **{r:.4f}** — '
            f'Amostra insuficiente ou padrão atípico.'
        )

    fig_corr = px.imshow(
        corr,
        text_auto='.3f',
        color_continuous_scale='RdBu',  # CORRIGIDO: padrão científico
        zmin=-1,                         # CORRIGIDO: escala fixa -1 a +1
        zmax=1,
        title='Matriz de correlação (Pearson)',
    )
    fig_corr.update_layout(coloraxis_colorbar=dict(title='r'))
    st.plotly_chart(fig_corr, use_container_width=True, key='corr_heatmap')

# -----------------------------
# DISPERSÃO
# CORRIGIDO: antes havia 3 gráficos de dispersão.
# Os 2 últimos (Energia×Tempo e Carga×Tempo) usavam 'interval_s'
# no eixo X. O problema: interval_s é quase sempre 300s (fixo),
# então todos os pontos ficavam empilhados em X=0 e X=300,
# sem mostrar nada útil — apenas um artefato do agente.
# Esses 2 gráficos foram REMOVIDOS.
# Mantido apenas Energia×Carga, que é o único com sentido analítico:
# mostra o trade-off energia × desempenho, central para o TCC.
# -----------------------------
st.subheader('📉 Dispersão: Energia × Carga efetiva')
st.caption(
    'Cada ponto = uma leitura do agente. '
    'A linha de tendência deve subir da esquerda para a direita: '
    'mais carga → mais energia. Isso é o trade-off energia × desempenho.'
)

if 'load_effective' in combined.columns and 'energy_Wh_est' in combined.columns:
    fig1 = scatter_with_fit(
        combined['load_effective'],
        combined['energy_Wh_est'],
        'Carga efetiva (0 = ociosa, 1 = no limite)',
        'Energia por intervalo (Wh)',
        f'Energia × Carga  |  n = {total_amostras} amostras'
    )
    st.plotly_chart(fig1, use_container_width=True, key='disp_carga')

# -----------------------------
# SÉRIES TEMPORAIS
# CORRIGIDO: antes havia 2 gráficos, mas cada um misturava métricas
# com escalas completamente diferentes no mesmo eixo Y:
#   - cpu(%) e ram(%) → escala 0–100
#   - load_effective  → escala 0–1
#   - power_w_est     → escala 0–120 W
# Com tudo junto, load_effective e power_w_est "sumiam" perto do zero
# porque a escala era dominada pelos valores de RAM (70–80%).
# Agora separado em 3 gráficos independentes, cada um com sua escala.
# -----------------------------
st.subheader('⏱️ Séries temporais')

if 'timestamp_utc' in combined.columns:
    xcol = 'timestamp_utc'
else:
    combined = combined.reset_index().rename(columns={'index': 'amostra'})
    xcol = 'amostra'

# Gráfico 1: CPU e RAM (%)
pct_cols = [c for c in ['cpu (%)', 'ram (%)'] if c in combined.columns]
if pct_cols:
    st.markdown('**CPU e RAM ao longo do tempo**')
    st.caption('Picos de CPU = processamento intenso. RAM alta e constante = muita coisa aberta na memória.')
    fig_pct = px.line(
        combined, x=xcol, y=pct_cols, color='__file',
        labels={'value': 'Percentual (%)', 'variable': 'Métrica'},
        title='CPU (%) e RAM (%) — escala 0 a 100%'
    )
    fig_pct.update_layout(yaxis_range=[0, 100])
    st.plotly_chart(fig_pct, use_container_width=True, key='series_pct')

# Gráfico 2: Carga efetiva (0–1)
if 'load_effective' in combined.columns:
    st.markdown('**Carga efetiva ao longo do tempo**')
    st.caption('0 = ociosa. 1 = no limite. Entre 0.20 e 0.70 = uso adequado.')
    fig_load = px.line(
        combined, x=xcol, y='load_effective', color='__file',
        labels={'load_effective': 'Carga efetiva (0–1)'},
        title='Carga efetiva — escala 0 a 1'
    )
    fig_load.update_layout(yaxis_range=[0, 1])
    st.plotly_chart(fig_load, use_container_width=True, key='series_load')

# Gráfico 3: Potência estimada (W)
if 'power_w_est' in combined.columns:
    st.markdown('**Potência estimada ao longo do tempo**')
    st.caption('Segue a carga efetiva. Confirma visualmente o modelo de estimativa de consumo.')
    fig_power = px.line(
        combined, x=xcol, y='power_w_est', color='__file',
        labels={'power_w_est': 'Potência estimada (W)'},
        title='Potência estimada (W)'
    )
    st.plotly_chart(fig_power, use_container_width=True, key='series_power')

st.caption(f"© {dt.datetime.now().year} – Dashboard TCC v3 (modo real)")