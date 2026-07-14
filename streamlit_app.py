import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

# ==========================================
# 1. CARGA DE DATOS DE SCRAP RT DESDE GOOGLE SHEETS
# ==========================================
@st.cache_data(ttl=300)
def load_scrap_rt_google_sheets(gs_url):
    """
    Convierte cualquier enlace público de Google Sheets en un flujo CSV
    para lectura en tiempo real desde Streamlit Cloud.
    """
    try:
        if "/edit" in gs_url:
            base_url = gs_url.split("/edit")[0]
            gid = "0"
            if "gid=" in gs_url:
                gid = gs_url.split("gid=")[1].split("&")[0]
            csv_url = f"{base_url}/export?format=csv&gid={gid}"
        else:
            csv_url = gs_url
            
        df_gs = pd.read_csv(csv_url)
        
        # Limpieza estándar de columnas
        df_gs.columns = df_gs.columns.str.strip().str.upper()
        
        # Identificar columna de cantidad de scrap (común: SCRAP, CANTIDAD, SUMA DE SCRAP, PIEZAS)
        col_scrap = next((c for c in df_gs.columns if 'SCRAP' in c or 'CANT' in c or 'SUMA' in c or 'PIEZA' in c), None)
        col_prod = next((c for c in df_gs.columns if 'PROD' in c or 'COD' in c or 'PIEZA' in c or 'PART' in c), None)
        
        if col_scrap:
            df_gs['SCRAP_NUM'] = pd.to_numeric(df_gs[col_scrap], errors='coerce').fillna(0)
        else:
            df_gs['SCRAP_NUM'] = 0
            
        return df_gs, col_prod
    except Exception as e:
        st.warning(f"⚠️ No se pudo conectar con Google Sheets: {e}")
        return pd.DataFrame(), None

# ==========================================
# 2. INTERFAZ: DASHBOARD DE SCRAP Y RETRABAJO (RT)
# ==========================================
st.markdown('<div class="header-style">📊 Dashboard Consolidado: Retrabajo (RT) y Scrap</div>', unsafe_allow_html=True)
st.write("Análisis general de indicadores de calidad por planta y línea de producción, integrando datos de SQL Server y Google Sheets.")

# --- Configuración de Enlace Google Sheets ---
url_gs_default = "https://docs.google.com/spreadsheets/d/1l6a6ab82p_Nm0g0RdprVR7AWSvMgYjRp-16M1210hMU/edit?gid=1779842834#gid=1779842834"
with st.expander("🔗 Configuración de Fuente Externa (Google Sheets Scrap RT)", expanded=False):
    url_gs_input = st.text_input("URL del Google Sheets:", value=url_gs_default, key="gs_rt_url")

# Cargar Google Sheets
df_gs_rt, col_prod_gs = load_scrap_rt_google_sheets(url_gs_input)
total_scrap_gs = df_gs_rt['SCRAP_NUM'].sum() if not df_gs_rt.empty else 0

# --- Procesamiento de los datos SQL (df_prod_target) ---
if 'pdf_df_prod_target' in locals() and not pdf_df_prod_target.empty:
    df_calidad = pdf_df_prod_target.copy()
    
    # Asegurar numéricos
    for col in ['Buenas', 'Retrabajo', 'Observadas']:
        df_calidad[col] = pd.to_numeric(df_calidad[col], errors='coerce').fillna(0)
        
    # Asignar Grupos / Origen al estilo de las planillas Excel
    def asignar_origen_excel(maq):
        m = str(maq).strip().upper()
        if m in MAQUINAS_MAP: return MAQUINAS_MAP[m]
        if 'LINEA 1' in m or 'LÍNEA 1' in m: return 'LINEA 1'
        if 'LINEA 2' in m or 'LÍNEA 2' in m: return 'LINEA 2'
        if 'LINEA 3' in m or 'LÍNEA 3' in m: return 'LINEA 3'
        if 'CELL' in m or 'CELDA' in m: return 'CELDAS SOLDADURA'
        if 'PRP' in m or 'SOLD' in m: return 'EQUIPOS PRP'
        if 'MATRIC' in m: return 'MATRICERIA'
        if 'FIREWALL' in m: return 'FIREWALL'
        return 'OTRAS LÍNEAS'

    df_calidad['ORIGEN'] = df_calidad['Máquina'].apply(asignar_origen_excel)
    
    # 3. CÁLCULO DE TOTALES GLOBALES (Denominador Común)
    total_buenas_sql = df_calidad['Buenas'].sum()
    total_rt_sql = df_calidad['Retrabajo'].sum()
    total_scrap_sql = df_calidad['Observadas'].sum()
    
    # Total Piezas (Base para % según planillas de Excel)
    total_piezas_planta = total_buenas_sql + total_rt_sql + total_scrap_sql
    
    # Scrap total (SQL + Google Sheets)
    total_scrap_planta = total_scrap_sql + total_scrap_gs
    
    # Porcentajes Clave
    pct_rt_planta = (total_rt_sql / total_piezas_planta * 100) if total_piezas_planta > 0 else 0
    pct_scrap_planta = (total_scrap_planta / total_piezas_planta * 100) if total_piezas_planta > 0 else 0

    # ==========================================
    # 4. TARJETAS DE INDICADORES (KPI CARDS)
    # ==========================================
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total Piezas Producidas", f"{int(total_piezas_planta):,}".replace(",", "."))
    with c2:
        st.metric("Total Retrabajo (RT)", f"{int(total_rt_sql):,}".replace(",", "."), f"{pct_rt_planta:.2f}% del total", delta_color="inverse")
    with c3:
        st.metric("Total Scrap (Planta + GS)", f"{int(total_scrap_planta):,}".replace(",", "."), f"{pct_scrap_planta:.2f}% del total", delta_color="inverse")
    with c4:
        st.metric("Scrap en Línea (SQL)", f"{int(total_scrap_sql):,}".replace(",", "."))
    with c5:
        st.metric("Scrap de RT (Google Sheets)", f"{int(total_scrap_gs):,}".replace(",", "."))

    st.divider()

    # ==========================================
    # 5. TABLA RESUMEN ESTILO EXCEL (POR ORIGEN / LÍNEA)
    # ==========================================
    st.markdown("### 📋 Resumen por Origen de Falla / Línea de Producción")
    
    # Agrupar por Origen
    resumen_origen = df_calidad.groupby('ORIGEN')[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
    
    # Añadir la fila externa de Google Sheets como un Origen propio "RT (Google Sheets)"
    if total_scrap_gs > 0:
        fila_gs = pd.DataFrame([{
            'ORIGEN': 'RT (Google Sheets)',
            'Buenas': 0,
            'Retrabajo': 0,
            'Observadas': total_scrap_gs
        }])
        resumen_origen = pd.concat([resumen_origen, fila_gs], ignore_index=True)

    # Calcular porcentajes individuales sobre los totales de Planta
    resumen_origen['Total Piezas Origen'] = resumen_origen['Buenas'] + resumen_origen['Retrabajo'] + resumen_origen['Observadas']
    resumen_origen['% RT sobre Total'] = (resumen_origen['Retrabajo'] / total_piezas_planta) * 100
    resumen_origen['% Scrap sobre Total'] = (resumen_origen['Observadas'] / total_piezas_planta) * 100
    
    # Ordenar por volumen de defectos (RT + Scrap)
    resumen_origen['Total Defectos'] = resumen_origen['Retrabajo'] + resumen_origen['Observadas']
    resumen_origen = resumen_origen.sort_values('Total Defectos', ascending=False).drop(columns=['Total Defectos'])

    # Formatear tabla para visualización limpia
    st.dataframe(
        resumen_origen,
        column_config={
            "ORIGEN": st.column_config.TextColumn("Origen / Línea", width="medium"),
            "Buenas": st.column_config.NumberColumn("Piezas Buenas", format="%d"),
            "Retrabajo": st.column_config.NumberColumn("Cant. RT", format="%d"),
            "% RT sobre Total": st.column_config.ProgressColumn("% RT (Planta)", format="%.2f%%", min_value=0, max_value=max(resumen_origen['% RT sobre Total'].max(), 5)),
            "Observadas": st.column_config.NumberColumn("Cant. Scrap", format="%d"),
            "% Scrap sobre Total": st.column_config.ProgressColumn("% Scrap (Planta)", format="%.2f%%", min_value=0, max_value=max(resumen_origen['% Scrap sobre Total'].max(), 5)),
            "Total Piezas Origen": st.column_config.NumberColumn("Volumen Total", format="%d"),
        },
        hide_index=True,
        use_container_width=True
    )

    # ==========================================
    # 6. GRÁFICOS COMPARATIVOS (ESTIMADO VS SOLDADURA VS RT)
    # ==========================================
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        # Gráfico de Torta: Distribución de Scrap por Origen
        fig_scrap = px.pie(
            resumen_origen[resumen_origen['Observadas'] > 0],
            values='Observadas',
            names='ORIGEN',
            hole=0.4,
            title="<b>Distribución de Scrap por Origen</b> (Incluye RT GS)",
            color_discrete_sequence=px.colors.sequential.RdBu
        )
        fig_scrap.update_traces(textinfo='percent+label', textposition='outside')
        fig_scrap.update_layout(height=380, margin=dict(t=50, b=20, l=20, r=20), showlegend=False)
        st.plotly_chart(fig_scrap, use_container_width=True)

    with col_g2:
        # Gráfico de Barras: Retrabajo (RT) por Línea
        fig_rt = px.bar(
            resumen_origen[resumen_origen['Retrabajo'] > 0].sort_values('Retrabajo', ascending=True),
            x='Retrabajo',
            y='ORIGEN',
            orientation='h',
            title="<b>Concentración de Retrabajo (RT) por Línea</b>",
            text='Retrabajo',
            color='Retrabajo',
            color_continuous_scale='Oranges'
        )
        fig_rt.update_traces(textposition='outside')
        fig_rt.update_layout(height=380, margin=dict(t=50, b=20, l=20, r=20), xaxis_title="Cantidad de Piezas RT", yaxis_title="", coloraxis_showscale=False)
        st.plotly_chart(fig_rt, use_container_width=True)

    # ==========================================
    # 7. DESGLOSE DETALLADO: TOP CÓDIGOS DE PRODUCTO (ESTILO HOJA MENSUAL EXCEL)
    # ==========================================
    st.markdown("### 🔍 Top Códigos Críticos (Piezas con Mayor Índice de Defectos)")
    
    col_t1, col_t2 = st.columns(2)
    
    with col_t1:
        st.markdown("#### Top 10 Productos con Mayor Retrabajo (RT)")
        top_rt = df_calidad.groupby('Código')['Retrabajo'].sum().reset_index()
        top_rt = top_rt[top_rt['Retrabajo'] > 0].sort_values('Retrabajo', ascending=False).head(10)
        
        st.dataframe(
            top_rt,
            column_config={
                "Código": "Código de Pieza",
                "Retrabajo": st.column_config.NumberColumn("Piezas Retrabajadas", format="%d")
            },
            hide_index=True,
            use_container_width=True
        )

    with col_t2:
        st.markdown("#### Top 10 Productos con Mayor Scrap (SQL + GS)")
        
        # Unir Scrap de SQL
        top_scrap_sql = df_calidad.groupby('Código')['Observadas'].sum().reset_index()
        top_scrap_sql.rename(columns={'Observadas': 'Scrap'}, inplace=True)
        
        # Unir Scrap de Google Sheets (si tiene código de producto)
        if not df_gs_rt.empty and col_prod_gs in df_gs_rt.columns:
            top_scrap_gs = df_gs_rt.groupby(col_prod_gs)['SCRAP_NUM'].sum().reset_index()
            top_scrap_gs.rename(columns={col_prod_gs: 'Código', 'SCRAP_NUM': 'Scrap'}, inplace=True)
            top_scrap_gs['Código'] = top_scrap_gs['Código'].astype(str)
            top_scrap_sql['Código'] = top_scrap_sql['Código'].astype(str)
            
            top_scrap = pd.concat([top_scrap_sql, top_scrap_gs]).groupby('Código')['Scrap'].sum().reset_index()
        else:
            top_scrap = top_scrap_sql
            
        top_scrap = top_scrap[top_scrap['Scrap'] > 0].sort_values('Scrap', ascending=False).head(10)
        
        st.dataframe(
            top_scrap,
            column_config={
                "Código": "Código de Pieza",
                "Scrap": st.column_config.NumberColumn("Piezas Scrap", format="%d")
            },
            hide_index=True,
            use_container_width=True
        )

    # --- Opción de descarga de datos consolidados ---
    st.divider()
    csv_export = resumen_origen.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Descargar Resumen de RT y Scrap (CSV)",
        data=csv_export,
        file_name=f"Resumen_RT_Scrap_{pd.to_datetime('today').strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True
    )
else:
    st.info("ℹ️ No hay datos de producción (`PROD_M_01` / `PROD_D_01`) cargados en el período seleccionado para calcular Scrap y RT.")
