import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import difflib

# URL fija del Google Sheets de Calidad (Scrap en Retrabajo) - Lectura en segundo plano
URL_GS_RT = "https://docs.google.com/spreadsheets/d/1l6a6ab82p_Nm0g0RdprVR7AWSvMgYjRp-16M1210hMU/edit?resourcekey=&gid=1779842834#gid=1779842834"

MESES_MAP = {1:'ENERO', 2:'FEBRERO', 3:'MARZO', 4:'ABRIL', 5:'MAYO', 6:'JUNIO', 
             7:'JULIO', 8:'AGOSTO', 9:'SEPTIEMBRE', 10:'OCTUBRE', 11:'NOVIEMBRE', 12:'DICIEMBRE'}
MESES_REVERSE_MAP = {v: k for k, v in MESES_MAP.items()}

# Configuración de página y estilos
st.set_page_config(page_title="FAMMA - Panel de Calidad", layout="wide")

st.markdown("""
<style>
    .header-style { font-size: 28px; font-weight: bold; color: #1F2937; margin-bottom: 0px; }
    .sub-header { font-size: 20px; font-weight: bold; color: #34495E; margin-top: 15px; margin-bottom: 10px; text-transform: uppercase; }
    hr { margin-top: 1rem; margin-bottom: 1rem; }
    div[data-testid="stRadio"] > div { background-color: #F8F9F9; padding: 10px; border-radius: 8px; border: 1px solid #D5D8DC; }
</style>
""", unsafe_allow_html=True)

def render_dark_table(df):
    df_reset = df.reset_index()
    df_reset.rename(columns={'index': ''}, inplace=True)
    html = '<table style="width:100%; border-collapse: collapse; border: 2px solid black; font-family: Arial, sans-serif; font-size: 13px;">'
    html += '<tr style="background-color: #D5D8DC;">'
    for col in df_reset.columns:
        html += f'<th style="border: 1px solid black; padding: 8px; text-align: center;">{col}</th>'
    html += '</tr>'
    for _, row in df_reset.iterrows():
        header_val = row.iloc[0] 
        is_bold = "font-weight: bold;" if header_val in ['TOTAL PIEZAS', 'TOTAL SCRAP', '% SCRAP', 'TOTAL RT', '% RT', 'TOTAL'] else ""
        bg_color = "background-color: #F1C40F;" if header_val in ['% SCRAP', '% RT', 'TOTAL'] else ""
        html += f'<tr style="{is_bold} {bg_color}">'
        for val in row:
            html += f'<td style="border: 1px solid black; padding: 6px; text-align: center;">{val}</td>'
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
                    is_substring = (base.upper() in other.upper()) and len(base) > 5
                    if ratio >= 0.85 or is_substring:
                        mapping[other] = base
    df['Código'] = df['Código'].map(mapping).fillna(df['Código'])
    return df

# Función auxiliar para generar gráficos de barras Top 10
def plot_top10(df_subset, titulo, color_bar):
    fig = go.Figure()
    empty_layout = lambda t: fig.update_layout(title=f"<b>{t}</b>", height=280, plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False), yaxis=dict(visible=False), annotations=[dict(text="Sin registros", xref="paper", yref="paper", showarrow=False, font=dict(size=14, color="gray"))], margin=dict(t=40, b=10, l=10, r=10))
    
    if df_subset is None or df_subset.empty:
        empty_layout(titulo)
        return fig
        
    df_top = df_subset.groupby('Código')['Observadas'].sum().reset_index()
    df_top = df_top[df_top['Observadas'] > 0].sort_values('Observadas', ascending=True).tail(10)
    
    if df_top.empty:
        empty_layout(titulo)
        return fig
        
    max_val = df_top['Observadas'].max()
    fig = px.bar(df_top, x='Observadas', y='Código', orientation='h', text='Observadas')
    fig.update_traces(marker_color=color_bar, textposition='outside', textfont=dict(color='black'), width=0.6)
    fig.update_layout(title=f"<b>{titulo}</b>", height=280, xaxis=dict(visible=False, range=[0, max_val * 1.3]), yaxis=dict(title="", tickfont=dict(size=10)), plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=40, b=10, l=10, r=40))
    return fig

# Encabezado y botón de actualización
col_title, col_btn = st.columns([5, 1])
with col_title:
    st.markdown('<div class="header-style">📊 RESUMEN SCRAP Y RT - FAMMA</div>', unsafe_allow_html=True)
    st.caption("Métrica exacta: Scrap = 'Observadas' (SQL) + GS | Retrabajo = 'Retrabajo' (SQL)")
with col_btn:
    if st.button("🔄 Actualizar Datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.divider()

# Funciones de extracción de datos
@st.cache_data(ttl=300)
def fetch_annual_data(anio):
    try:
        conn = st.connection("wii_bi", type="sql")
        q_anual = f"""
            SELECT p.Month as Mes, ISNULL(c.Name, 'OTRA') as Máquina, ISNULL(pr.Code, 'SIN CÓDIGO') as Código, 
                   SUM(p.Good) as Buenas, SUM(p.Rework) as Retrabajo, SUM(p.Scrap) as Observadas
            FROM PROD_M_01 p 
            LEFT JOIN CELL c ON p.CellId = c.CellId LEFT JOIN PRODUCT pr ON p.ProductId = pr.ProductId 
            WHERE p.Year = {anio} GROUP BY p.Month, c.Name, pr.Code
        """
        df_anual = conn.query(q_anual)
        if not df_anual.empty:
            for col in ['Buenas', 'Retrabajo', 'Observadas']:
                df_anual[col] = pd.to_numeric(df_anual[col], errors='coerce').fillna(0)
        return df_anual
    except Exception as e:
        st.error(f"Error en SQL: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_gs_annual(gs_url, anio):
    try:
        id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', gs_url)
        if not id_match: return pd.DataFrame()
        sheet_id = id_match.group(1)
        gid = re.search(r'gid=(\d+)', gs_url).group(1) if re.search(r'gid=(\d+)', gs_url) else "0"
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        df_gs = pd.read_csv(csv_url)
        df_gs.columns = df_gs.columns.str.strip()
        
        cols_piezas = [c for c in df_gs.columns if any(p in c.upper() for p in ['FIAT', 'RENAULT', 'NISSAN', 'SOLDADURA', 'QUE PIEZA'])]
        df_gs['Código'] = df_gs[cols_piezas].replace(r'^\s*$', pd.NA, regex=True).bfill(axis=1).iloc[:, 0].fillna('SIN CÓDIGO') if cols_piezas else "SIN CÓDIGO"
        c_scrap = next((c for c in df_gs.columns if 'SCRAP' in c.upper()), None)
        df_gs['Observadas'] = pd.to_numeric(df_gs[c_scrap].astype(str).str.replace(',', ''), errors='coerce').fillna(0) if c_scrap else 0
        c_fecha = next((c for c in ['Fecha', 'Marca temporal', 'FECHA'] if c in df_gs.columns), None)
        df_gs['Fecha_DT'] = pd.to_datetime(df_gs[c_fecha], dayfirst=True, errors='coerce') if c_fecha else pd.NaT
        c_cliente = next((c for c in df_gs.columns if 'CLIENTE' in c.upper()), None)
        df_gs['Cliente'] = df_gs[c_cliente].fillna('OTRO') if c_cliente else 'OTRO'
        
        df_gs = df_gs[df_gs['Fecha_DT'].dt.year == anio].copy()
        if not df_gs.empty:
            df_gs['Mes'] = df_gs['Fecha_DT'].dt.month
            df_gs['ORIGEN'] = 'RT'
            df_gs['Máquina'] = df_gs['Cliente']
            df_gs['Buenas'] = 0
            df_gs['Retrabajo'] = 0
            return df_gs[['Mes', 'Máquina', 'ORIGEN', 'Código', 'Buenas', 'Retrabajo', 'Observadas']]
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

# Filtros principales
col_f1, col_f2 = st.columns([1, 3])
with col_f1:
    anio_sel = st.selectbox("**Año de Análisis:**", range(2023, pd.to_datetime("today").year + 2), index=pd.to_datetime("today").year-2023)
with col_f2:
    area_sel = st.radio("**Área de Producción:**", ["ESTAMPADO (Líneas)", "SOLDADURA (Celdas y PRP)"], horizontal=True)

# Carga de datos
df_sql = fetch_annual_data(anio_sel)
df_gs = fetch_gs_annual(URL_GS_RT, anio_sel)

def asignar_y_filtrar_origen_sql(m, area):
    m = str(m).strip().upper()
    if 'RT' in m or 'RETRABAJO' in m: return None 
    if area == "ESTAMPADO (Líneas)":
        if 'LINEA 1' in m or 'LÍNEA 1' in m: return 'LINEA 1'
        if 'LINEA 2' in m or 'LÍNEA 2' in m: return 'LINEA 2'
        if 'LINEA 3' in m or 'LÍNEA 3' in m: return 'LINEA 3'
        if 'MATRIC' in m: return 'MATRICERIA'
        if 'FIREWALL' in m: return 'FIREWALL'
        return None
    else:
        if 'CELL' in m or 'CELDA' in m: return m 
        if 'PRP' in m or 'SOLD' in m: return 'EQUIPOS PRP'
        return None

# PROCESAMIENTO ESTRICTO
df_sql_fil = df_sql.copy() if not df_sql.empty else pd.DataFrame()
if not df_sql_fil.empty:
    df_sql_fil['ORIGEN'] = df_sql_fil['Máquina'].apply(lambda x: asignar_y_filtrar_origen_sql(x, area_sel))
    df_sql_fil = df_sql_fil[df_sql_fil['ORIGEN'].notnull()]

lista_blanca_sql = set(df_sql_fil['Código'].str.strip().str.upper().unique()) if not df_sql_fil.empty else set()

df_gs_fil = df_gs.copy() if not df_gs.empty else pd.DataFrame()
if not df_gs_fil.empty:
    if len(lista_blanca_sql) > 0:
        df_gs_fil['Código_Clean'] = df_gs_fil['Código'].str.strip().str.upper()
        df_gs_fil = df_gs_fil[df_gs_fil['Código_Clean'].isin(lista_blanca_sql)]
        df_gs_fil.drop(columns=['Código_Clean'], inplace=True)
    else:
        df_gs_fil = pd.DataFrame()

df_full_raw = pd.concat([df_sql_fil, df_gs_fil], ignore_index=True) if not df_sql_fil.empty else pd.DataFrame()

hoy = pd.to_datetime("today")
if anio_sel == hoy.year and not df_full_raw.empty:
    df_full_raw = df_full_raw[df_full_raw['Mes'] < hoy.month]

df_full = unificar_codigos_similares(df_full_raw)

# Configuración de Colores y Origenes para Gráficos
origenes_productivos = [o for o in sorted(df_full['ORIGEN'].unique()) if o != 'RT' and str(o) != 'nan'] if not df_full.empty else []
colors = ["#27AE60", "#2980B9", "#8E44AD", "#16A085", "#D35400", "#C0392B", "#34495E"]

# --- PESTAÑAS PRINCIPALES ---
tab_scrap, tab_rt = st.tabs(["🔴 MATRIZ DE SCRAP", "🟠 MATRIZ DE RETRABAJO (RT)"])

# ====== PESTAÑA SCRAP ======
with tab_scrap:
    if not df_full.empty:
        
        # TOGGLE: ANUAL vs MENSUAL
        col_t1, col_t2 = st.columns([1, 2])
        with col_t1:
            vista_scrap = st.radio("**Seleccione Vista:**", ["📆 Detalle Mensual (Dashboard Excel)", "📊 Acumulado Anual"], horizontal=True)
            
        st.divider()

        if vista_scrap == "📊 Acumulado Anual":
            # --- VISTA ACUMULADA ANUAL (Original) ---
            df_mes = df_full.groupby('Mes').agg(Buenas=('Buenas', 'sum'), Retrabajo=('Retrabajo', 'sum'), Scrap=('Observadas', 'sum')).reset_index()
            df_mes['Total_Piezas'] = df_mes['Buenas'] + df_mes['Retrabajo'] + df_mes['Scrap']
            df_mes['Pct_Scrap'] = (df_mes['Scrap'] / df_mes['Total_Piezas'].replace(0, 1)) * 100
            
            df_mes_completo = pd.DataFrame({'Mes': range(1, 13)})
            df_mes_completo = pd.merge(df_mes_completo, df_mes, on='Mes', how='left').fillna(0)
            df_mes_completo['Mes_Nombre'] = df_mes_completo['Mes'].map(MESES_MAP)
            
            st.markdown(f'<div class="sub-header">INDICADOR GENERAL DE SCRAP DE PLANTA - {area_sel}</div>', unsafe_allow_html=True)
            
            matriz_general = pd.DataFrame(index=['TOTAL PIEZAS', 'TOTAL SCRAP', '% SCRAP'])
            for _, row in df_mes_completo.iterrows():
                matriz_general.loc['TOTAL PIEZAS', row['Mes_Nombre']] = f"{int(row['Total_Piezas']):,}".replace(',', '.')
                matriz_general.loc['TOTAL SCRAP', row['Mes_Nombre']] = f"{int(row['Scrap']):,}".replace(',', '.')
                matriz_general.loc['% SCRAP', row['Mes_Nombre']] = "0,00%" if row['Total_Piezas'] == 0 else f"{row['Pct_Scrap']:.2f}%".replace('.', ',')

            render_dark_table(matriz_general)

            origenes = sorted(df_full['ORIGEN'].unique().tolist())
            matriz_origen = pd.DataFrame(index=origenes)
            for m in range(1, 13):
                total_mes_scrap = df_mes_completo[df_mes_completo['Mes'] == m]['Scrap'].values[0]
                for orig in origenes:
                    val = df_full[(df_full['ORIGEN'] == orig) & (df_full['Mes'] == m)]['Observadas'].sum()
                    pct = (val / total_mes_scrap * 100) if total_mes_scrap > 0 else 0
                    matriz_origen.loc[orig, MESES_MAP[m]] = f"{int(val)}  |  {pct:.0f}%" if val > 0 else "-"

            if not matriz_origen.empty:
                matriz_origen.loc['TOTAL'] = matriz_general.loc['TOTAL SCRAP']
                render_dark_table(matriz_origen)

            st.divider()

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                with st.container(border=True):
                    fig_pct = go.Figure()
                    fig_pct.add_trace(go.Bar(x=df_mes_completo['Mes_Nombre'], y=df_mes_completo['Pct_Scrap'], marker_color='#F1C40F', text=[f"{v:.2f}%" if v>0 else "" for v in df_mes_completo['Pct_Scrap']], textposition='outside'))
                    fig_pct.add_hline(y=0.5, line_color="#E67E22", line_width=2, line_dash="solid", annotation_text="Meta: 0.50%")
                    fig_pct.update_layout(title="<b>% DE SCRAP MENSUAL</b>", height=350, plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(title="% Scrap"), margin=dict(t=40, b=20, l=20, r=20))
                    st.plotly_chart(fig_pct, use_container_width=True)
                
            with col_g2:
                with st.container(border=True):
                    df_g_origen = df_full.groupby(['Mes', 'ORIGEN'])['Observadas'].sum().reset_index()
                    df_g_origen['Mes_Nombre'] = df_g_origen['Mes'].map(MESES_MAP)
                    fig_bar = px.bar(df_g_origen, x='Mes_Nombre', y='Observadas', color='ORIGEN', barmode='group', title="<b>SCRAP POR ORIGENES (Cantidad)</b>", color_discrete_sequence=px.colors.qualitative.Prism)
                    fig_bar.update_layout(height=350, plot_bgcolor='rgba(0,0,0,0)', yaxis_title="Cantidad Piezas", xaxis_title="", margin=dict(t=40, b=20, l=20, r=20), legend_title="")
                    st.plotly_chart(fig_bar, use_container_width=True)

            st.divider()
            st.markdown('<div class="sub-header">SCRAP - TOP 10 DEL AÑO POR ORIGEN</div>', unsafe_allow_html=True)
            
            # Cuadrícula Dinámica con Recuadros (Anual)
            row_cols = st.columns(3)
            with row_cols[0].container(border=True):
                st.plotly_chart(plot_top10(df_full, "SCRAP GENERAL (Todo el Año)", "#5D6D7E"), use_container_width=True)
            with row_cols[1].container(border=True):
                st.plotly_chart(plot_top10(df_full[df_full['ORIGEN'] == 'RT'], "SCRAP RT", "#F39C12"), use_container_width=True)
            
            c_idx, r_container = 2, row_cols
            for i, orig in enumerate(origenes_productivos):
                if c_idx == 3:
                    r_container = st.columns(3)
                    c_idx = 0
                with r_container[c_idx].container(border=True):
                    st.plotly_chart(plot_top10(df_full[df_full['ORIGEN'] == orig], f"SCRAP - {orig}", colors[i % len(colors)]), use_container_width=True)
                c_idx += 1


        else:
            # --- VISTA DETALLE MENSUAL (REPLICA EXCEL) ---
            meses_disp = sorted(df_full['Mes'].unique().tolist())
            mes_nombres = [MESES_MAP[m] for m in meses_disp]
            
            col_sel_mes, _ = st.columns([1, 4])
            with col_sel_mes:
                mes_sel_nombre = st.selectbox("**Seleccione el Mes:**", mes_nombres, index=len(mes_nombres)-1)
            
            mes_sel_int = MESES_REVERSE_MAP[mes_sel_nombre]
            df_mes_view = df_full[df_full['Mes'] == mes_sel_int].copy()
            
            st.markdown(f'<div class="sub-header" style="text-align:center; background-color:#D5D8DC; padding:8px; border:2px solid black; color:black;">INDICADORES DE SCRAP DE PLANTA - {mes_sel_nombre}</div>', unsafe_allow_html=True)
            
            if not df_mes_view.empty:
                total_scrap_mes = df_mes_view['Observadas'].sum()
                df_tabla_mes = df_mes_view.groupby('ORIGEN')['Observadas'].sum().reset_index()
                df_tabla_mes['%'] = (df_tabla_mes['Observadas'] / total_scrap_mes) * 100 if total_scrap_mes > 0 else 0
                
                # Fila 1: Tabla, Gráfico Gral, Pie Chart
                row1_m = st.columns([1, 1.5, 1.5])
                
                # Tabla Origen (Izquierda)
                with row1_m[0].container(border=True):
                    html_tb = f'<table style="width:100%; border-collapse: collapse; border: 2px solid black; font-family: Arial; font-size: 13px; text-align: center;">'
                    html_tb += f'<tr style="background-color: #EAEDED;"><th style="border: 1px solid black; padding: 4px;">ORIGEN</th><th style="border: 1px solid black;">CANT</th><th style="border: 1px solid black;">%</th></tr>'
                    for _, row_tb in df_tabla_mes.sort_values('Observadas', ascending=False).iterrows():
                        html_tb += f'<tr><td style="border: 1px solid black; padding: 4px;">{row_tb["ORIGEN"]}</td><td style="border: 1px solid black;">{int(row_tb["Observadas"])}</td><td style="border: 1px solid black;">{row_tb["%"]:.0f}%</td></tr>'
                    html_tb += f'<tr style="background-color: #F1C40F; font-weight: bold;"><td style="border: 1px solid black; padding: 4px;">TOTAL</td><td style="border: 1px solid black;">{int(total_scrap_mes)}</td><td style="border: 1px solid black;">100%</td></tr>'
                    html_tb += '</table>'
                    st.markdown(html_tb, unsafe_allow_html=True)
                
                # Pie Chart (Centro)
                with row1_m[1].container(border=True):
                    if total_scrap_mes > 0:
                        fig_pie = px.pie(df_tabla_mes, values='Observadas', names='ORIGEN', color_discrete_sequence=px.colors.qualitative.Pastel)
                        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                        fig_pie.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
                        st.plotly_chart(fig_pie, use_container_width=True)
                    else:
                        st.info("Sin Scrap este mes")

                # General Scrap (Derecha)
                with row1_m[2].container(border=True):
                    st.plotly_chart(plot_top10(df_mes_view, "SCRAP GENERAL", "#5D6D7E"), use_container_width=True)
                
                # Cuadrícula Dinámica con Recuadros (Mensual)
                st.markdown("<br>", unsafe_allow_html=True)
                row_cols_m = st.columns(3)
                
                # Siempre mostrar RT primero si aplica
                with row_cols_m[0].container(border=True):
                    st.plotly_chart(plot_top10(df_mes_view[df_mes_view['ORIGEN'] == 'RT'], "SCRAP RT", "#F39C12"), use_container_width=True)
                
                c_idx_m, r_container_m = 1, row_cols_m
                for i, orig in enumerate(origenes_productivos):
                    if c_idx_m == 3:
                        r_container_m = st.columns(3)
                        c_idx_m = 0
                    with r_container_m[c_idx_m].container(border=True):
                        st.plotly_chart(plot_top10(df_mes_view[df_mes_view['ORIGEN'] == orig], f"SCRAP {orig}", colors[i % len(colors)]), use_container_width=True)
                    c_idx_m += 1

            else:
                st.info(f"No hay registros de Scrap para el mes de {mes_sel_nombre}.")

    else:
        st.info(f"No hay registros de Scrap en la base de datos para el año {anio_sel} en el área seleccionada.")

# ====== PESTAÑA RETRABAJO (RT) ======
with tab_rt:
    if not df_full.empty:
        df_mes_rt = df_full.groupby('Mes').agg(Buenas=('Buenas', 'sum'), Retrabajo=('Retrabajo', 'sum'), Scrap=('Observadas', 'sum')).reset_index()
        df_mes_rt['Total_Piezas'] = df_mes_rt['Buenas'] + df_mes_rt['Retrabajo'] + df_mes_rt['Scrap']
        df_mes_rt['Pct_RT'] = (df_mes_rt['Retrabajo'] / df_mes_rt['Total_Piezas'].replace(0, 1)) * 100
        
        df_mes_completo_rt = pd.DataFrame({'Mes': range(1, 13)})
        df_mes_completo_rt = pd.merge(df_mes_completo_rt, df_mes_rt, on='Mes', how='left').fillna(0)
        df_mes_completo_rt['Mes_Nombre'] = df_mes_completo_rt['Mes'].map(MESES_MAP)
        
        st.markdown(f'<div class="sub-header">INDICADOR GENERAL DE RETRABAJO DE PLANTA - {area_sel}</div>', unsafe_allow_html=True)
        
        matriz_rt = pd.DataFrame(index=['TOTAL PIEZAS', 'TOTAL RT', '% RT'])
        for _, row in df_mes_completo_rt.iterrows():
            mes_str = row['Mes_Nombre']
            matriz_rt.loc['TOTAL PIEZAS', mes_str] = f"{int(row['Total_Piezas']):,}".replace(',', '.')
            matriz_rt.loc['TOTAL RT', mes_str] = f"{int(row['Retrabajo']):,}".replace(',', '.')
            matriz_rt.loc['% RT', mes_str] = "0,00%" if row['Total_Piezas'] == 0 else f"{row['Pct_RT']:.2f}%".replace('.', ',')

        render_dark_table(matriz_rt)
        
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            with st.container(border=True):
                fig_pct_rt = go.Figure()
                fig_pct_rt.add_trace(go.Bar(x=df_mes_completo_rt['Mes_Nombre'], y=df_mes_completo_rt['Pct_RT'], marker_color='#E67E22', text=[f"{v:.2f}%" if v>0 else "" for v in df_mes_completo_rt['Pct_RT']], textposition='outside'))
                fig_pct_rt.add_hline(y=2.0, line_color="#C0392B", line_width=2, line_dash="solid", annotation_text="Meta: 2.00%")
                fig_pct_rt.update_layout(title="<b>% DE RT MENSUAL</b>", height=350, plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=40, b=20, l=20, r=20))
                st.plotly_chart(fig_pct_rt, use_container_width=True)
            
        with col_r2:
            with st.container(border=True):
                st.markdown('<div style="margin-top: 10px; margin-bottom: 15px;"><b>Top 15 Piezas con Mayor Retrabajo (SQL)</b></div>', unsafe_allow_html=True)
                top_rt_df = df_full.groupby('Código')['Retrabajo'].sum().reset_index()
                top_rt_df = top_rt_df[top_rt_df['Retrabajo'] > 0].sort_values('Retrabajo', ascending=False).head(15)
                st.dataframe(top_rt_df, column_config={"Código": "Código de Producto", "Retrabajo": st.column_config.NumberColumn("Cantidad RT", format="%d")}, hide_index=True, use_container_width=True)
    else:
        st.info("No hay registros de Retrabajo para el área seleccionada.")
