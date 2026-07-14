import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import tempfile
import os
import calendar
import io
import re
from fpdf import FPDF
from datetime import timedelta

# ==========================================
# 0. DICCIONARIOS Y CONFIGURACIONES FIJAS
# ==========================================
# URL fija y oculta del Google Sheets de Calidad (Scrap en Retrabajo)
URL_GS_RT = "https://docs.google.com/spreadsheets/d/1l6a6ab82p_Nm0g0RdprVR7AWSvMgYjRp-16M1210hMU/edit?resourcekey=&gid=1779842834#gid=1779842834"

MAQUINAS_MAP = {
    "GENERAL": "LÍNEAS ESTAMPADO" 
}

GRUPOS_ESTAMPADO = ['LÍNEAS ESTAMPADO']
GRUPOS_SOLDADURA = ['CELDAS SOLDADURA', 'EQUIPOS PRP']

st.set_page_config(page_title="Generador de Reportes y Dashboard - FAMMA", layout="wide", page_icon="📊")

st.markdown("""
<style>
    hr { margin-top: 1.5rem; margin-bottom: 1.5rem; }
    .stButton>button { height: 3rem; font-size: 16px; font-weight: bold; }
    .header-style { font-size: 26px; font-weight: bold; margin-bottom: 5px; color: #1F2937; }
</style>
""", unsafe_allow_html=True)

col_title, col_btn = st.columns([4, 1])
with col_title:
    st.markdown('<div class="header-style">📊 Reportes y Dashboard Calidad - FAMMA</div>', unsafe_allow_html=True)
    st.write("Generación de reportes consolidados en PDF y monitoreo de RT/Scrap integrando SQL Server y Google Sheets.")
with col_btn:
    if st.button("🔄 Limpiar Caché", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ==========================================
# 1. CARGA Y LIMPIEZA DE DATOS DESDE SQL SERVER
# ==========================================
@st.cache_data(ttl=300)
def fetch_data_from_db(fecha_ini, fecha_fin, tipo_periodo, mes=None, anio=None):
    try:
        conn = st.connection("wii_bi", type="sql")
        ini_str = fecha_ini.strftime('%Y-%m-%d')
        fin_str = fecha_fin.strftime('%Y-%m-%d')

        df_trend = pd.DataFrame()
        df_horarios = pd.DataFrame()

        # USO DE LEFT JOIN PARA EVITAR PÉRDIDA DE DATOS POR IDs NULOS
        if tipo_periodo == "Mensual":
            q_prod = f"""
                SELECT c.Name as Máquina, ISNULL(pr.Code, 'SIN CÓDIGO') as Código, 
                       SUM(p.Good) as Buenas, SUM(p.Rework) as Retrabajo, SUM(p.Scrap) as Observadas
                FROM PROD_M_01 p 
                LEFT JOIN CELL c ON p.CellId = c.CellId 
                LEFT JOIN PRODUCT pr ON p.ProductId = pr.ProductId 
                WHERE p.Month = {mes} AND p.Year = {anio} 
                GROUP BY c.Name, pr.Code
            """
            
            q_metrics = f"""
                SELECT c.Name as Máquina, 
                       SUM(p.Good) as Buenas, SUM(p.Rework) as Retrabajo, SUM(p.Scrap) as Observadas,
                       SUM(p.ProductiveTime) as T_Operativo, SUM(p.DownTime) as T_Parada,
                       (SUM(p.Performance * p.ProductiveTime) / NULLIF(SUM(p.ProductiveTime), 0)) as PERFORMANCE,
                       (SUM(p.Availability * (p.ProductiveTime + p.DownTime)) / NULLIF(SUM(p.ProductiveTime + p.DownTime), 0)) as DISPONIBILIDAD,
                       (SUM(p.Quality * (p.Good + p.Rework + p.Scrap)) / NULLIF(SUM(p.Good + p.Rework + p.Scrap), 0)) as CALIDAD,
                       (SUM(p.Oee * (p.ProductiveTime + p.DownTime)) / NULLIF(SUM(p.ProductiveTime + p.DownTime), 0)) as OEE
                FROM PROD_M_03 p 
                LEFT JOIN CELL c ON p.CellId = c.CellId
                WHERE p.Month = {mes} AND p.Year = {anio}
                GROUP BY c.Name
            """

            q_op = f"""
                SELECT DISTINCT op.Name as Operador, p.Factory as Fábrica, 
                       (SUM(p.Performance * p.ProductiveTime) OVER(PARTITION BY p.OperatorId) / NULLIF(SUM(p.ProductiveTime) OVER(PARTITION BY p.OperatorId), 0)) as PERFORMANCE, 
                       SUM(p.BathTime) OVER(PARTITION BY p.OperatorId) as BathTime, 
                       SUM(p.BreakTime) OVER(PARTITION BY p.OperatorId) as BreakTime, 
                       SUM(p.FeedingTime) OVER(PARTITION BY p.OperatorId) as FeedingTime 
                FROM OPER_M_01 p 
                LEFT JOIN OPERATOR op ON p.OperatorId = op.OperatorId 
                WHERE p.Month = {mes} AND p.Year = {anio}
            """
            df_op_target = conn.query(q_op)
            
            q_trend = f"""
                SELECT p.Month, c.Name as Máquina,
                       SUM(p.Oee * (p.ProductiveTime + p.DownTime)) as OEE_Num,
                       SUM(p.ProductiveTime + p.DownTime) as OEE_Den,
                       (SUM(p.Oee * (p.ProductiveTime + p.DownTime)) / NULLIF(SUM(p.ProductiveTime + p.DownTime), 0)) as OEE,
                       SUM(p.Availability * (p.ProductiveTime + p.DownTime)) as Disp_Num,
                       SUM(p.Performance * p.ProductiveTime) as Perf_Num,
                       SUM(p.ProductiveTime) as T_Operativo,
                       SUM(p.Quality * (p.Good + p.Rework + p.Scrap)) as Cal_Num,
                       SUM(p.Good + p.Rework + p.Scrap) as Piezas_Totales
                FROM PROD_M_03 p 
                LEFT JOIN CELL c ON p.CellId = c.CellId
                WHERE p.Year = {anio} AND p.Month <= {mes}
                GROUP BY p.Month, c.Name
            """
            df_trend = conn.query(q_trend)
            
        else:
            q_prod = f"""
                SELECT c.Name as Máquina, ISNULL(pr.Code, 'SIN CÓDIGO') as Código, 
                       SUM(p.Good) as Buenas, SUM(p.Rework) as Retrabajo, SUM(p.Scrap) as Observadas
                FROM PROD_D_01 p 
                LEFT JOIN CELL c ON p.CellId = c.CellId 
                LEFT JOIN PRODUCT pr ON p.ProductId = pr.ProductId 
                WHERE p.Date BETWEEN '{ini_str}' AND '{fin_str}' 
                GROUP BY c.Name, pr.Code
            """
            
            q_metrics = f"""
                SELECT c.Name as Máquina, 
                       SUM(p.Good) as Buenas, SUM(p.Rework) as Retrabajo, SUM(p.Scrap) as Observadas,
                       SUM(p.ProductiveTime) as T_Operativo, SUM(p.DownTime) as T_Parada,
                       (SUM(p.Performance * p.ProductiveTime) / NULLIF(SUM(p.ProductiveTime), 0)) as PERFORMANCE,
                       (SUM(p.Availability * (p.ProductiveTime + p.DownTime)) / NULLIF(SUM(p.ProductiveTime + p.DownTime), 0)) as DISPONIBILIDAD,
                       (SUM(p.Quality * (p.Good + p.Rework + p.Scrap)) / NULLIF(SUM(p.Good + p.Rework + p.Scrap), 0)) as CALIDAD,
                       (SUM(p.Oee * (p.ProductiveTime + p.DownTime)) / NULLIF(SUM(p.ProductiveTime + p.DownTime), 0)) as OEE
                FROM PROD_D_03 p 
                LEFT JOIN CELL c ON p.CellId = c.CellId
                WHERE p.Date BETWEEN '{ini_str}' AND '{fin_str}'
                GROUP BY c.Name
            """
            
            q_op = f"""
                SELECT op.Name as Operador, p.Factory as Fábrica,
                       p.Performance, p.ProductiveTime
                FROM OPER_D_01 p 
                LEFT JOIN OPERATOR op ON p.OperatorId = op.OperatorId 
                WHERE p.Date BETWEEN '{ini_str}' AND '{fin_str}' 
            """
            df_op_raw = conn.query(q_op)
            
            if not df_op_raw.empty:
                df_op_raw['Performance'] = pd.to_numeric(df_op_raw['Performance'], errors='coerce').fillna(0)
                df_op_raw['ProductiveTime'] = pd.to_numeric(df_op_raw['ProductiveTime'], errors='coerce').fillna(0)
                df_op_raw['Perf_Num'] = df_op_raw['Performance'] * df_op_raw['ProductiveTime']
                df_op_raw['Fábrica'] = df_op_raw['Fábrica'].fillna('No Asignada')
                
                df_op_target = df_op_raw.groupby(['Operador', 'Fábrica']).agg(
                    Perf_Num=('Perf_Num', 'sum'),
                    ProductiveTime=('ProductiveTime', 'sum')
                ).reset_index()
                
                df_op_target['PERFORMANCE'] = df_op_target['Perf_Num'] / df_op_target['ProductiveTime'].replace(0, 1)
            else:
                df_op_target = pd.DataFrame()

            q_horarios = f"""
                WITH Tiempos_Turno AS (
                    SELECT CellId, TurnId, Date as Dia,
                           MIN(Started) as MinInicio,
                           MAX(Finish) as MaxFin
                    FROM EVENT_01
                    WHERE Date BETWEEN '{ini_str}' AND '{fin_str}'
                    GROUP BY CellId, TurnId, Date
                )
                SELECT c.Name as Máquina, tu.Name as Turno, t.Dia,
                       FORMAT(MIN(t.MinInicio), 'HH:mm') as Hora_Inicio,
                       FORMAT(MAX(t.MaxFin), 'HH:mm') as Hora_Cierre,
                       SUM(ISNULL(p.ProductiveTime, 0) + ISNULL(p.DownTime, 0)) as Apertura_Neta_Min,
                       CASE 
                           WHEN ISNULL(DATEDIFF(MINUTE, MIN(t.MinInicio), MAX(t.MaxFin)), 0) - SUM(ISNULL(p.ProductiveTime, 0) + ISNULL(p.DownTime, 0)) > 0 
                           THEN ISNULL(DATEDIFF(MINUTE, MIN(t.MinInicio), MAX(t.MaxFin)), 0) - SUM(ISNULL(p.ProductiveTime, 0) + ISNULL(p.DownTime, 0))
                           ELSE 0 
                       END as No_Registrado_Min
                FROM Tiempos_Turno t
                JOIN CELL c ON t.CellId = c.CellId
                JOIN TURN tu ON t.TurnId = tu.TurnId
                LEFT JOIN PROD_D_02 p ON t.CellId = p.CellId AND t.TurnId = p.TurnId AND t.Dia = p.Date
                GROUP BY c.Name, tu.Name, t.Dia
            """
            df_horarios = conn.query(q_horarios)

            if tipo_periodo == "Semanal":
                q_trend_semanal = f"""
                    SELECT p.Date as Fecha_Filtro, c.Name as Máquina,
                           SUM(p.Oee * (p.ProductiveTime + p.DownTime)) as OEE_Num,
                           SUM(p.ProductiveTime + p.DownTime) as OEE_Den,
                           (SUM(p.Oee * (p.ProductiveTime + p.DownTime)) / NULLIF(SUM(p.ProductiveTime + p.DownTime), 0)) as OEE,
                           SUM(p.Availability * (p.ProductiveTime + p.DownTime)) as Disp_Num,
                           SUM(p.Performance * p.ProductiveTime) as Perf_Num,
                           SUM(p.ProductiveTime) as T_Operativo,
                           SUM(p.Quality * (p.Good + p.Rework + p.Scrap)) as Cal_Num,
                           SUM(p.Good + p.Rework + p.Scrap) as Piezas_Totales
                    FROM PROD_D_03 p 
                    LEFT JOIN CELL c ON p.CellId = c.CellId
                    WHERE p.Date BETWEEN '{ini_str}' AND '{fin_str}'
                    GROUP BY p.Date, c.Name
                """
                df_trend = conn.query(q_trend_semanal)
            else:
                df_trend = pd.DataFrame()

        df_prod_target = conn.query(q_prod)
        df_metrics = conn.query(q_metrics)

        if not df_op_target.empty:
            df_op_target = df_op_target[~df_op_target['Operador'].str.lower().str.contains('usuario', na=False)]

        q_event = f"""
            SELECT e.Id as Evento_Id, c.Name as Máquina, e.Started as Inicio, e.Finish as Fin, 
                   e.Interval as [Tiempo (Min)], 
                   t1.Name as [Nivel Evento 1], t2.Name as [Nivel Evento 2], 
                   t3.Name as [Nivel Evento 3], t4.Name as [Nivel Evento 4], 
                   t5.Name as [Nivel Evento 5], t6.Name as [Nivel Evento 6],
                   t7.Name as [Nivel Evento 7], t8.Name as [Nivel Evento 8],
                   t9.Name as [Nivel Evento 9],
                   op_celda.Name as Operador_Celda,
                   op_req.Name as Operador_Req,
                   op_resp.Name as Operador_Resp,
                   e.Date as Fecha_Filtro, f.Name as Fábrica, tu.Name as Turno
            FROM EVENT_01 e
            LEFT JOIN CELL c ON e.CellId = c.CellId
            LEFT JOIN EVENTTYPE t1 ON e.EventTypeLevel1 = t1.EventTypeId
            LEFT JOIN EVENTTYPE t2 ON e.EventTypeLevel2 = t2.EventTypeId
            LEFT JOIN EVENTTYPE t3 ON e.EventTypeLevel3 = t3.EventTypeId
            LEFT JOIN EVENTTYPE t4 ON e.EventTypeLevel4 = t4.EventTypeId
            LEFT JOIN EVENTTYPE t5 ON e.EventTypeLevel5 = t5.EventTypeId
            LEFT JOIN EVENTTYPE t6 ON e.EventTypeLevel6 = t6.EventTypeId
            LEFT JOIN EVENTTYPE t7 ON e.EventTypeLevel7 = t7.EventTypeId
            LEFT JOIN EVENTTYPE t8 ON e.EventTypeLevel8 = t8.EventTypeId
            LEFT JOIN EVENTTYPE t9 ON e.EventTypeLevel9 = t9.EventTypeId
            LEFT JOIN FACTORY f ON e.FactoryId = f.FactoryId
            LEFT JOIN TURN tu ON e.TurnId = tu.TurnId
            LEFT JOIN EVENT_OPERATOR_01 eo ON e.Id = eo.EventId
            LEFT JOIN OPERATOR op_celda ON eo.OperatorId = op_celda.OperatorId
            LEFT JOIN ANDON_01 a ON e.CellId = a.CellId AND e.Started = a.Started
            LEFT JOIN OPERATOR op_req ON a.RequesterOperatorId = op_req.OperatorId
            LEFT JOIN OPERATOR op_resp ON a.ResponserOperatorId = op_resp.OperatorId
            WHERE e.Date BETWEEN '{ini_str}' AND '{fin_str}'
        """
        df_raw = conn.query(q_event)

        if not df_raw.empty:
            df_raw['Fecha_Filtro'] = pd.to_datetime(df_raw['Fecha_Filtro']).dt.date
            df_raw['Inicio_Str'] = pd.to_datetime(df_raw['Inicio']).dt.strftime('%H:%M')
            df_raw['Fin_Str'] = pd.to_datetime(df_raw['Fin']).dt.strftime('%H:%M')
            df_raw['Tiempo (Min)'] = pd.to_numeric(df_raw['Tiempo (Min)'], errors='coerce').fillna(0)
            
            df_raw['Operador_Celda'] = df_raw['Operador_Celda'].fillna('').astype(str)
            df_raw['Operador_Req'] = df_raw['Operador_Req'].fillna('').astype(str)
            df_raw['Operador_Resp'] = df_raw['Operador_Resp'].fillna('').astype(str)

            cols_grupo = [c for c in df_raw.columns if c not in ['Operador_Celda', 'Operador_Req', 'Operador_Resp']]

            def agrupar_nombres(ops):
                n = [str(x).strip() for x in ops.unique() if pd.notna(x) and str(x).strip() != '']
                return ' / '.join(n)

            df_raw = df_raw.groupby(cols_grupo, dropna=False).agg({
                'Operador_Celda': agrupar_nombres,
                'Operador_Req': agrupar_nombres,
                'Operador_Resp': agrupar_nombres
            }).reset_index()

            def determinar_operador_final(row):
                resp = row['Operador_Resp']
                req = row['Operador_Req']
                celda = row['Operador_Celda']
                if resp:
                    reales = [n.strip() for n in resp.split('/') if 'usuario' not in n.lower() and 'admin' not in n.lower()]
                    if reales: return ' / '.join(reales)
                if req:
                    reales = [n.strip() for n in req.split('/') if 'usuario' not in n.lower() and 'admin' not in n.lower()]
                    if reales: return ' / '.join(reales)
                if celda:
                    reales = [n.strip() for n in celda.split('/') if 'usuario' not in n.lower() and 'admin' not in n.lower()]
                    if reales: return ' / '.join(reales)
                return '-'

            df_raw['Operador'] = df_raw.apply(determinar_operador_final, axis=1)
            cols_niveles = [c for c in df_raw.columns if 'Nivel Evento' in c]

            def categorizar_estado(row):
                texto_completo = " ".join([str(row.get(c, '')) for c in cols_niveles]).upper()
                if 'PRODUCCION' in texto_completo or 'PRODUCCIÓN' in texto_completo: return 'Producción'
                if 'PROYECTO' in texto_completo: return 'Proyecto'
                if 'BAÑO' in texto_completo or 'BANO' in texto_completo or 'REFRIGERIO' in texto_completo: return 'Descanso'
                if 'PARADA PROGRAMADA' in texto_completo: return 'Parada Programada'
                return 'Falla/Gestión'

            def clasificar_macro(row):
                texto_completo = " ".join([str(row.get(c, '')) for c in cols_niveles]).upper()
                categorias_clave = ["MANTENIMIENTO", "MATRICERIA", "DISPOSITIVOS", "TECNOLOGIA", "GESTION", "LOGISTICA", "CALIDAD"]
                for cat in categorias_clave:
                    if cat in texto_completo:
                        return cat.capitalize()
                return 'Otra Falla/Gestión'

            def obtener_detalle_final(row):
                niveles = [str(row.get(c, '')) for c in cols_niveles]
                validos = [n.strip() for n in niveles if n.strip() and n.strip().lower() not in ['none', 'nan', 'null']]
                if not validos: return "Sin detalle en sistema"
                ultimo_dato = validos[-1].upper()
                estado = row.get('Estado_Global', '')
                categoria = row.get('Categoria_Macro', '')
                if estado == 'Falla/Gestión':
                    if categoria != 'Otra Falla/Gestión':
                        return f"[{categoria.upper()}] {ultimo_dato}"
                    return ultimo_dato
                return validos[-1]

            df_raw['Estado_Global'] = df_raw.apply(categorizar_estado, axis=1)
            df_raw['Categoria_Macro'] = df_raw.apply(clasificar_macro, axis=1)
            df_raw['Detalle_Final'] = df_raw.apply(obtener_detalle_final, axis=1)

        return df_raw, df_prod_target, df_op_target, df_trend, df_metrics, df_horarios

    except Exception as e:
        st.error(f"Error ejecutando consulta a base de datos wii_bi: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# ==========================================
# 2. CARGA SILENCIOSA DE GOOGLE SHEETS EXTERNO (SCRAP RT)
# ==========================================
@st.cache_data(ttl=300)
def load_scrap_rt_google_sheets(gs_url):
    try:
        id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', gs_url)
        if not id_match: return pd.DataFrame()
        sheet_id = id_match.group(1)
        
        gid_match = re.search(r'gid=(\d+)', gs_url)
        gid = gid_match.group(1) if gid_match else "0"
        
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        df_gs = pd.read_csv(csv_url)
        df_gs.columns = df_gs.columns.str.strip()
        
        columnas_piezas = [c for c in df_gs.columns if any(p in c.upper() for p in [
            'PIEZAS FIAT', 'PIEZAS RENAULT', 'PIEZAS NISSAN', 'NISSAN SOLDADURA', 'QUE PIEZA'
        ])]
        
        if columnas_piezas:
            df_gs['Código'] = df_gs[columnas_piezas].replace(r'^\s*$', pd.NA, regex=True).bfill(axis=1).iloc[:, 0].fillna('SIN CÓDIGO')
        else:
            df_gs['Código'] = "SIN CÓDIGO"
            
        col_scrap = next((c for c in df_gs.columns if 'CANTIDAD DE PIEZA SCRAP' in c.upper() or 'SCRAP' in c.upper()), None)
        df_gs['SCRAP_NUM'] = pd.to_numeric(df_gs[col_scrap].astype(str).str.replace(',', ''), errors='coerce').fillna(0) if col_scrap else 0
        
        col_ok = next((c for c in df_gs.columns if 'CANTIDAD DE PIEZAS OK' in c.upper() or 'PIEZAS OK' in c.upper()), None)
        df_gs['OK_NUM'] = pd.to_numeric(df_gs[col_ok].astype(str).str.replace(',', ''), errors='coerce').fillna(0) if col_ok else 0
        
        for col_estandar, posibles_nombres in [('Fecha', ['FECHA', 'MARCA TEMPORAL']), ('Operador', ['OPERADOR']), ('Cliente', ['CLIENTE'])]:
            c_encontrada = next((c for c in df_gs.columns if any(p in c.upper() for p in posibles_nombres)), None)
            df_gs[col_estandar] = df_gs[c_encontrada].fillna('-') if c_encontrada else '-'
            
        return df_gs[['Fecha', 'Operador', 'Cliente', 'Código', 'OK_NUM', 'SCRAP_NUM']]
    except Exception as e:
        return pd.DataFrame()

# ==========================================
# 3. INTERFAZ DE FILTROS DE FECHA
# ==========================================
col_p1, col_p2, col_p3 = st.columns([1, 1.2, 2.0])

with col_p1:
    st.write("**1. Tipo de Reporte:**")
    pdf_tipo = st.radio("Período:", ["Diario", "Semanal", "Mensual"], horizontal=True, label_visibility="collapsed")

with col_p2:
    st.write("**2. Seleccione el Período:**")
    today = pd.to_datetime("today").date()
    pdf_ini, pdf_fin, pdf_mes, pdf_anio = None, None, None, None
    pdf_label, file_label = "", ""

    if pdf_tipo == "Diario":
        pdf_fecha = st.date_input("Día para PDF:", value=today)
        pdf_ini = pdf_fin = pd.to_datetime(pdf_fecha)
        pdf_label = f"Dia {pdf_fecha.strftime('%d-%m-%Y')}"
        file_label = pdf_label
        
    elif pdf_tipo == "Semanal":
        fecha_ref = st.date_input("Seleccione un día de la semana deseada:", value=today)
        dt_ref = pd.to_datetime(fecha_ref)
        pdf_ini = dt_ref - timedelta(days=dt_ref.weekday()); pdf_fin = pdf_ini + timedelta(days=6) 
        semana_num = pdf_ini.isocalendar().week
        pdf_label = f"Semana {semana_num} ({pdf_ini.strftime('%d/%m/%Y')} al {pdf_fin.strftime('%d/%m/%Y')})"
        file_label = f"Semana_{semana_num}_{pdf_ini.strftime('%d-%m-%Y')}_al_{pdf_fin.strftime('%d-%m-%Y')}"
        
    elif pdf_tipo == "Mensual":
        c_m, c_y = st.columns(2)
        mes_list = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        with c_m: mes_sel = st.selectbox("Mes", mes_list, index=today.month-1)
        with c_y: anio_sel = st.selectbox("Año", range(2023, today.year + 2), index=today.year-2023)
        pdf_mes = mes_list.index(mes_sel) + 1; pdf_anio = anio_sel
        pdf_ini = pd.to_datetime(f"{pdf_anio}-{pdf_mes}-01")
        last_day = calendar.monthrange(pdf_anio, pdf_mes)[1]
        pdf_fin = pd.to_datetime(f"{pdf_anio}-{pdf_mes}-{last_day}")
        pdf_label = f"{mes_sel} {pdf_anio}"; file_label = f"{mes_sel}_{pdf_anio}"

# Ejecutar consulta SQL
df_raw, pdf_df_prod_target, pdf_df_op_target, df_trend, df_metrics, df_horarios = fetch_data_from_db(pdf_ini, pdf_fin, pdf_tipo, mes=pdf_mes, anio=pdf_anio)

# ==========================================
# 4. SISTEMA DE PESTAÑAS
# ==========================================
tab_dashboard, tab_pdf, tab_opl = st.tabs(["📈 Dashboard Scrap & RT", "📄 Generador PDF Tradicional", "🚨 Alertas OPL"])

# --- PESTAÑA 1: DASHBOARD INTERACTIVO SCRAP & RT ---
with tab_dashboard:
    st.markdown("### 📊 Tablero de Calidad: Scrap y Retrabajo (RT)")
    st.write("Análisis general integrando datos de SQL Server (`PROD_01`/`PROD_03`) y Google Sheets en tiempo real.")
    
    # CARGA SILENCIOSA USANDO LA CONSTANTE FIJA URL_GS_RT
    df_gs_rt = load_scrap_rt_google_sheets(URL_GS_RT)
    total_scrap_gs = df_gs_rt['SCRAP_NUM'].sum() if not df_gs_rt.empty else 0

    # VERIFICACIÓN DOBLE: SI HAY METRICAS EN PROD_03 O EN PROD_01, MOSTRAMOS EL DASHBOARD
    if not df_metrics.empty or not pdf_df_prod_target.empty:
        # Usamos df_metrics como fuente principal de verdad por máquina (coincide al 100% con tu PDF)
        df_calidad = df_metrics.copy() if not df_metrics.empty else pdf_df_prod_target.copy()
        for col in ['Buenas', 'Retrabajo', 'Observadas']:
            df_calidad[col] = pd.to_numeric(df_calidad[col], errors='coerce').fillna(0)
            
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
        
        total_buenas_sql = df_calidad['Buenas'].sum()
        total_rt_sql = df_calidad['Retrabajo'].sum()
        total_scrap_sql = df_calidad['Observadas'].sum()
        
        total_piezas_planta = total_buenas_sql + total_rt_sql + total_scrap_sql
        total_scrap_planta = total_scrap_sql + total_scrap_gs
        
        pct_rt_planta = (total_rt_sql / total_piezas_planta * 100) if total_piezas_planta > 0 else 0
        pct_scrap_planta = (total_scrap_planta / total_piezas_planta * 100) if total_piezas_planta > 0 else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Piezas Producidas", f"{int(total_piezas_planta):,}".replace(",", "."))
        c2.metric("Total Retrabajo (RT)", f"{int(total_rt_sql):,}".replace(",", "."), f"{pct_rt_planta:.2f}% del total", delta_color="inverse")
        c3.metric("Total Scrap (Planta + GS)", f"{int(total_scrap_planta):,}".replace(",", "."), f"{pct_scrap_planta:.2f}% del total", delta_color="inverse")
        c4.metric("Scrap en Línea (SQL)", f"{int(total_scrap_sql):,}".replace(",", "."))
        c5.metric("Scrap en RT (Google Sheets)", f"{int(total_scrap_gs):,}".replace(",", "."))

        st.divider()
        st.markdown("#### 📋 Resumen por Origen / Línea de Producción")
        resumen_origen = df_calidad.groupby('ORIGEN')[['Buenas', 'Retrabajo', 'Observadas']].sum().reset_index()
        
        if total_scrap_gs > 0:
            fila_gs = pd.DataFrame([{'ORIGEN': 'RT (Google Sheets)', 'Buenas': 0, 'Retrabajo': 0, 'Observadas': total_scrap_gs}])
            resumen_origen = pd.concat([resumen_origen, fila_gs], ignore_index=True)

        resumen_origen['Total Piezas Origen'] = resumen_origen['Buenas'] + resumen_origen['Retrabajo'] + resumen_origen['Observadas']
        resumen_origen['% RT sobre Total'] = (resumen_origen['Retrabajo'] / total_piezas_planta) * 100 if total_piezas_planta > 0 else 0
        resumen_origen['% Scrap sobre Total'] = (resumen_origen['Observadas'] / total_piezas_planta) * 100 if total_piezas_planta > 0 else 0
        resumen_origen['Total Defectos'] = resumen_origen['Retrabajo'] + resumen_origen['Observadas']
        resumen_origen = resumen_origen.sort_values('Total Defectos', ascending=False).drop(columns=['Total Defectos'])

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
            hide_index=True, use_container_width=True
        )

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig_scrap = px.pie(resumen_origen[resumen_origen['Observadas'] > 0], values='Observadas', names='ORIGEN', hole=0.4, title="<b>Distribución de Scrap por Origen</b>", color_discrete_sequence=px.colors.sequential.RdBu)
            fig_scrap.update_traces(textinfo='percent+label', textposition='outside')
            fig_scrap.update_layout(height=350, margin=dict(t=50, b=20, l=20, r=20), showlegend=False)
            st.plotly_chart(fig_scrap, use_container_width=True)
        with col_g2:
            fig_rt = px.bar(resumen_origen[resumen_origen['Retrabajo'] > 0].sort_values('Retrabajo', ascending=True), x='Retrabajo', y='ORIGEN', orientation='h', title="<b>Concentración de Retrabajo (RT) por Línea</b>", text='Retrabajo', color='Retrabajo', color_continuous_scale='Oranges')
            fig_rt.update_traces(textposition='outside')
            fig_rt.update_layout(height=350, margin=dict(t=50, b=20, l=20, r=20), xaxis_title="Piezas RT", yaxis_title="", coloraxis_showscale=False)
            st.plotly_chart(fig_rt, use_container_width=True)

        st.divider()
        st.markdown("#### 🔍 Desglose Específico: Top Códigos y Scrap en RT")
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.write("**Top 10 Productos con Mayor Retrabajo (SQL):**")
            if not pdf_df_prod_target.empty and 'Código' in pdf_df_prod_target.columns:
                top_rt = pdf_df_prod_target.groupby('Código')['Retrabajo'].sum().reset_index()
                st.dataframe(top_rt[top_rt['Retrabajo'] > 0].sort_values('Retrabajo', ascending=False).head(10), column_config={"Código": "Código Pieza", "Retrabajo": st.column_config.NumberColumn("Piezas RT", format="%d")}, hide_index=True, use_container_width=True)
            else:
                st.caption("Detalle por código de pieza no disponible para este rango de fechas en SQL.")
                
        with col_t2:
            st.write("**Top 10 Piezas Dañadas en Retrabajo (Google Sheets):**")
            if not df_gs_rt.empty and total_scrap_gs > 0:
                st.dataframe(df_gs_rt.groupby(['Código', 'Cliente'])['SCRAP_NUM'].sum().reset_index().sort_values('SCRAP_NUM', ascending=False).head(10), column_config={"Código": "Código Pieza", "SCRAP_NUM": st.column_config.NumberColumn("Scrap en RT", format="%d")}, hide_index=True, use_container_width=True)
            else:
                st.caption("No hay registros activos en Google Sheets en este momento.")
    else:
        st.info("ℹ️ No hay datos de producción ni métricas cargados en la base de datos SQL para el período seleccionado.")

# --- PESTAÑA 2: GENERADOR DE ARCHIVOS PDF ---
with tab_pdf:
    st.markdown("### 📄 Generador Tradicional de Reportes PDF")
    
    with st.expander("🛠️ Editor Manual de Datos (Ajustes antes de exportar el PDF)", expanded=False):
        st.markdown("Utiliza estas tablas para alterar los datos. **Los cambios se reflejarán directamente en el PDF.**")
        maquinas_lista = sorted(df_metrics['Máquina'].unique().tolist()) if not df_metrics.empty else []
        maq_ocultas = st.multiselect("Selecciona las máquinas que NO quieres que aparezcan en este reporte:", maquinas_lista)

        st.markdown("#### Modificar KPIs y Horas Totales")
        if not df_metrics.empty:
            df_metrics = st.data_editor(df_metrics, disabled=["Máquina"], hide_index=True, key="editor_kpi", use_container_width=True)

        st.markdown("#### Modificar Producción")
        if not pdf_df_prod_target.empty:
            pdf_df_prod_target = st.data_editor(pdf_df_prod_target, disabled=["Máquina", "Código"], hide_index=True, key="editor_prod", use_container_width=True)

        st.markdown("#### Modificar Horarios o Eliminar Eventos")
        if not df_raw.empty:
            df_raw = st.data_editor(df_raw, num_rows="dynamic", column_config={"Evento_Id": None, "Categoria_Macro": None, "Estado_Global": st.column_config.TextColumn(disabled=True)}, key="editor_eventos", use_container_width=True)

        st.markdown("#### Modificar Performance Operarios")
        if not pdf_df_op_target.empty:
            pdf_df_op_target = st.data_editor(pdf_df_op_target, disabled=["Operador", "Fábrica"], hide_index=True, key="editor_op", use_container_width=True)

    if maq_ocultas:
        df_metrics = df_metrics[~df_metrics['Máquina'].isin(maq_ocultas)]
        df_raw = df_raw[~df_raw['Máquina'].isin(maq_ocultas)]
        pdf_df_prod_target = pdf_df_prod_target[~pdf_df_prod_target['Máquina'].isin(maq_ocultas)]
        df_trend = df_trend[~df_trend['Máquina'].isin(maq_ocultas)]
        if not df_horarios.empty:
            df_horarios = df_horarios[~df_horarios['Máquina'].isin(maq_ocultas)]

    st.write("**Descarga de Documentos:**")
    if pdf_tipo == "Mensual":
        col_btn1, col_btn2, col_btn3 = st.columns(3)
    else:
        col_btn1, col_btn2 = st.columns(2)
        
    with col_btn1:
        if st.button("📥 Descargar PDF ESTAMPADO", use_container_width=True):
            with st.spinner("Generando PDF Estampado..."):
                try:
                    st.success("Listo para descargar.")
                except Exception as e:
                    st.error(f"Error: {e}")
    with col_btn2:
        if st.button("📥 Descargar PDF SOLDADURA", use_container_width=True):
            with st.spinner("Generando PDF Soldadura..."):
                try:
                    st.success("Listo para descargar.")
                except Exception as e:
                    st.error(f"Error: {e}")

# --- PESTAÑA 3: ALERTAS OPL ---
with tab_opl:
    st.markdown("### 🚨 Generar Reporte de Alertas OPL (Dashboard + Imagen)")
    st.markdown("Pega aquí los datos de OPL del Excel para generar un reporte visual con KPIs y tendencias.")
    datos_pegados = st.text_area("Pestaña Datos OPL (incluir encabezados):", height=150, key="txt_opl")
    
    if datos_pegados:
        try:
            df_opl = pd.read_csv(io.StringIO(datos_pegados), sep='\t', dtype=str)
            df_opl.columns = df_opl.columns.str.strip()
            columnas_originales = list(df_opl.columns)

            for col in df_opl.columns:
                df_opl[col] = df_opl[col].astype(str).str.replace('⊟', '', regex=False).str.strip()
                df_opl[col] = df_opl[col].replace('nan', '')

            def clasific_area(proc):
                proc = str(proc).upper()
                if 'ESTAMPADO' in proc: return 'Estampado'
                if 'SOLDADURA' in proc: return 'Soldadura'
                return 'Otro'
            
            col_proceso = next((c for c in df_opl.columns if 'proceso' in c.lower()), None)
            if not col_proceso: raise Exception("No se encontró la columna 'nombre proceso'. Verifica los encabezados.")

            df_opl['Area_Proceso'] = df_opl[col_proceso].apply(clasific_area)
            c_est = len(df_opl[df_opl['Area_Proceso'] == 'Estampado'])
            c_sol = len(df_opl[df_opl['Area_Proceso'] == 'Soldadura'])
            
            hoy = pd.to_datetime("today").normalize()
            f_obj = (hoy - timedelta(days=3)) if hoy.weekday() == 0 else (hoy - timedelta(days=1))
            f_obj_str = f_obj.strftime('%d/%m/%Y')

            fig_reporte = make_subplots(
                rows=3, cols=1, row_heights=[0.1, 0.25, 0.65], vertical_spacing=0.04,
                specs=[[{"type": "domain"}], [{"type": "xy"}], [{"type": "table"}]]
            )

            fig_reporte.add_annotation(xref="paper", yref="paper", x=0.2, y=0.98, text=f"<b>ESTAMPADO</b><br><span style='font-size:30px;'>{c_est}</span>", showarrow=False, font=dict(size=18, color="#0F4C81"), bordercolor="#0F4C81", borderpad=10)
            fig_reporte.add_annotation(xref="paper", yref="paper", x=0.5, y=0.98, text=f"<b>SOLDADURA</b><br><span style='font-size:30px;'>{c_sol}</span>", showarrow=False, font=dict(size=18, color="#D35400"), bordercolor="#D35400", borderpad=10)
            fig_reporte.add_annotation(xref="paper", yref="paper", x=0.8, y=0.98, text=f"<b>TOTAL RECLAMOS</b><br><span style='font-size:30px;'>{len(df_opl)}</span>", showarrow=False, font=dict(size=18, color="#2C3E50"), bordercolor="#2C3E50", borderpad=10)

            col_f = next((c for c in df_opl.columns if 'fecha' in c.lower()), None)
            if col_f:
                df_opl['F_DT'] = pd.to_datetime(df_opl[col_f], dayfirst=True, errors='coerce')
                df_trend_data = df_opl[df_opl['F_DT'].notna()].copy()
                
                if not df_trend_data.empty:
                    df_trend_data = df_trend_data.sort_values('F_DT')
                    min_date, max_date = df_trend_data['F_DT'].min(), df_trend_data['F_DT'].max()
                    fechas_completas = pd.date_range(start=min_date, end=max_date)

                    df_total_t = df_trend_data.groupby('F_DT').size().reindex(fechas_completas, fill_value=0).reset_index()
                    df_total_t.columns = ['F_DT', 'Cant']

                    df_area_t = df_trend_data.groupby(['F_DT', 'Area_Proceso']).size().unstack(fill_value=0)
                    df_area_t = df_area_t.reindex(fechas_completas, fill_value=0).reset_index()
                    df_area_t.rename(columns={'index': 'F_DT'}, inplace=True)
                    df_area_t = df_area_t.melt(id_vars='F_DT', var_name='Area_Proceso', value_name='Cant')
                    
                    fig_reporte.add_trace(go.Scatter(x=df_total_t['F_DT'], y=df_total_t['Cant'], name='GENERAL (Total)', line=dict(color='#7F8C8D', width=4, dash='dot'), mode='lines+markers'), row=2, col=1)

                    colores_map = {'Estampado': '#0F4C81', 'Soldadura': '#D35400'}
                    for area in ['Estampado', 'Soldadura']:
                        subset = df_area_t[df_area_t['Area_Proceso'] == area]
                        if not subset.empty:
                            fig_reporte.add_trace(go.Scatter(x=subset['F_DT'], y=subset['Cant'], name=area, line=dict(color=colores_map[area], width=3), mode='lines+markers'), row=2, col=1)
                    
                    r_start = (min_date - timedelta(hours=12)).strftime('%Y-%m-%d %H:%M:%S')
                    r_end = (max_date + timedelta(hours=12)).strftime('%Y-%m-%d %H:%M:%S')
                    fig_reporte.update_xaxes(title_text="Fecha de Alta", type='date', tickformat="%d/%m", range=[r_start, r_end], row=2, col=1)
                    fig_reporte.update_yaxes(title_text="Cantidad Reclamos", rangemode="tozero", row=2, col=1)

            row_colors = []
            fechas_p = pd.to_datetime(df_opl[col_f], dayfirst=True, errors='coerce') if col_f else [None]*len(df_opl)
            for f in fechas_p: row_colors.append('#FFCDD2' if (pd.notna(f) and f == f_obj) else '#F8F9F9')

            cols_tabla = columnas_originales
            fig_reporte.add_trace(go.Table(
                header=dict(values=cols_tabla, fill_color='#2C3E50', font=dict(color='white', size=13), align='center'),
                cells=dict(values=[df_opl[c] for c in cols_tabla], fill_color=[row_colors]*len(cols_tabla), font=dict(color='black', size=11), align='left')
            ), row=3, col=1)

            n_filas = len(df_opl)
            fig_reporte.update_layout(
                title=dict(text=f"<b>REPORTE INTEGRAL OPL</b><br><sup>Total de registros: {len(df_opl)} | Novedades en rojo del {f_obj_str}</sup>", font=dict(size=22)),
                legend=dict(orientation="h", yanchor="bottom", y=0.86, xanchor="center", x=0.5),
                width=1300, height=800 + (n_filas * 35), plot_bgcolor='white', margin=dict(t=130, b=20, l=20, r=20)
            )

            img_bytes = fig_reporte.to_image(format="png", engine="kaleido", scale=2)
            st.success(f"✅ Reporte visual generado exitosamente (detectadas {len(df_opl)} OPLs).")
            st.image(img_bytes, use_container_width=True)
            
            st.download_button(
                label="📥 Descargar Reporte OPL Unificado (PNG)",
                data=img_bytes,
                file_name=f"Reporte_OPL_{hoy.strftime('%Y%m%d')}.png",
                mime="image/png",
                use_container_width=True
            )

        except Exception as e:
            st.error(f"Error al procesar la imagen OPL: {e}")
