import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import difflib

# URLs de Google Sheets para ambas plantas
URL_GS_RT_FAMMA = "https://docs.google.com/spreadsheets/d/1l6a6ab82p_Nm0g0RdprVR7AWSvMgYjRp-16M1210hMU/edit?resourcekey=&gid=1779842834#gid=1779842834"
URL_GS_RT_FUMISCOR = "https://docs.google.com/spreadsheets/d/1pyVCOSGtypIW-4eW1HEFXSdICybNgtPFGtRKb4bsyDI/edit?resourcekey=&gid=1999259605#gid=1999259605"
URL_GS_H = "https://docs.google.com/spreadsheets/d/1mLnIC8B7mwmFZwthO0A32H3ZFfXSKt7vIUMBXEZxDJ0/edit?gid=0#gid=0"

MESES_MAP = {1:'ENERO', 2:'FEBRERO', 3:'MARZO', 4:'ABRIL', 5:'MAYO', 6:'JUNIO', 
             7:'JULIO', 8:'AGOSTO', 9:'SEPTIEMBRE', 10:'OCTUBRE', 11:'NOVIEMBRE', 12:'DICIEMBRE'}
MESES_REVERSE_MAP = {v: k for k, v in MESES_MAP.items()}

# Configuración de página
st.set_page_config(page_title="Panel de Calidad", layout="wide")

# Estilos CSS - Modo Oscuro
st.markdown("""
<style>
    .stApp { background-color: #0F172A !important; color: #F8FAFC !important; }
    .header-style { font-size: 28px; font-weight: bold; color: #F8FAFC; margin-bottom: 10px; }
    .sub-header { font-size: 20px; font-weight: bold; color: #38BDF8; margin-top: 15px; margin-bottom: 10px; text-transform: uppercase; }
    hr { border-color: #334155 !important; margin-top: 1rem; margin-bottom: 1rem; }
    div[data-testid="stVerticalBlockBorderWrapper"] { background-color: #1E293B !important; border: 1px solid #334155 !important; border-radius: 8px; }
    div[data-testid="stButton"] button { background-color: #1E293B !important; color: #F8FAFC !important; border: 1px solid #38BDF8 !important; font-weight: bold !important; border-radius: 6px !important; }
    div[data-testid="stButton"] button:hover { background-color: #0284C7 !important; border-color: #38BDF8 !important; }
    label, .stMarkdown p, .stText, span { color: #F8FAFC !important; }
    div[data-testid="stRadio"] > div { background-color: #1E293B !important; padding: 10px !important; border-radius: 8px !important; border: 1px solid #334155 !important; }
    div[role="radiogroup"] label div p { color: #F8FAFC !important; font-weight: 700 !important; font-size: 15px !important; }
    div[data-baseweb="select"] > div { background-color: #1E293B !important; color: #F8FAFC !important; border-color: #334155 !important; }
    ul[data-baseweb="menu"] { background-color: #1E293B !important; border: 1px solid #334155 !important; }
    li[data-baseweb="option"] { color: #F8FAFC !important; background-color: #1E293B !important; }
    li[data-baseweb="option"]:hover, li[data-baseweb="option"][aria-selected="true"] { background-color: #334155 !important; color: #38BDF8 !important; }
</style>
""", unsafe_allow_html=True)

# Tablas HTML
def render_dark_table(df):
    df_reset = df.reset_index()
    df_reset.rename(columns={'index': ''}, inplace=True)
    html = '<table style="width:100%; border-collapse: collapse; border: 1px solid #475569; font-family: Arial, sans-serif; font-size: 13px; color: #F8FAFC;">'
    html += '<tr style="background-color: #334155; font-weight: bold;">'
    for col in df_reset.columns: html += f'<th style="border: 1px solid #475569; padding: 8px; text-align: center;">{col}</th>'
    html += '</tr>'
    for _, row in df_reset.iterrows():
        is_bold = "font-weight: bold;" if row.iloc[0] in ['TOTAL PIEZAS', 'TOTAL SCRAP', '% SCRAP', 'TOTAL RT', '% RT', 'TOTAL'] else ""
        bg_color = "background-color: #F59E0B; color: #000000;" if row.iloc[0] in ['% SCRAP', '% RT', 'TOTAL'] else "background-color: #1E293B; color: #F8FAFC;"
        html += f'<tr style="{is_bold} {bg_color}">'
        for val in row: html += f'<td style="border: 1px solid #475569; padding: 6px; text-align: center;">{val}</td>'
        html += '</tr>'
    html += '</table><br>'
    st.markdown(html, unsafe_allow_html=True)

def unificar_codigos_similares(df):
    if df.empty or 'Código' not in df.columns: return df
    unique_codes = sorted(df['Código'].dropna().unique(), key=len)
    mapping = {}
    for i, base in enumerate(unique_codes):
        if base not in mapping:
            mapping[base] = base
            for other in unique_codes[i+1:]:
                if other not in mapping:
                    ratio = difflib.SequenceMatcher(None, base.upper(), other.upper()).ratio()
                    if ratio >= 0.90 or (base.upper() in other.upper() and len(base) > 5):
                        mapping[other] = base
    df['Código'] = df['Código'].map(mapping).fillna(df['Código'])
    return df

@st.cache_data(ttl=3600)
def fetch_piezas_h(gs_url):
    try:
        id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', gs_url)
        if not id_match: return []
        csv_url = f"https://docs.google.com/spreadsheets/d/{id_match.group(1)}/export?format=csv&gid=0"
        return [p for p in pd.read_csv(csv_url).iloc[:, 0].dropna().astype(str).str.strip().tolist() if p.upper() != 'PIEZA']
    except: return []

def filtrar_piezas_h(df, lista_h):
    if df.empty or 'Código' not in df.columns or not lista_h: return df
    unique_codes = df['Código'].dropna().unique()
    codes_to_remove = {cod for cod in unique_codes for item in lista_h if (len(str(cod)) > 5 and str(cod).upper() in str(item).upper()) or difflib.SequenceMatcher(None, str(cod).upper(), str(item).upper()).ratio() >= 0.85}
    return df[~df['Código'].isin(codes_to_remove)].copy() if codes_to_remove else df

# --- GRÁFICOS: ESTÁNDAR Y COMBINADO (APILADO) ---
def plot_top10(df_subset, titulo, color_bar, metrica):
    fig = go.Figure()
    if df_subset is None or df_subset.empty:
        fig.update_layout(title=dict(text=f"<b>{titulo}</b>", font=dict(color="#F8FAFC", size=13)), height=300, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False), yaxis=dict(visible=False), annotations=[dict(text="Sin registros", xref="paper", yref="paper", showarrow=False, font=dict(size=14, color="#94A3B8"))], margin=dict(t=40, b=10, l=10, r=10))
        return fig
        
    df_top = df_subset.groupby('Código')[metrica].sum().reset_index().sort_values(metrica, ascending=True).tail(10)
    df_top = df_top[df_top[metrica] > 0]
    if df_top.empty: return fig
    
    top_codes = df_top['Código'].tolist()
    
    fig = px.bar(df_top, x=metrica, y='Código', orientation='h', text=metrica)
    fig.update_traces(marker_color=color_bar, textposition='outside', textfont=dict(color='#F8FAFC', size=11), width=0.6)
    fig.update_layout(
        title=dict(text=f"<b>{titulo}</b>", font=dict(color="#F8FAFC", size=13)), 
        height=300, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', 
        font=dict(color="#F8FAFC"), 
        xaxis=dict(visible=False, range=[0, df_top[metrica].max() * 1.3]), 
        yaxis=dict(title="", tickfont=dict(size=10, color="#F8FAFC"), categoryorder='array', categoryarray=top_codes), 
        margin=dict(t=40, b=10, l=10, r=40)
    )
    return fig

def plot_top10_stacked(df_subset, titulo, metrica):
    fig = go.Figure()
    if df_subset is None or df_subset.empty:
        fig.update_layout(title=dict(text=f"<b>{titulo}</b>", font=dict(color="#F8FAFC", size=13)), height=300, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False), yaxis=dict(visible=False), annotations=[dict(text="Sin registros", xref="paper", yref="paper", showarrow=False, font=dict(size=14, color="#94A3B8"))], margin=dict(t=40, b=10, l=10, r=10))
        return fig
        
    df_totals = df_subset.groupby('Código')[metrica].sum().reset_index()
    top_codes = df_totals.nlargest(10, metrica)['Código'].tolist()
    
    if not top_codes: return fig
    
    df_plot = df_subset[df_subset['Código'].isin(top_codes)].groupby(['Código', 'FUENTE'])[metrica].sum().reset_index()
    df_plot = df_plot[df_plot[metrica] > 0]
    
    color_map = {'Línea': '#3498DB', 'Formulario': '#F97316'}
    
    fig = px.bar(df_plot, x=metrica, y='Código', color='FUENTE', orientation='h', text=metrica, color_discrete_map=color_map, barmode='stack')
    fig.update_traces(textposition='inside', textfont=dict(color='#F8FAFC', size=11, shadow="auto"), width=0.6)
    
    for code in top_codes:
        total_val = df_totals[df_totals['Código'] == code][metrica].values[0]
        fig.add_annotation(x=total_val, y=code, text=f"<b>{int(total_val)}</b>", showarrow=False, xanchor='left', xshift=5, font=dict(color="#2ECC71", size=13))

    fig.update_layout(
        title=dict(text=f"<b>{titulo}</b>", font=dict(color="#F8FAFC", size=13)), 
        height=300, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', 
        font=dict(color="#F8FAFC"), 
        xaxis=dict(visible=False, range=[0, df_totals[df_totals['Código'].isin(top_codes)][metrica].max() * 1.3]), 
        yaxis=dict(title="", tickfont=dict(size=10, color="#F8FAFC"), categoryorder='array', categoryarray=top_codes[::-1]), 
        margin=dict(t=40, b=10, l=10, r=40), 
        legend=dict(title="", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10, color="#F8FAFC"))
    )
    return fig

# CONEXIÓN SQL DINÁMICA
@st.cache_data(ttl=300)
def fetch_annual_data(anio, planta):
    try:
        conn_name = "famma" if planta == "FAMMA" else "fumiscor"
        conn = st.connection(conn_name, type="sql")
        q_anual = f"SELECT p.Month as Mes, ISNULL(c.Name, 'OTRA') as Máquina, ISNULL(pr.Code, 'SIN CÓDIGO') as Código, SUM(p.Good) as Buenas, SUM(p.Rework) as Retrabajo, SUM(p.Scrap) as Observadas FROM PROD_M_01 p LEFT JOIN CELL c ON p.CellId = c.CellId LEFT JOIN PRODUCT pr ON p.ProductId = pr.ProductId WHERE p.Year = {anio} GROUP BY p.Month, c.Name, pr.Code"
        df_anual = conn.query(q_anual)
        if not df_anual.empty:
            for col in ['Buenas', 'Retrabajo', 'Observadas']: df_anual[col] = pd.to_numeric(df_anual[col], errors='coerce').fillna(0)
        return df_anual
    except Exception as e:
        st.error(f"Error conectando a SQL ({conn_name}): {e}"); return pd.DataFrame()

# LECTURA DE GOOGLE SHEETS
@st.cache_data(ttl=300)
def fetch_gs_annual(gs_url, anio):
    try:
        id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', gs_url)
        if not id_match: return pd.DataFrame()
        gid = re.search(r'gid=(\d+)', gs_url).group(1) if re.search(r'gid=(\d+)', gs_url) else "0"
        df_gs = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{id_match.group(1)}/export?format=csv&gid={gid}")
        df_gs.columns = df_gs.columns.str.strip()
        
        exclude_keywords = ['SCRAP', 'OK', 'ORIGEN', 'TRAZABILIDAD', 'MOTIVO', 'MAQUINA', 'PLANTA', 'HORAS', 'OPERARIO']
        cols_piezas = [c for c in df_gs.columns if any(p in c.upper() for p in ['FIAT', 'RENAULT', 'NISSAN', 'QUE PIEZA', 'PIEZA']) and not any(ex in c.upper() for ex in exclude_keywords)]
        df_gs['Código'] = df_gs[cols_piezas].astype(str).replace(r'^\s*$', pd.NA, regex=True).replace('nan', pd.NA).bfill(axis=1).iloc[:, 0].fillna('SIN CÓDIGO') if cols_piezas else "SIN CÓDIGO"
            
        c_scrap = next((c for c in df_gs.columns if 'SCRAP' in c.upper() and 'MOTIVO' not in c.upper()), None)
        c_rt = next((c for c in df_gs.columns if ('OK' in c.upper() or 'RETRABAJO' in c.upper() or 'CANTIDAD RT' in c.upper()) and 'MOTIVO' not in c.upper()), None)
            
        df_gs['Observadas'] = pd.to_numeric(df_gs[c_scrap].astype(str).str.replace(',', '.').str.extract(r'(\d+\.?\d*)', expand=False), errors='coerce').fillna(0) if c_scrap else 0
        df_gs['Retrabajo'] = pd.to_numeric(df_gs[c_rt].astype(str).str.replace(',', '.').str.extract(r'(\d+\.?\d*)', expand=False), errors='coerce').fillna(0) if c_rt else 0
        
        c_fecha = next((c for c in df_gs.columns if 'MARCA TEMPORAL' in c.upper() or 'TIMESTAMP' in c.upper()), None)
        if not c_fecha: c_fecha = next((c for c in df_gs.columns if 'FECHA' in c.upper()), None)
        df_gs['Fecha_DT'] = pd.to_datetime(df_gs[c_fecha], errors='coerce', dayfirst=True) if c_fecha else pd.NaT
            
        c_cliente = next((c for c in df_gs.columns if 'MAQUINA DE ORIGEN' in c.upper() or 'MÁQUINA DE ORIGEN' in c.upper()), None)
        if not c_cliente: c_cliente = next((c for c in df_gs.columns if 'MAQUINA' in c.upper() or 'MÁQUINA' in c.upper()), None)
        if not c_cliente: c_cliente = next((c for c in df_gs.columns if 'CLIENTE' in c.upper()), None)
        df_gs['Cliente'] = df_gs[c_cliente].fillna('OTRO') if c_cliente else 'OTRO'
        
        df_gs = df_gs[df_gs['Fecha_DT'].dt.year == anio].copy()
        df_gs = df_gs[(df_gs['Observadas'] > 0) | (df_gs['Retrabajo'] > 0)]
        
        if not df_gs.empty:
            df_gs['Mes'] = df_gs['Fecha_DT'].dt.month
            df_gs['Máquina'] = df_gs['Cliente']
            df_gs['Buenas'] = 0
            return df_gs[['Mes', 'Máquina', 'Código', 'Buenas', 'Retrabajo', 'Observadas']]
        return pd.DataFrame()
    except Exception as e: return pd.DataFrame()

def asignar_y_filtrar_origen_sql(m, area):
    m_upper = str(m).strip().upper()
    if 'RT' in m_upper or 'RETRABAJO' in m_upper: return 'SECTOR RT' 
    m_clean = m_upper.replace(' FAMMA', '').replace('FAMMA', '').replace(' FUMISCOR', '').replace('FUMISCOR', '').replace(' FUMIS', '').strip()
    kw_soldadura = ['CELL', 'CELDA', 'PRP', 'SOLD', 'ROBOT', 'PUNTO', 'PROY', 'ENSAMBLE', 'ARMADO', 'MONTAJE', 'MIG', 'MAG', 'TIG']
    kw_estampado = ['LINEA', 'LÍNEA', 'PRENSA', 'MATRIC', 'FIREWALL', 'BALANCIN', 'CORTE', 'BLANQUEO', 'ESTAMPA', 'TANDEM', 'GUILLOTINA', 'BALANCÍN']
    is_sold = any(k in m_upper for k in kw_soldadura) or re.search(r'\bC\d+', m_upper)
    is_est  = any(k in m_upper for k in kw_estampado) or re.search(r'\bP\d+', m_upper)
    
    if area == "ESTAMPADO (Líneas)":
        if is_sold: return None
        if 'LINEA 1.5' in m_upper or 'LÍNEA 1.5' in m_upper: return 'LINEA 1.5'
        if 'LINEA 1' in m_upper or 'LÍNEA 1' in m_upper: return 'LINEA 1'
        if 'LINEA 2' in m_upper or 'LÍNEA 2' in m_upper: return 'LINEA 2'
        if 'LINEA 3' in m_upper or 'LÍNEA 3' in m_upper: return 'LINEA 3'
        if 'LINEA 4' in m_upper or 'LÍNEA 4' in m_upper: return 'LINEA 4'
        if 'MATRIC' in m_upper: return 'MATRICERIA'
        if 'FIREWALL' in m_upper: return 'FIREWALL'
        return m_clean 
    else: 
        if is_est: return None 
        if 'PRP' in m_upper: return 'EQUIPOS PRP'
        return m_clean 

# ==========================================
# ⚙️ PANEL DE CONTROL UNIFICADO
# ==========================================
st.markdown('<div class="header-style">📊 PANEL DE CALIDAD: SCRAP Y RETRABAJO</div>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown('<div style="color:#38BDF8; font-weight:bold; font-size: 16px; margin-bottom:10px;">⚙️ CONFIGURACIÓN DEL TABLERO</div>', unsafe_allow_html=True)
    
    # Fila 1: Origen de datos
    c1, c2, c3, c4 = st.columns([1.5, 1, 2.5, 1.5])
    with c1: planta_sel = st.selectbox("**🏢 Planta:**", ["FAMMA", "FUMISCOR"])
    with c2: anio_sel = st.selectbox("**📅 Año:**", range(2023, pd.to_datetime("today").year + 2), index=pd.to_datetime("today").year-2023)
    with c3: area_sel = st.radio("**⚙️ Área:**", ["ESTAMPADO (Líneas)", "SOLDADURA (Celdas y PRP)"], horizontal=True)
    with c4: 
        st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
        ignorar_h = st.checkbox("🚫 Ignorar Piezas H", value=False)
        if st.button("🔄 Actualizar Datos", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # --- CARGA DE DATOS ---
    url_gs_activa = URL_GS_RT_FAMMA if planta_sel == "FAMMA" else URL_GS_RT_FUMISCOR
    df_sql = fetch_annual_data(anio_sel, planta_sel)
    df_gs = fetch_gs_annual(url_gs_activa, anio_sel)
    lista_piezas_h = fetch_piezas_h(URL_GS_H) if ignorar_h else []

    df_sql_fil = df_sql.copy() if not df_sql.empty else pd.DataFrame()
    if not df_sql_fil.empty:
        df_sql_fil['ORIGEN'] = df_sql_fil['Máquina'].apply(lambda x: asignar_y_filtrar_origen_sql(x, area_sel))
        df_sql_fil = df_sql_fil[df_sql_fil['ORIGEN'].notnull()]
        df_sql_fil['FUENTE'] = 'Línea'

    df_gs_fil = df_gs.copy() if not df_gs.empty else pd.DataFrame()
    if not df_gs_fil.empty:
        df_gs_fil['Código'] = df_gs_fil['Código'].str.strip().str.upper()
        df_gs_fil['ORIGEN'] = df_gs_fil['Máquina'].apply(lambda x: asignar_y_filtrar_origen_sql(x, area_sel))
        df_gs_fil = df_gs_fil[df_gs_fil['ORIGEN'].notnull()]
        df_gs_fil['FUENTE'] = 'Formulario'

    df_full_raw = pd.concat([df_sql_fil, df_gs_fil], ignore_index=True) if (not df_sql_fil.empty or not df_gs_fil.empty) else pd.DataFrame()

    hoy = pd.to_datetime("today")
    if anio_sel == hoy.year and not df_full_raw.empty: df_full_raw = df_full_raw[df_full_raw['Mes'] <= hoy.month]

    df_full = unificar_codigos_similares(df_full_raw)
    if ignorar_h and not df_full.empty: df_full = filtrar_piezas_h(df_full, lista_piezas_h)

    # Fila 2: Filtros de Visualización
    st.markdown("<hr style='margin: 10px 0; border-color: #334155;'>", unsafe_allow_html=True)
    c5, c6, c7 = st.columns([1.5, 1.5, 2])
    with c5: panel_principal = st.radio("**Indicador a analizar:**", ["🔴 SCRAP", "🟠 RETRABAJO (RT)"], horizontal=True)
    with c6: vista_sel = st.radio("**Vista temporal:**", ["📊 Acumulado Anual", "📆 Detalle Mensual"], horizontal=True)
    with c7:
        meses_disp = sorted(df_full['Mes'].unique().tolist()) if not df_full.empty else []
        mes_nombres = [MESES_MAP[m] for m in meses_disp]
        if vista_sel == "📆 Detalle Mensual":
            if mes_nombres:
                mes_sel_nombre = st.selectbox("**Seleccione el Mes:**", mes_nombres, index=len(mes_nombres)-1)
                mes_sel_int = MESES_REVERSE_MAP[mes_sel_nombre]
            else:
                st.info("Sin meses disponibles")
                mes_sel_nombre = None
        else:
            mes_sel_nombre = None

st.divider()

# ==========================================
# 📊 RENDERIZADO DE RESULTADOS
# ==========================================
if not df_full.empty:
    origenes_productivos = [o for o in sorted(df_full['ORIGEN'].unique()) if str(o) != 'nan']
    colors = ["#2ECC71", "#3498DB", "#9B59B6", "#1ABC9C", "#E67E22", "#E74C3C", "#F1C40F", "#34495E", "#16A085", "#8E44AD", "#D35400", "#27AE60"]

    if panel_principal == "🔴 SCRAP":
        if vista_sel == "📊 Acumulado Anual":
            df_mes = df_full.groupby('Mes').agg(Buenas=('Buenas', 'sum'), Retrabajo=('Retrabajo', 'sum'), Scrap=('Observadas', 'sum')).reset_index()
            df_mes['Total_Piezas'] = df_mes['Buenas'] + df_mes['Retrabajo'] + df_mes['Scrap']
            df_mes['Pct_Scrap'] = (df_mes['Scrap'] / df_mes['Total_Piezas'].replace(0, 1)) * 100
            
            df_mes_completo = pd.merge(pd.DataFrame({'Mes': range(1, 13)}), df_mes, on='Mes', how='left').fillna(0)
            df_mes_completo['Mes_Nombre'] = df_mes_completo['Mes'].map(MESES_MAP)
            
            st.markdown(f'<div class="sub-header">INDICADOR GENERAL DE SCRAP DE PLANTA - {area_sel}</div>', unsafe_allow_html=True)
            matriz_general = pd.DataFrame(index=['TOTAL PIEZAS', 'TOTAL SCRAP', '% SCRAP'])
            for _, row in df_mes_completo.iterrows():
                matriz_general.loc['TOTAL PIEZAS', row['Mes_Nombre']] = f"{int(row['Total_Piezas']):,}".replace(',', '.')
                matriz_general.loc['TOTAL SCRAP', row['Mes_Nombre']] = f"{int(row['Scrap']):,}".replace(',', '.')
                matriz_general.loc['% SCRAP', row['Mes_Nombre']] = "0,00%" if row['Total_Piezas'] == 0 else f"{row['Pct_Scrap']:.2f}%".replace('.', ',')
            render_dark_table(matriz_general)

            matriz_origen = pd.DataFrame(index=origenes_productivos)
            for m in range(1, 13):
                total_mes_scrap = df_mes_completo[df_mes_completo['Mes'] == m]['Scrap'].values[0]
                for orig in origenes_productivos:
                    val = df_full[(df_full['ORIGEN'] == orig) & (df_full['Mes'] == m)]['Observadas'].sum()
                    pct = (val / total_mes_scrap * 100) if total_mes_scrap > 0 else 0
                    matriz_origen.loc[orig, MESES_MAP[m]] = f"{int(val)}  |  {pct:.0f}%" if val > 0 else "-"
            if not matriz_origen.empty:
                matriz_origen.loc['TOTAL'] = matriz_general.loc['TOTAL SCRAP']
                render_dark_table(matriz_origen)

            st.divider()
            
            st.markdown('<div class="sub-header">TOP 10 SCRAP ANUAL - LÍNEA VS FORMULARIO</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            with c1.container(border=True): st.plotly_chart(plot_top10(df_full[df_full['FUENTE'] == 'Línea'], "SOLO LÍNEA (SQL)", "#3498DB", 'Observadas'), use_container_width=True)
            with c2.container(border=True): st.plotly_chart(plot_top10(df_full[df_full['FUENTE'] == 'Formulario'], "SOLO FORMULARIO (GS)", "#F97316", 'Observadas'), use_container_width=True)
            with c3.container(border=True): st.plotly_chart(plot_top10_stacked(df_full, "TOTAL COMBINADO", 'Observadas'), use_container_width=True)
                
            st.divider()

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                with st.container(border=True):
                    fig_pct = go.Figure()
                    fig_pct.add_trace(go.Bar(x=df_mes_completo['Mes_Nombre'], y=df_mes_completo['Pct_Scrap'], marker_color='#F59E0B', text=[f"{v:.2f}%" if v>0 else "" for v in df_mes_completo['Pct_Scrap']], textposition='outside', textfont=dict(color="#F8FAFC", size=11)))
                    fig_pct.add_hline(y=0.5, line_color="#38BDF8", line_width=2, line_dash="solid", annotation_text="Meta: 0.50%", annotation_font=dict(color="#38BDF8", size=12))
                    fig_pct.update_layout(title=dict(text="<b>% DE SCRAP MENSUAL</b>", font=dict(color="#F8FAFC", size=15)), height=350, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color="#F8FAFC"), yaxis=dict(title="% Scrap", gridcolor="#334155", tickfont=dict(color="#F8FAFC")), xaxis=dict(tickfont=dict(color="#F8FAFC")), margin=dict(t=40, b=20, l=20, r=20))
                    st.plotly_chart(fig_pct, use_container_width=True)
                
            with col_g2:
                with st.container(border=True):
                    df_g_origen = df_full.groupby(['Mes', 'ORIGEN'])['Observadas'].sum().reset_index()
                    df_g_origen['Mes_Nombre'] = df_g_origen['Mes'].map(MESES_MAP)
                    fig_bar = px.bar(df_g_origen, x='Mes_Nombre', y='Observadas', color='ORIGEN', barmode='group', title="<b>SCRAP POR ORÍGENES (Cantidad)</b>", color_discrete_sequence=px.colors.qualitative.Prism)
                    fig_bar.update_layout(title=dict(font=dict(color="#F8FAFC", size=15)), height=350, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color="#F8FAFC"), yaxis=dict(title="Cantidad Piezas", gridcolor="#334155", tickfont=dict(color="#F8FAFC")), xaxis=dict(title="", tickfont=dict(color="#F8FAFC")), margin=dict(t=40, b=20, l=20, r=20), legend=dict(title=dict(text="<b>ORIGEN</b>", font=dict(color="#F8FAFC")), font=dict(color="#F8FAFC")))
                    st.plotly_chart(fig_bar, use_container_width=True)

        elif vista_sel == "📆 Detalle Mensual" and mes_sel_nombre:
            df_mes_view = df_full[df_full['Mes'] == mes_sel_int].copy()
            st.markdown(f'<div class="sub-header" style="text-align:center; background-color:#1E293B; padding:8px; border:1px solid #38BDF8; border-radius:6px; color:#F8FAFC;">INDICADORES DE SCRAP - {mes_sel_nombre}</div>', unsafe_allow_html=True)
            
            if not df_mes_view.empty:
                total_scrap_mes = df_mes_view['Observadas'].sum()
                df_tabla_mes = df_mes_view.groupby(['FUENTE', 'ORIGEN'])['Observadas'].sum().reset_index()
                df_tabla_mes = df_tabla_mes[df_tabla_mes['Observadas'] > 0]
                df_tabla_mes['ORIGEN_MOSTRAR'] = df_tabla_mes['ORIGEN'] + " (" + df_tabla_mes['FUENTE'] + ")"
                df_tabla_mes['%'] = (df_tabla_mes['Observadas'] / total_scrap_mes) * 100 if total_scrap_mes > 0 else 0
                
                row1_m = st.columns([1, 1.5, 1.5])
                with row1_m[0].container(border=True):
                    html_tb = f'<table style="width:100%; border-collapse: collapse; border: 1px solid #475569; font-family: Arial; font-size: 13px; text-align: center; color: #F8FAFC;">'
                    html_tb += f'<tr style="background-color: #334155;"><th style="border: 1px solid #475569; padding: 6px;">ORIGEN</th><th style="border: 1px solid #475569;">CANT</th><th style="border: 1px solid #475569;">%</th></tr>'
                    for _, row_tb in df_tabla_mes.sort_values('Observadas', ascending=False).iterrows():
                        html_tb += f'<tr style="background-color: #1E293B;"><td style="border: 1px solid #475569; padding: 4px;">{row_tb["ORIGEN_MOSTRAR"]}</td><td style="border: 1px solid #475569;">{int(row_tb["Observadas"])}</td><td style="border: 1px solid #475569;">{row_tb["%"]:.0f}%</td></tr>'
                    html_tb += f'<tr style="background-color: #F59E0B; color: #000000; font-weight: bold;"><td style="border: 1px solid #475569; padding: 6px;">TOTAL</td><td style="border: 1px solid #475569;">{int(total_scrap_mes)}</td><td style="border: 1px solid #475569;">100%</td></tr></table>'
                    st.markdown(html_tb, unsafe_allow_html=True)
                
                with row1_m[1].container(border=True):
                    if total_scrap_mes > 0:
                        fig_pie = px.pie(df_tabla_mes, values='Observadas', names='ORIGEN_MOSTRAR', color_discrete_sequence=px.colors.qualitative.Pastel)
                        fig_pie.update_traces(textposition='inside', textinfo='percent+label', textfont=dict(color="#000000", size=12))
                        fig_pie.update_layout(title=dict(text="<b>DISTRIBUCIÓN POR ORIGEN</b>", font=dict(color="#F8FAFC", size=14)), height=280, margin=dict(t=40, b=10, l=10, r=10), showlegend=False, paper_bgcolor='rgba(0,0,0,0)', font=dict(color="#F8FAFC"))
                        st.plotly_chart(fig_pie, use_container_width=True)
                    else: st.info("Sin Scrap este mes")

                with row1_m[2].container(border=True):
                    st.plotly_chart(plot_top10(df_mes_view[df_mes_view['ORIGEN'] == 'SECTOR RT'], "TOP SCRAP (SECTOR RT)", "#F59E0B", 'Observadas'), use_container_width=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown('<div class="sub-header">TOP 10 SCRAP (MENSUAL) - LÍNEA VS FORMULARIO</div>', unsafe_allow_html=True)
                cm1, cm2, cm3 = st.columns(3)
                with cm1.container(border=True): st.plotly_chart(plot_top10(df_mes_view[df_mes_view['FUENTE'] == 'Línea'], "SOLO LÍNEA (SQL)", "#3498DB", 'Observadas'), use_container_width=True)
                with cm2.container(border=True): st.plotly_chart(plot_top10(df_mes_view[df_mes_view['FUENTE'] == 'Formulario'], "SOLO FORMULARIO (GS)", "#F97316", 'Observadas'), use_container_width=True)
                with cm3.container(border=True): st.plotly_chart(plot_top10_stacked(df_mes_view, "TOTAL COMBINADO", 'Observadas'), use_container_width=True)
            else: st.info(f"No hay registros de Scrap para {mes_sel_nombre}.")

    # ====== PANEL RETRABAJO (RT) ======
    elif panel_principal == "🟠 RETRABAJO (RT)":
        if vista_sel == "📊 Acumulado Anual":
            df_mes_rt = df_full.groupby('Mes').agg(Buenas=('Buenas', 'sum'), Retrabajo=('Retrabajo', 'sum'), Scrap=('Observadas', 'sum')).reset_index()
            df_mes_rt['Total_Piezas'] = df_mes_rt['Buenas'] + df_mes_rt['Retrabajo'] + df_mes_rt['Scrap']
            df_mes_rt['Pct_RT'] = (df_mes_rt['Retrabajo'] / df_mes_rt['Total_Piezas'].replace(0, 1)) * 100
            
            df_mes_completo_rt = pd.merge(pd.DataFrame({'Mes': range(1, 13)}), df_mes_rt, on='Mes', how='left').fillna(0)
            df_mes_completo_rt['Mes_Nombre'] = df_mes_completo_rt['Mes'].map(MESES_MAP)
            
            st.markdown(f'<div class="sub-header">INDICADOR GENERAL DE RETRABAJO DE PLANTA - {area_sel}</div>', unsafe_allow_html=True)
            matriz_rt = pd.DataFrame(index=['TOTAL PIEZAS', 'TOTAL RT', '% RT'])
            for _, row in df_mes_completo_rt.iterrows():
                matriz_rt.loc['TOTAL PIEZAS', row['Mes_Nombre']] = f"{int(row['Total_Piezas']):,}".replace(',', '.')
                matriz_rt.loc['TOTAL RT', row['Mes_Nombre']] = f"{int(row['Retrabajo']):,}".replace(',', '.')
                matriz_rt.loc['% RT', row['Mes_Nombre']] = "0,00%" if row['Total_Piezas'] == 0 else f"{row['Pct_RT']:.2f}%".replace('.', ',')
            render_dark_table(matriz_rt)
            
            matriz_origen_rt = pd.DataFrame(index=origenes_productivos)
            for m in range(1, 13):
                total_mes_rt_val = df_mes_completo_rt[df_mes_completo_rt['Mes'] == m]['Retrabajo'].values[0]
                for orig in origenes_productivos:
                    val = df_full[(df_full['ORIGEN'] == orig) & (df_full['Mes'] == m)]['Retrabajo'].sum()
                    pct = (val / total_mes_rt_val * 100) if total_mes_rt_val > 0 else 0
                    matriz_origen_rt.loc[orig, MESES_MAP[m]] = f"{int(val)}  |  {pct:.0f}%" if val > 0 else "-"
            if not matriz_origen_rt.empty:
                matriz_origen_rt.loc['TOTAL'] = matriz_rt.loc['TOTAL RT']
                render_dark_table(matriz_origen_rt)

            st.divider()

            st.markdown('<div class="sub-header">TOP 10 RETRABAJO ANUAL - LÍNEA VS FORMULARIO</div>', unsafe_allow_html=True)
            c1_rt, c2_rt, c3_rt = st.columns(3)
            with c1_rt.container(border=True): st.plotly_chart(plot_top10(df_full[df_full['FUENTE'] == 'Línea'], "SOLO LÍNEA (SQL)", "#3498DB", 'Retrabajo'), use_container_width=True)
            with c2_rt.container(border=True): st.plotly_chart(plot_top10(df_full[df_full['FUENTE'] == 'Formulario'], "SOLO FORMULARIO (GS)", "#F97316", 'Retrabajo'), use_container_width=True)
            with c3_rt.container(border=True): st.plotly_chart(plot_top10_stacked(df_full, "TOTAL COMBINADO", 'Retrabajo'), use_container_width=True)

            st.divider()
            
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                with st.container(border=True):
                    fig_pct_rt = go.Figure()
                    fig_pct_rt.add_trace(go.Bar(x=df_mes_completo_rt['Mes_Nombre'], y=df_mes_completo_rt['Pct_RT'], marker_color='#38BDF8', text=[f"{v:.2f}%" if v>0 else "" for v in df_mes_completo_rt['Pct_RT']], textposition='outside', textfont=dict(color="#F8FAFC", size=11)))
                    fig_pct_rt.add_hline(y=2.0, line_color="#EF4444", line_width=2, line_dash="solid", annotation_text="Meta: 2.00%", annotation_font=dict(color="#EF4444", size=12))
                    fig_pct_rt.update_layout(title=dict(text="<b>% DE RT MENSUAL</b>", font=dict(color="#F8FAFC", size=15)), height=350, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color="#F8FAFC"), yaxis=dict(title="% Retrabajo", gridcolor="#334155", tickfont=dict(color="#F8FAFC")), xaxis=dict(tickfont=dict(color="#F8FAFC")), margin=dict(t=40, b=20, l=20, r=20))
                    st.plotly_chart(fig_pct_rt, use_container_width=True)
            
            with col_r2:
                with st.container(border=True):
                    df_g_origen_rt = df_full.groupby(['Mes', 'ORIGEN'])['Retrabajo'].sum().reset_index()
                    df_g_origen_rt['Mes_Nombre'] = df_g_origen_rt['Mes'].map(MESES_MAP)
                    fig_bar_rt = px.bar(df_g_origen_rt, x='Mes_Nombre', y='Retrabajo', color='ORIGEN', barmode='group', title="<b>RETRABAJO POR ORÍGENES (Cantidad)</b>", color_discrete_sequence=px.colors.qualitative.Prism)
                    fig_bar_rt.update_layout(title=dict(font=dict(color="#F8FAFC", size=15)), height=350, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color="#F8FAFC"), yaxis=dict(title="Cantidad Piezas RT", gridcolor="#334155", tickfont=dict(color="#F8FAFC")), xaxis=dict(title="", tickfont=dict(color="#F8FAFC")), margin=dict(t=40, b=20, l=20, r=20), legend=dict(title=dict(text="<b>ORIGEN</b>", font=dict(color="#F8FAFC")), font=dict(color="#F8FAFC")))
                    st.plotly_chart(fig_bar_rt, use_container_width=True)

        elif vista_sel == "📆 Detalle Mensual" and mes_sel_nombre:
            df_mes_view_rt = df_full[df_full['Mes'] == mes_sel_int].copy()
            st.markdown(f'<div class="sub-header" style="text-align:center; background-color:#1E293B; padding:8px; border:1px solid #38BDF8; border-radius:6px; color:#F8FAFC;">INDICADORES DE RETRABAJO - {mes_sel_nombre}</div>', unsafe_allow_html=True)
            
            if not df_mes_view_rt.empty:
                total_rt_mes = df_mes_view_rt['Retrabajo'].sum()
                df_tabla_mes_rt = df_mes_view_rt.groupby(['FUENTE', 'ORIGEN'])['Retrabajo'].sum().reset_index()
                df_tabla_mes_rt = df_tabla_mes_rt[df_tabla_mes_rt['Retrabajo'] > 0]
                df_tabla_mes_rt['ORIGEN_MOSTRAR'] = df_tabla_mes_rt['ORIGEN'] + " (" + df_tabla_mes_rt['FUENTE'] + ")"
                df_tabla_mes_rt['%'] = (df_tabla_mes_rt['Retrabajo'] / total_rt_mes) * 100 if total_rt_mes > 0 else 0
                
                row1_m_rt = st.columns([1, 1.5, 1.5])
                with row1_m_rt[0].container(border=True):
                    html_tb_rt = f'<table style="width:100%; border-collapse: collapse; border: 1px solid #475569; font-family: Arial; font-size: 13px; text-align: center; color: #F8FAFC;">'
                    html_tb_rt += f'<tr style="background-color: #334155;"><th style="border: 1px solid #475569; padding: 6px;">ORIGEN</th><th style="border: 1px solid #475569;">CANT</th><th style="border: 1px solid #475569;">%</th></tr>'
                    for _, row_tb in df_tabla_mes_rt.sort_values('Retrabajo', ascending=False).iterrows():
                        html_tb_rt += f'<tr style="background-color: #1E293B;"><td style="border: 1px solid #475569; padding: 4px;">{row_tb["ORIGEN_MOSTRAR"]}</td><td style="border: 1px solid #475569;">{int(row_tb["Retrabajo"])}</td><td style="border: 1px solid #475569;">{row_tb["%"]:.0f}%</td></tr>'
                    html_tb_rt += f'<tr style="background-color: #F59E0B; color: #000000; font-weight: bold;"><td style="border: 1px solid #475569; padding: 6px;">TOTAL</td><td style="border: 1px solid #475569;">{int(total_rt_mes)}</td><td style="border: 1px solid #475569;">100%</td></tr></table>'
                    st.markdown(html_tb_rt, unsafe_allow_html=True)
                
                with row1_m_rt[1].container(border=True):
                    if total_rt_mes > 0:
                        fig_pie_rt = px.pie(df_tabla_mes_rt, values='Retrabajo', names='ORIGEN_MOSTRAR', color_discrete_sequence=px.colors.qualitative.Pastel)
                        fig_pie_rt.update_traces(textposition='inside', textinfo='percent+label', textfont=dict(color="#000000", size=12))
                        fig_pie_rt.update_layout(title=dict(text="<b>DISTRIBUCIÓN POR ORIGEN</b>", font=dict(color="#F8FAFC", size=14)), height=280, margin=dict(t=40, b=10, l=10, r=10), showlegend=False, paper_bgcolor='rgba(0,0,0,0)', font=dict(color="#F8FAFC"))
                        st.plotly_chart(fig_pie_rt, use_container_width=True)
                    else: st.info("Sin Retrabajo este mes")

                with row1_m_rt[2].container(border=True):
                    st.markdown('<div style="margin-top: 5px; margin-bottom: 10px; color:#F8FAFC;"><b>Top 10 Piezas (Tabla General)</b></div>', unsafe_allow_html=True)
                    top_rt_df = df_mes_view_rt.groupby('Código')['Retrabajo'].sum().reset_index().sort_values('Retrabajo', ascending=False).head(10)
                    st.dataframe(top_rt_df, column_config={"Código": "Código de Producto", "Retrabajo": st.column_config.NumberColumn("Cantidad RT", format="%d")}, hide_index=True, use_container_width=True)
                
                st.markdown("<br>", unsafe_allow_html=True)

                st.markdown('<div class="sub-header">TOP 10 RETRABAJO (MENSUAL) - LÍNEA VS FORMULARIO</div>', unsafe_allow_html=True)
                cm1_rt, cm2_rt, cm3_rt = st.columns(3)
                with cm1_rt.container(border=True): st.plotly_chart(plot_top10(df_mes_view_rt[df_mes_view_rt['FUENTE'] == 'Línea'], "SOLO LÍNEA (SQL)", "#3498DB", 'Retrabajo'), use_container_width=True)
                with cm2_rt.container(border=True): st.plotly_chart(plot_top10(df_mes_view_rt[df_mes_view_rt['FUENTE'] == 'Formulario'], "SOLO FORMULARIO (GS)", "#F97316", 'Retrabajo'), use_container_width=True)
                with cm3_rt.container(border=True): st.plotly_chart(plot_top10_stacked(df_mes_view_rt, "TOTAL COMBINADO", 'Retrabajo'), use_container_width=True)

            else: st.info(f"No hay registros de Retrabajo para {mes_sel_nombre}.")
else:
    st.info(f"No hay registros en la base de datos para la configuración seleccionada.")
