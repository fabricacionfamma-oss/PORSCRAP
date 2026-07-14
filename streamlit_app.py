import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
from datetime import timedelta
import calendar

# ==========================================
# 0. CONFIGURACIÓN Y CONSTANTES
# ==========================================
URL_GS_RT = "https://docs.google.com/spreadsheets/d/1l6a6ab82p_Nm0g0RdprVR7AWSvMgYjRp-16M1210hMU/edit?resourcekey=&gid=1779842834#gid=1779842834"

MESES_MAP = {1:'ENERO', 2:'FEBRERO', 3:'MARZO', 4:'ABRIL', 5:'MAYO', 6:'JUNIO', 
             7:'JULIO', 8:'AGOSTO', 9:'SEPTIEMBRE', 10:'OCTUBRE', 11:'NOVIEMBRE', 12:'DICIEMBRE'}

st.set_page_config(page_title="Dashboard Gerencial - FAMMA", layout="wide", page_icon="📊")

st.markdown("""
<style>
    .header-style { font-size: 28px; font-weight: bold; color: #1F2937; margin-bottom: 0px; }
    .sub-header { font-size: 18px; font-weight: bold; color: #34495E; margin-top: 10px; margin-bottom: 10px; }
    hr { margin-top: 1rem; margin-bottom: 1rem; }
    .stDataFrame { border: 1px solid #ddd; }
</style>
""", unsafe_allow_html=True)

col_title, col_btn = st.columns([5, 1])
with col_title:
    st.markdown('<div class="header-style">📊 INDICADOR GENERAL DE PLANTA (SCRAP Y RT)</div>', unsafe_allow_html=True)
with col_btn:
    if st.button("🔄 Actualizar Datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ==========================================
# 1. FUNCIONES DE BASE DE DATOS (CON LEFT JOIN Y FECHAS CORREGIDAS)
# ==========================================
@st.cache_data(ttl=300)
def fetch_annual_data(anio):
    """
    Extrae la data anual consolidada de producción, retrabajo y scrap desde SQL Server.
    Usa LEFT JOIN para no perder registros que no tengan ProductId o CellId.
    """
    try:
        conn = st.connection("wii_bi", type="sql")
        
        # Consulta Anual Principal
        q_anual = f"""
            SELECT p.Month as Mes, 
                   ISNULL(c.Name, 'OTRA') as Máquina, 
                   ISNULL(pr.Code, 'SIN CÓDIGO') as Código, 
                   SUM(p.Good) as Buenas, 
                   SUM(p.Rework) as Retrabajo, 
                   SUM(p.Scrap) as Observadas
            FROM PROD_M_01 p 
            LEFT JOIN CELL c ON p.CellId = c.CellId 
            LEFT JOIN PRODUCT pr ON p.ProductId = pr.ProductId 
            WHERE p.Year = {anio}
            GROUP BY p.Month, c.Name, pr.Code
        """
        df_anual = conn.query(q_anual)
        
        # Mapeo de orígenes igual al Excel
        def asignar_origen(m):
            m = str(m).strip().upper()
            if 'LINEA 1' in m or 'LÍNEA 1' in m: return 'LINEA 1'
            if 'LINEA 2' in m or 'LÍNEA 2' in m: return 'LINEA 2'
            if 'LINEA 3' in m or 'LÍNEA 3' in m: return 'LINEA 3'
            if 'MATRIC' in m: return 'MATRICERIA'
            if 'FIREWALL' in m: return 'FIREWALL'
            if 'RT' in m or 'RETRABAJO' in m: return 'RT'
            return 'OTROS'

        if not df_anual.empty:
            for col in ['Buenas', 'Retrabajo', 'Observadas']:
                df_anual[col] = pd.to_numeric(df_anual[col], errors='coerce').fillna(0)
            df_anual['ORIGEN'] = df_anual['Máquina'].apply(asignar_origen)
            
        return df_anual
    except Exception as e:
        st.error(f"Error en SQL: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_gs_annual(gs_url, anio):
    """
    Extrae y unifica los datos anuales del Google Sheets para Scrap en RT.
    """
    try:
        id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', gs_url)
        if not id_match: return pd.DataFrame()
        sheet_id = id_match.group(1)
        gid = re.search(r'gid=(\d+)', gs_url).group(1) if re.search(r'gid=(\d+)', gs_url) else "0"
        
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        df_gs = pd.read_csv(csv_url)
        df_gs.columns = df_gs.columns.str.strip()
        
        # Unificar piezas
        cols_piezas = [c for c in df_gs.columns if any(p in c.upper() for p in ['FIAT', 'RENAULT', 'NISSAN', 'SOLDADURA', 'QUE PIEZA'])]
        if cols_piezas:
            df_gs['Código'] = df_gs[cols_piezas].replace(r'^\s*$', pd.NA, regex=True).bfill(axis=1).iloc[:, 0].fillna('SIN CÓDIGO')
        else:
            df_gs['Código'] = "SIN CÓDIGO"
            
        # Obtener Scrap y Fecha
        c_scrap = next((c for c in df_gs.columns if 'SCRAP' in c.upper()), None)
        df_gs['Observadas'] = pd.to_numeric(df_gs[c_scrap].astype(str).str.replace(',', ''), errors='coerce').fillna(0) if c_scrap else 0
        
        c_fecha = next((c for c in df_gs.columns if 'FECHA' in c.upper() or 'TEMPORAL' in c.upper()), None)
        df_gs['Fecha_DT'] = pd.to_datetime(df_gs[c_fecha], dayfirst=True, errors='coerce') if c_fecha else pd.NaT
        
        # Filtrar por año
        df_gs = df_gs[df_gs['Fecha_DT'].dt.year == anio].copy()
        
        if not df_gs.empty:
            df_gs['Mes'] = df_gs['Fecha_DT'].dt.month
            df_gs['ORIGEN'] = 'RT (GS)'
            df_gs['Buenas'] = 0
            df_gs['Retrabajo'] = 0
            return df_gs[['Mes', 'ORIGEN', 'Código', 'Buenas', 'Retrabajo', 'Observadas']]
            
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

# ==========================================
# 2. FILTROS DE AÑO SUPERIORES
# ==========================================
st.write("**Seleccione el año de análisis:**")
anio_sel = st.selectbox("Año", range(2023, pd.to_datetime("today").year + 2), index=pd.to_datetime("today").year-2023, label_visibility="collapsed")

# Cargar Datos Anuales
df_sql = fetch_annual_data(anio_sel)
df_gs = fetch_gs_annual(URL_GS_RT, anio_sel)

# Combinar SQL y Google Sheets
if not df_gs.empty:
    df_full = pd.concat([df_sql, df_gs], ignore_index=True)
else:
    df_full = df_sql.copy()

# ==========================================
# 3. PESTAÑAS DEL DASHBOARD
# ==========================================
tab_scrap, tab_rt, tab_pdf = st.tabs([
    "🔴 DASHBOARD SCRAP (Visual Excel)", 
    "🟠 DASHBOARD RETRABAJO (RT)", 
    "📄 GENERADOR PDF"
])

# ---------------------------------------------------------
# PESTAÑA 1: DASHBOARD SCRAP (IDÉNTICO AL EXCEL)
# ---------------------------------------------------------
with tab_scrap:
    if not df_full.empty:
        # Calcular Totales Mensuales de la Planta
        df_mes = df_full.groupby('Mes').agg(
            Buenas=('Buenas', 'sum'),
            Retrabajo=('Retrabajo', 'sum'),
            Scrap=('Observadas', 'sum')
        ).reset_index()
        
        df_mes['Total_Piezas'] = df_mes['Buenas'] + df_mes['Retrabajo'] + df_mes['Scrap']
        df_mes['Pct_Scrap'] = (df_mes['Scrap'] / df_mes['Total_Piezas'].replace(0, 1)) * 100
        
        # Asegurar todos los meses del 1 al 12
        df_mes_completo = pd.DataFrame({'Mes': range(1, 13)})
        df_mes_completo = pd.merge(df_mes_completo, df_mes, on='Mes', how='left').fillna(0)
        df_mes_completo['Mes_Nombre'] = df_mes_completo['Mes'].map(MESES_MAP)
        
        # 1. MATRIZ SUPERIOR: INDICADOR GENERAL DE SCRAP DE PLANTA
        st.markdown('<div class="sub-header">INDICADOR GENERAL DE SCRAP DE PLANTA</div>', unsafe_allow_html=True)
        
        # Transformar para visualización
        matriz_general = pd.DataFrame(index=['TOTAL PIEZAS', 'TOTAL SCRAP', '% SCRAP'])
        for _, row in df_mes_completo.iterrows():
            mes_str = row['Mes_Nombre']
            matriz_general.loc['TOTAL PIEZAS', mes_str] = f"{int(row['Total_Piezas']):,}".replace(',', '.')
            matriz_general.loc['TOTAL SCRAP', mes_str] = f"{int(row['Scrap']):,}".replace(',', '.')
            # Evitar error de división por 0 visual (#¡DIV/0!)
            if row['Total_Piezas'] == 0:
                matriz_general.loc['% SCRAP', mes_str] = "0,00%"
            else:
                matriz_general.loc['% SCRAP', mes_str] = f"{row['Pct_Scrap']:.2f}%".replace('.', ',')

        st.dataframe(matriz_general, use_container_width=True)

        # 2. MATRIZ DE ORIGEN (Línea 1, Línea 2...)
        df_origen = df_full.groupby(['ORIGEN', 'Mes'])['Observadas'].sum().reset_index()
        origenes = ['LINEA 1', 'LINEA 2', 'LINEA 3', 'RT', 'MATRICERIA', 'FIREWALL', 'RT (GS)', 'OTROS']
        
        matriz_origen = pd.DataFrame(index=origenes)
        for m in range(1, 13):
            mes_str = MESES_MAP[m]
            total_mes_scrap = df_mes_completo[df_mes_completo['Mes'] == m]['Scrap'].values[0]
            
            for orig in origenes:
                val = df_origen[(df_origen['ORIGEN'] == orig) & (df_origen['Mes'] == m)]['Observadas'].sum()
                pct = (val / total_mes_scrap * 100) if total_mes_scrap > 0 else 0
                
                # Juntamos Cantidad y Porcentaje en la misma celda visualmente
                matriz_origen.loc[orig, mes_str] = f"{int(val)} ({pct:.0f}%)" if val > 0 else "-"

        # Añadir fila TOTAL a la matriz
        matriz_origen.loc['TOTAL'] = matriz_general.loc['TOTAL SCRAP']
        
        # Eliminar filas vacías si no existen (ej: "OTROS")
        matriz_origen = matriz_origen.loc[(matriz_origen != '-').any(axis=1)]
        st.dataframe(matriz_origen, use_container_width=True)

        st.divider()

        # 3. GRÁFICOS DE TENDENCIA (Mitad de pantalla)
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            # Gráfico Amarillo de % Scrap Mensual
            fig_pct = go.Figure()
            fig_pct.add_trace(go.Bar(
                x=df_mes_completo['Mes_Nombre'], 
                y=df_mes_completo['Pct_Scrap'],
                marker_color='#F1C40F', # Amarillo Excel
                text=[f"{v:.2f}%" if v>0 else "" for v in df_mes_completo['Pct_Scrap']],
                textposition='outside'
            ))
            # Línea objetivo (naranja)
            fig_pct.add_hline(y=0.5, line_color="#E67E22", line_width=2, line_dash="solid", annotation_text="0.50%")
            
            fig_pct.update_layout(
                title="<b>% DE SCRAP MENSUAL</b>",
                height=350, plot_bgcolor='rgba(0,0,0,0)', 
                yaxis=dict(title="% Scrap", tickformat=".2f"),
                margin=dict(t=40, b=20, l=20, r=20)
            )
            st.plotly_chart(fig_pct, use_container_width=True)
            
        with col_g2:
            # Gráfico de Barras Agrupadas por Línea
            df_g_origen = df_full[df_full['ORIGEN'].isin(['LINEA 1', 'LINEA 2', 'LINEA 3', 'RT', 'MATRICERIA', 'FIREWALL'])]
            df_g_origen = df_g_origen.groupby(['Mes', 'ORIGEN'])['Observadas'].sum().reset_index()
            df_g_origen['Mes_Nombre'] = df_g_origen['Mes'].map(MESES_MAP)
            
            color_map = {'LINEA 1': '#3498DB', 'LINEA 2': '#E67E22', 'LINEA 3': '#95A5A6', 
                         'RT': '#F1C40F', 'MATRICERIA': '#2980B9', 'FIREWALL': '#2ECC71'}
                         
            fig_bar = px.bar(
                df_g_origen, x='Mes_Nombre', y='Observadas', color='ORIGEN', 
                barmode='group', title="<b>SCRAP POR LÍNEA</b>",
                color_discrete_map=color_map
            )
            fig_bar.update_layout(
                height=350, plot_bgcolor='rgba(0,0,0,0)', yaxis_title="Cantidad", xaxis_title="",
                legend_title="", legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
                margin=dict(t=40, b=20, l=20, r=20)
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()

        # 4. TOP 10 CÓDIGOS DE PIEZAS (Abajo - Cuadrícula de 3 columnas)
        st.markdown('<div class="sub-header">SCRAP - TOP 10 DEL AÑO POR ORIGEN</div>', unsafe_allow_html=True)
        
        def plot_top10(df_subset, titulo, color_bar):
            if df_subset.empty: return None
            df_top = df_subset.groupby('Código')['Observadas'].sum().reset_index()
            df_top = df_top[df_top['Observadas'] > 0].sort_values('Observadas', ascending=True).tail(10)
            if df_top.empty: return None
            
            fig = px.bar(
                df_top, x='Observadas', y='Código', orientation='h', text='Observadas'
            )
            fig.update_traces(marker_color=color_bar, textposition='outside', textfont=dict(color='black'))
            fig.update_layout(
                title=f"<b>{titulo}</b>", height=300, 
                xaxis=dict(visible=False, showgrid=False), yaxis=dict(title=""),
                plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=40, b=10, l=10, r=40)
            )
            return fig

        r1c1, r1c2, r1c3 = st.columns(3)
        r2c1, r2c2, r2c3 = st.columns(3)

        # Fila 1
        with r1c1:
            fig_gen = plot_top10(df_full, "SCRAP GENERAL", "#5D6D7E")
            if fig_gen: st.plotly_chart(fig_gen, use_container_width=True)
        with r1c2:
            fig_rt = plot_top10(df_full[df_full['ORIGEN'].isin(['RT', 'RT (GS)'])], "SCRAP RT (SQL + GS)", "#F39C12")
            if fig_rt: st.plotly_chart(fig_rt, use_container_width=True)
        with r1c3:
            fig_mat = plot_top10(df_full[df_full['ORIGEN'] == 'MATRICERIA'], "SCRAP MATRICERIA", "#2980B9")
            if fig_mat: st.plotly_chart(fig_mat, use_container_width=True)

        # Fila 2
        with r2c1:
            fig_l1 = plot_top10(df_full[df_full['ORIGEN'] == 'LINEA 1'], "SCRAP L1", "#27AE60")
            if fig_l1: st.plotly_chart(fig_l1, use_container_width=True)
        with r2c2:
            fig_l2 = plot_top10(df_full[df_full['ORIGEN'] == 'LINEA 2'], "SCRAP L2", "#E67E22")
            if fig_l2: st.plotly_chart(fig_l2, use_container_width=True)
        with r2c3:
            fig_l3 = plot_top10(df_full[df_full['ORIGEN'] == 'LINEA 3'], "SCRAP L3", "#95A5A6")
            if fig_l3: st.plotly_chart(fig_l3, use_container_width=True)
            
    else:
        st.info(f"No hay registros de Scrap en la base de datos para el año {anio_sel}.")

# ---------------------------------------------------------
# PESTAÑA 2: DASHBOARD RETRABAJO (RT)
# ---------------------------------------------------------
with tab_rt:
    if not df_full.empty:
        df_mes_rt = df_full.groupby('Mes').agg(
            Buenas=('Buenas', 'sum'),
            Retrabajo=('Retrabajo', 'sum'),
            Scrap=('Observadas', 'sum')
        ).reset_index()
        
        df_mes_rt['Total_Piezas'] = df_mes_rt['Buenas'] + df_mes_rt['Retrabajo'] + df_mes_rt['Scrap']
        df_mes_rt['Pct_RT'] = (df_mes_rt['Retrabajo'] / df_mes_rt['Total_Piezas'].replace(0, 1)) * 100
        
        df_mes_completo_rt = pd.DataFrame({'Mes': range(1, 13)})
        df_mes_completo_rt = pd.merge(df_mes_completo_rt, df_mes_rt, on='Mes', how='left').fillna(0)
        df_mes_completo_rt['Mes_Nombre'] = df_mes_completo_rt['Mes'].map(MESES_MAP)
        
        st.markdown('<div class="sub-header">INDICADOR GENERAL DE RETRABAJO (RT) DE PLANTA</div>', unsafe_allow_html=True)
        
        matriz_rt = pd.DataFrame(index=['TOTAL PIEZAS', 'TOTAL RT', '% RT'])
        for _, row in df_mes_completo_rt.iterrows():
            mes_str = row['Mes_Nombre']
            matriz_rt.loc['TOTAL PIEZAS', mes_str] = f"{int(row['Total_Piezas']):,}".replace(',', '.')
            matriz_rt.loc['TOTAL RT', mes_str] = f"{int(row['Retrabajo']):,}".replace(',', '.')
            if row['Total_Piezas'] == 0:
                matriz_rt.loc['% RT', mes_str] = "0,00%"
            else:
                matriz_rt.loc['% RT', mes_str] = f"{row['Pct_RT']:.2f}%".replace('.', ',')

        st.dataframe(matriz_rt, use_container_width=True)
        
        # Gráficos de RT
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            fig_pct_rt = go.Figure()
            fig_pct_rt.add_trace(go.Bar(
                x=df_mes_completo_rt['Mes_Nombre'], y=df_mes_completo_rt['Pct_RT'],
                marker_color='#E67E22', text=[f"{v:.2f}%" if v>0 else "" for v in df_mes_completo_rt['Pct_RT']],
                textposition='outside'
            ))
            fig_pct_rt.update_layout(title="<b>% DE RT MENSUAL</b>", height=350, plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=40, b=20, l=20, r=20))
            st.plotly_chart(fig_pct_rt, use_container_width=True)
            
        with col_r2:
            st.write("**Top 15 Piezas con Mayor Retrabajo Histórico**")
            top_rt_df = df_full.groupby('Código')['Retrabajo'].sum().reset_index()
            top_rt_df = top_rt_df[top_rt_df['Retrabajo'] > 0].sort_values('Retrabajo', ascending=False).head(15)
            st.dataframe(top_rt_df, column_config={"Código": "Código de Producto", "Retrabajo": st.column_config.NumberColumn("Cantidad RT", format="%d")}, hide_index=True, use_container_width=True)
    else:
        st.info("No hay registros de Retrabajo.")

# ---------------------------------------------------------
# PESTAÑA 3: GENERADOR PDF (Solo si se requiere descargar el formato tradicional)
# ---------------------------------------------------------
with tab_pdf:
    st.markdown("### 📄 Generador PDF de Paradas y Horarios")
    st.info("Para generar los PDF detallados de paradas, horarios y OEE, utiliza este botón. Requiere que primero limpies la caché si cambiaste de año.")
