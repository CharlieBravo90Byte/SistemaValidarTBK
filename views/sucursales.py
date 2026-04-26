"""
views/sucursales.py
────────────────────
Vista detallada por sucursal: ventas, comisión, neto, cuotas y descarga.
"""

import streamlit as st
import plotly.express as px
import pandas as pd
from core.database   import get_movimientos, get_sucursales
from core.calculator import enriquecer_movimientos
from core.exporter   import generar_excel_sucursal
from config import COLOR_DEBITO, COLOR_CREDITO


def render_sucursales():
    st.markdown("## 🏪 Análisis por Sucursal")

    periodo = st.session_state.get("periodo_activo")
    if not periodo:
        st.info("📂 Selecciona un período en el menú lateral.")
        return

    with st.spinner("Cargando datos..."):
        df_raw = get_movimientos(periodo, solo_ventas=True)
        if df_raw.empty:
            st.warning(f"⚠️ No hay datos para el período **{periodo}**.")
            return
        df = enriquecer_movimientos(df_raw)

    neto_col = "neto_final" if "neto_final" in df.columns else "neto"

    # ── Selector de sucursal ─────────────────────────────────────────────────
    sucursales_lista = sorted(df["local_nombre"].dropna().unique().tolist())
    sel = st.selectbox(
        "🔍 Seleccionar Sucursal",
        ["— Todas —"] + sucursales_lista,
        index=0,
    )

    if sel == "— Todas —":
        _render_consolidado_todas(df, periodo, neto_col)
    else:
        _render_detalle_sucursal(df, sel, periodo, neto_col)


def _render_consolidado_todas(df: pd.DataFrame, periodo: str, neto_col: str):
    """Vista consolidada de todas las sucursales."""
    st.markdown(f"### 📊 Consolidado todas las sucursales — `{periodo}`")

    grp = df.groupby(["local_nombre", "tipo_archivo"], as_index=False).agg(
        Cantidad      = ("monto_original", "count"),
        Ventas        = ("monto_original", "sum"),
        Comisión      = ("comision_iva", "sum"),
        Neto          = (neto_col, "sum"),
        Cuotas_Pend   = ("cuotas_pendientes", "sum") if "cuotas_pendientes" in df.columns else ("monto_original", "count"),
    )
    grp["Pct Comisión"] = (grp["Comisión"] / grp["Ventas"].replace(0, 1) * 100).round(2)

    # Gráfico
    fig = px.bar(
        grp,
        x="local_nombre",
        y="Ventas",
        color="tipo_archivo",
        barmode="group",
        color_discrete_map={"DEBITO": COLOR_DEBITO, "CREDITO": COLOR_CREDITO},
        labels={"local_nombre": "Sucursal", "Ventas": "Ventas ($)", "tipo_archivo": "Tipo"},
        height=400,
    )
    fig.update_xaxes(tickangle=45)
    fig.update_layout(margin=dict(l=20, r=20, t=30, b=120), legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)

    # Tabla
    tabla = grp.copy()
    tabla["Ventas"]   = tabla["Ventas"].apply(lambda x: f"${x:,.0f}")
    tabla["Comisión"] = tabla["Comisión"].apply(lambda x: f"${x:,.0f}")
    tabla["Neto"]     = tabla["Neto"].apply(lambda x: f"${x:,.0f}")
    tabla["Pct Comisión"] = tabla["Pct Comisión"].apply(lambda x: f"{x:.2f}%")
    tabla.columns = ["Sucursal", "Tipo", "Transacciones", "Ventas", "Comisión", "Neto", "Cuotas Pend.", "% Comisión"]
    st.dataframe(tabla, use_container_width=True, hide_index=True)


def _render_detalle_sucursal(df: pd.DataFrame, sucursal: str, periodo: str, neto_col: str):
    """Vista detallada de una sola sucursal."""
    df_suc = df[df["local_nombre"] == sucursal].copy()

    st.markdown(f"### 🏪 {sucursal}")
    st.caption(f"Período: `{periodo}` | {len(df_suc)} transacciones")

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("💰 Ventas", f"${df_suc['monto_original'].sum():,.0f}")
    with c2:
        st.metric("✅ Neto", f"${df_suc[neto_col].sum():,.0f}")
    with c3:
        st.metric("📉 Comisión", f"${df_suc['comision_iva'].sum():,.0f}")
    with c4:
        if "cuotas_pendientes" in df_suc.columns:
            st.metric("⏳ Cuotas Pend.", f"{int(df_suc['cuotas_pendientes'].sum())}")

    st.markdown("---")

    col_l, col_r = st.columns(2)

    # Gráfico por tipo tarjeta
    with col_l:
        st.markdown("##### Por Tipo de Tarjeta")
        if "tarjeta_nombre" in df_suc.columns:
            tarj = df_suc.groupby("tarjeta_nombre")["monto_original"].sum().reset_index()
            fig_t = px.pie(tarj, names="tarjeta_nombre", values="monto_original",
                           color_discrete_sequence=px.colors.qualitative.Set2, height=280)
            fig_t.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_t, use_container_width=True)

    # Gráfico por tipo cuota
    with col_r:
        st.markdown("##### Por Tipo de Cuota")
        if "cuota_desc" in df_suc.columns:
            cuota = df_suc.groupby("cuota_desc")["monto_original"].sum().reset_index()
            fig_c = px.bar(cuota, x="cuota_desc", y="monto_original",
                           color="cuota_desc",
                           color_discrete_sequence=px.colors.qualitative.Pastel,
                           labels={"cuota_desc": "Cuota", "monto_original": "$"},
                           height=280)
            fig_c.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_c, use_container_width=True)

    # Flujo por fecha de abono
    st.markdown("##### 📅 Abonos por Fecha")
    if "fecha_abono" in df_suc.columns:
        diario = df_suc.groupby(["fecha_abono", "tipo_archivo"], as_index=False).agg(
            total=("monto_abono", "sum")
        )
        diario["fecha_abono"] = pd.to_datetime(diario["fecha_abono"], errors="coerce")
        diario = diario.dropna(subset=["fecha_abono"])
        if not diario.empty:
            fig_d = px.bar(
                diario, x="fecha_abono", y="total", color="tipo_archivo",
                barmode="stack",
                color_discrete_map={"DEBITO": COLOR_DEBITO, "CREDITO": COLOR_CREDITO},
                labels={"total": "Abono ($)", "fecha_abono": "Fecha", "tipo_archivo": "Tipo"},
                height=280,
            )
            fig_d.update_layout(margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig_d, use_container_width=True)

    st.markdown("---")

    # Detalle de transacciones
    with st.expander("📋 Ver detalle de transacciones", expanded=False):
        cols_show = [
            "tipo_archivo", "fecha_venta", "tarjeta_nombre", "cuota_desc",
            "cuota_actual", "cuota_total", "monto_original", "monto_abono",
            "comision_iva", neto_col, "fecha_abono", "codigo_autorizacion"
        ]
        cols_ok = [c for c in cols_show if c in df_suc.columns]
        st.dataframe(df_suc[cols_ok], use_container_width=True, hide_index=True)

    # Descarga
    st.markdown("---")
    excel_bytes = generar_excel_sucursal(df_suc, sucursal, periodo)
    st.download_button(
        label="📥 Descargar Excel — Esta Sucursal",
        data=excel_bytes,
        file_name=f"TBK_{periodo}_{sucursal.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
