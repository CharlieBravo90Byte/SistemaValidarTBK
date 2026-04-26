"""
app.py
───────
Entrada principal del sistema de conciliación Transbank.
Ejecutar con: streamlit run app.py
"""

import os
import sys
import streamlit as st

# Agrega el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import init_db, get_periodos
from views.upload     import render_upload
from views.dashboard  import render_dashboard
from views.sucursales import render_sucursales
from views.pendientes import render_pendientes
from views.softland   import render_softland

# ── Configuración de página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Sistema Conciliación Transbank",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Sistema de Conciliación Transbank",
    },
)

# ── CSS personalizado ─────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Layout responsive: sin scroll horizontal */
    html, body, [data-testid="stAppViewContainer"], .main, .block-container {
        overflow-x: hidden !important;
        max-width: 100% !important;
    }
    .block-container {
        padding-top: 1.2rem;
        padding-left: clamp(0.6rem, 2vw, 2rem);
        padding-right: clamp(0.6rem, 2vw, 2rem);
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d2137 0%, #1f4e79 60%, #2d6a9f 100%);
    }
    [data-testid="stSidebar"] * {
        color: #e8f4ff !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        font-size: 1.05rem;
        padding: 4px 0;
    }

    /* Métricas */
    [data-testid="metric-container"] {
        background: #f0f6ff;
        border-radius: 10px;
        padding: 12px 16px;
        border-left: 4px solid #2196f3;
        min-width: 0;
    }
    [data-testid="stMetricLabel"]  { font-size: 0.85rem; color: #546e7a !important; }
    [data-testid="stMetricValue"]  { font-size: clamp(1.1rem, 2vw, 1.6rem); font-weight: 700; }
    [data-testid="stMetricDelta"]  { font-size: 0.8rem; }

    /* Dataframes responsivos */
    .stDataFrame, [data-testid="stDataFrame"] {
        border-radius: 8px;
        overflow: auto;
        max-width: 100%;
    }
    .stDataFrame table { table-layout: auto; width: 100% !important; }

    /* Imágenes y plotly */
    .stPlotlyChart, .element-container img { max-width: 100% !important; height: auto !important; }

    /* Encabezados */
    h2 { color: #1f4e79; border-bottom: 2px solid #2196f3; padding-bottom: 6px; }
    h3 { color: #2d6a9f; }

    /* Botón principal */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1f4e79, #2196f3);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        font-weight: 600;
        font-size: 1rem;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #163a5e, #1976d2);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(33,150,243,0.3);
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: #f0f6ff;
        padding: 6px;
        border-radius: 8px;
        flex-wrap: wrap;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        padding: 6px 18px;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: #2196f3 !important;
        color: white !important;
    }

    /* Expander */
    .streamlit-expanderHeader {
        background: #f0f6ff;
        border-radius: 8px;
        font-weight: 600;
    }

    /* Alerts */
    .stSuccess { border-radius: 8px; }
    .stWarning { border-radius: 8px; }
    .stError   { border-radius: 8px; }
    .stInfo    { border-radius: 8px; }

    /* Mobile */
    @media (max-width: 640px) {
        h1 { font-size: 1.4rem; }
        h2 { font-size: 1.2rem; }
        h3 { font-size: 1.05rem; }
        [data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
    }
</style>
""", unsafe_allow_html=True)

# ── Inicialización DB ─────────────────────────────────────────────────────────
init_db()

# ── Menú lateral ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center; padding: 10px 0 20px;'>
        <div style='font-size:2.5rem;'>💳</div>
        <div style='font-size:1.1rem; font-weight:700; color:#90caf9;'>Transbank System</div>
        <div style='font-size:0.75rem; color:#78909c;'>Conciliación mensual</div>
    </div>
    """, unsafe_allow_html=True)

    pagina = st.radio(
        "nav",
        options=[
            "📤 Cargar Archivos",
            "📊 Dashboard",
            "🏪 Por Sucursal",
            "⏳ Pendientes",
            "📁 Softland",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # ── Selector de período ───────────────────────────────────────────────────
    st.markdown("##### 📅 Período Activo")
    periodos = get_periodos()

    if periodos:
        opts = [p["periodo"] for p in periodos]
        idx_default = 0

        # Si ya hay un período activo en sesión, mantenerlo
        if "periodo_activo" in st.session_state and st.session_state["periodo_activo"] in opts:
            idx_default = opts.index(st.session_state["periodo_activo"])

        periodo_sel = st.selectbox(
            "Período",
            options=opts,
            index=idx_default,
            label_visibility="collapsed",
        )
        st.session_state["periodo_activo"] = periodo_sel

        # Info del período seleccionado
        p_data = next((p for p in periodos if p["periodo"] == periodo_sel), {})
        if p_data.get("total_ventas"):
            st.caption(f"💰 ${p_data['total_ventas']:,.0f}")
    else:
        st.info("Sin períodos cargados")
        if "periodo_activo" not in st.session_state:
            st.session_state["periodo_activo"] = None

    st.markdown("---")
    st.caption("Sistema Conciliación Transbank")

# ── Enrutamiento ──────────────────────────────────────────────────────────────
if pagina == "📤 Cargar Archivos":
    render_upload()
elif pagina == "📊 Dashboard":
    render_dashboard()
elif pagina == "🏪 Por Sucursal":
    render_sucursales()
elif pagina == "⏳ Pendientes":
    render_pendientes()
elif pagina == "📁 Softland":
    render_softland()
