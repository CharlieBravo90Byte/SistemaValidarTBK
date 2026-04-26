"""
views/dashboard.py
───────────────────
Dashboard principal con KPIs globales y gráficos del período.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from core.database    import get_movimientos, get_periodos
from core.calculator  import enriquecer_movimientos, consolidar_global, resumen_por_fecha_abono
from config import COLOR_DEBITO, COLOR_CREDITO, COLOR_PRIMARIO


def render_dashboard():
    st.markdown("## 📊 Dashboard — Análisis del Período")

    periodo = st.session_state.get("periodo_activo")

    if not periodo:
        periodos = get_periodos()
        if periodos:
            periodo = periodos[0]["periodo"]
            st.session_state["periodo_activo"] = periodo
        else:
            st.info("📂 No hay datos cargados. Ve a **Cargar Archivos** para comenzar.")
            return

    # ── Cargar y enriquecer datos ────────────────────────────────────────────
    with st.spinner("Cargando datos..."):
        df_raw = get_movimientos(periodo, solo_ventas=True)
        if df_raw.empty:
            st.warning(f"⚠️ No hay datos de ventas para el período **{periodo}**.")
            return
        df = enriquecer_movimientos(df_raw)

    resumen = consolidar_global(df)
    neto_col = "neto_final" if "neto_final" in df.columns else "neto"

    # ── KPIs principales ─────────────────────────────────────────────────────
    st.markdown(f"### 📅 Período: `{periodo}` — {resumen.get('sucursales_activas', 0)} sucursales")
    st.markdown("---")

    k1, k2, k3, k4 = st.columns(4)

    with k1:
        ventas = resumen.get("total_ventas", 0)
        st.metric(
            "💰 Total Ventas",
            f"${ventas:,.0f}",
            help="Suma de montos originales de ventas"
        )
    with k2:
        neto = resumen.get("total_neto", 0)
        st.metric(
            "✅ Total Neto Abono",
            f"${neto:,.0f}",
            help="Monto efectivo después de comisiones"
        )
    with k3:
        comision = resumen.get("total_comision", 0)
        pct = comision / ventas * 100 if ventas > 0 else 0
        st.metric(
            "📉 Total Comisión",
            f"${comision:,.0f}",
            delta=f"-{pct:.2f}% sobre ventas",
            delta_color="inverse",
            help="Comisiones + IVA cobradas por Transbank"
        )
    with k4:
        txns = resumen.get("total_transacciones", 0)
        st.metric(
            "🔢 Transacciones",
            f"{txns:,}",
            help="Total de ventas procesadas en el período"
        )

    st.markdown("---")

    # ── Gráfico: Débito vs Crédito ────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### 💳 Débito vs Crédito")
        debito  = resumen.get("total_debito", 0)
        credito = resumen.get("total_credito", 0)

        fig_pie = go.Figure(data=[go.Pie(
            labels=["Débito", "Crédito"],
            values=[debito, credito],
            hole=0.5,
            marker_colors=[COLOR_DEBITO, COLOR_CREDITO],
            textinfo="percent+label",
        )])
        fig_pie.update_layout(
            showlegend=True,
            height=320,
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        col_d, col_c = st.columns(2)
        with col_d:
            st.metric("💚 Débito", f"${debito:,.0f}")
        with col_c:
            st.metric("🔵 Crédito", f"${credito:,.0f}")

    # ── Gráfico: Flujo diario de abonos ──────────────────────────────────────
    with col_right:
        st.markdown("#### 📅 Abonos por Fecha")
        diario = resumen_por_fecha_abono(df)

        if not diario.empty and "fecha_abono" in diario.columns:
            diario["fecha_abono"] = pd.to_datetime(diario["fecha_abono"], errors="coerce")
            diario = diario.dropna(subset=["fecha_abono"])

            fig_bar = px.bar(
                diario,
                x="fecha_abono",
                y="total_abono",
                color="tipo_archivo",
                barmode="stack",
                color_discrete_map={"DEBITO": COLOR_DEBITO, "CREDITO": COLOR_CREDITO},
                labels={"total_abono": "Monto ($)", "fecha_abono": "Fecha", "tipo_archivo": "Tipo"},
                height=320,
            )
            fig_bar.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02)
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Sin datos de fecha de abono disponibles.")

    st.markdown("---")

    # ── Top 10 Sucursales ────────────────────────────────────────────────────
    st.markdown("#### 🏪 Top Sucursales por Venta")
    top_suc = (
        df.groupby("local_nombre", as_index=False)["monto_original"]
        .sum()
        .sort_values("monto_original", ascending=False)
        .head(12)
    )
    if not top_suc.empty:
        fig_suc = px.bar(
            top_suc,
            x="monto_original",
            y="local_nombre",
            orientation="h",
            color="monto_original",
            color_continuous_scale=["#e3f2fd", COLOR_PRIMARIO],
            labels={"monto_original": "Ventas ($)", "local_nombre": "Sucursal"},
            height=400,
        )
        fig_suc.update_layout(
            margin=dict(l=20, r=20, t=20, b=20),
            coloraxis_showscale=False,
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_suc, use_container_width=True)

    st.markdown("---")

    # ── Distribución por tipo de cuota ───────────────────────────────────────
    col_q, col_t = st.columns(2)

    with col_q:
        st.markdown("#### 🔢 Distribución por Tipo Cuota")
        if "cuota_desc" in df.columns:
            cuota_grp = df.groupby("cuota_desc")["monto_original"].sum().reset_index()
            fig_cuota = px.pie(
                cuota_grp, names="cuota_desc", values="monto_original",
                color_discrete_sequence=px.colors.qualitative.Set2,
                height=300,
            )
            fig_cuota.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_cuota, use_container_width=True)

    with col_t:
        st.markdown("#### 💳 Por Tipo de Tarjeta")
        if "tarjeta_nombre" in df.columns:
            tarj_grp = df.groupby("tarjeta_nombre")["monto_original"].sum().reset_index()
            fig_tarj = px.bar(
                tarj_grp, x="tarjeta_nombre", y="monto_original",
                color="tarjeta_nombre",
                color_discrete_sequence=px.colors.qualitative.Pastel,
                labels={"monto_original": "Ventas ($)", "tarjeta_nombre": "Tarjeta"},
                height=300,
            )
            fig_tarj.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_tarj, use_container_width=True)

    st.markdown("---")

    # ── Tabla resumen por sucursal ────────────────────────────────────────────
    st.markdown("#### 📋 Tabla Consolidada por Sucursal")
    tabla = df.groupby(["local_nombre", "tipo_archivo"], as_index=False).agg(
        Cantidad      = ("monto_original", "count"),
        Ventas        = ("monto_original", "sum"),
        Comisión      = ("comision_iva", "sum"),
        Neto          = (neto_col, "sum"),
    )
    tabla["Ventas"]   = tabla["Ventas"].apply(lambda x: f"${x:,.0f}")
    tabla["Comisión"] = tabla["Comisión"].apply(lambda x: f"${x:,.0f}")
    tabla["Neto"]     = tabla["Neto"].apply(lambda x: f"${x:,.0f}")
    tabla.columns = ["Sucursal", "Tipo", "Transacciones", "Ventas", "Comisión", "Neto"]
    st.dataframe(tabla, use_container_width=True, hide_index=True)
