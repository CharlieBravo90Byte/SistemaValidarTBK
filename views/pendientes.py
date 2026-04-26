"""
views/pendientes.py
────────────────────
Vista de movimientos pendientes:
  - Tab 1: Pendientes simples (sin match / SC sin conciliar)
  - Tab 2: Cuotas pendientes (cuotas futuras por cobrar)
  - Tab 3: Proyección de flujo futuro
"""

import streamlit as st
import plotly.express as px
import pandas as pd
from core.database    import get_movimientos
from core.calculator  import enriquecer_movimientos, calcular_proyeccion_cuotas
from config import COLOR_ALERTA, COLOR_PELIGRO


def render_pendientes():
    st.markdown("## ⏳ Pendientes y Cuotas por Cobrar")

    periodo = st.session_state.get("periodo_activo")
    if not periodo:
        st.info("📂 Selecciona un período en el menú lateral.")
        return

    with st.spinner("Cargando pendientes..."):
        df_raw = get_movimientos(periodo, solo_ventas=True)
        if df_raw.empty:
            st.warning(f"⚠️ No hay datos para el período **{periodo}**.")
            return
        df = enriquecer_movimientos(df_raw)

    neto_col = "neto_final" if "neto_final" in df.columns else "neto"

    # ── KPIs rápidos ─────────────────────────────────────────────────────────
    cuotas_activas = df[df.get("cuota_total", pd.Series(dtype=int)) > 1] if "cuota_total" in df.columns else pd.DataFrame()
    cuotas_pend    = df[(df.get("cuota_total", 1) > 1) & (df.get("cuota_actual", 1) < df.get("cuota_total", 1))] if "cuota_total" in df.columns else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("📋 Total Transacciones", f"{len(df):,}")
    with c2:
        n_cuotas = len(cuotas_activas) if not cuotas_activas.empty else 0
        st.metric("🔢 En Cuotas", f"{n_cuotas:,}",
                  help="Transacciones con más de 1 cuota")
    with c3:
        n_pend = len(cuotas_pend) if not cuotas_pend.empty else 0
        st.metric("⏳ Cuotas Pendientes", f"{n_pend:,}",
                  help="Cuotas que aún no han sido abonadas")
    with c4:
        monto_pend = cuotas_pend[neto_col].sum() if not cuotas_pend.empty and neto_col in cuotas_pend.columns else 0
        st.metric("💰 Monto Pend. Cuotas", f"${monto_pend:,.0f}")

    st.markdown("---")

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs([
        "⏳ Cuotas Pendientes",
        "📈 Proyección Futura",
        "🔍 Detalle por Tipo Cuota",
    ])

    with tab1:
        _render_cuotas_pendientes(df, neto_col)

    with tab2:
        _render_proyeccion(df)

    with tab3:
        _render_detalle_tipo_cuota(df, neto_col)


def _render_cuotas_pendientes(df: pd.DataFrame, neto_col: str):
    """Cuotas futuras por cobrar."""
    st.markdown("### ⏳ Cuotas Pendientes de Cobro")
    st.caption("Ventas en cuotas donde aún quedan cuotas por recibir del período siguiente.")

    if "cuota_total" not in df.columns:
        st.info("Sin información de cuotas disponible.")
        return

    pend = df[
        (df["cuota_total"] > 1) &
        (df["cuota_actual"] < df["cuota_total"])
    ].copy()

    if pend.empty:
        st.success("✅ No hay cuotas pendientes para este período.")
        return

    # Filtros
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        tipos_cuota = ["Todos"] + sorted(pend["tipo_cuota"].unique().tolist())
        tipo_sel = st.selectbox("Filtrar por tipo cuota", tipos_cuota, key="pend_tipo")
    with col_f2:
        sucursales = ["Todas"] + sorted(pend["local_nombre"].dropna().unique().tolist())
        suc_sel = st.selectbox("Filtrar por sucursal", sucursales, key="pend_suc")

    if tipo_sel != "Todos":
        pend = pend[pend["tipo_cuota"] == tipo_sel]
    if suc_sel != "Todas":
        pend = pend[pend["local_nombre"] == suc_sel]

    # Resumen por sucursal
    grp = pend.groupby(["local_nombre", "tipo_cuota"], as_index=False).agg(
        Transacciones  = ("monto_original", "count"),
        Ventas_Orig    = ("monto_original", "sum"),
        Cuotas_Rest    = ("cuotas_pendientes", "sum"),
        Monto_Pend     = (neto_col, "sum"),
    )
    grp["Ventas_Orig"] = grp["Ventas_Orig"].apply(lambda x: f"${x:,.0f}")
    grp["Monto_Pend"]  = grp["Monto_Pend"].apply(lambda x: f"${x:,.0f}")
    grp.columns = ["Sucursal", "Tipo Cuota", "Transacciones", "Venta Original", "Cuotas Restantes", "Monto Pendiente"]
    st.dataframe(grp, use_container_width=True, hide_index=True)

    # Gráfico por sucursal
    fig = px.bar(
        pend.groupby("local_nombre")[neto_col].sum().reset_index(),
        x=neto_col, y="local_nombre", orientation="h",
        color_discrete_sequence=[COLOR_ALERTA],
        labels={neto_col: "Monto Pendiente ($)", "local_nombre": "Sucursal"},
        height=max(300, len(pend["local_nombre"].unique()) * 35),
    )
    fig.update_layout(yaxis=dict(autorange="reversed"), margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Detalle expandible
    with st.expander("📋 Ver todas las transacciones pendientes", expanded=False):
        cols_show = [
            "local_nombre", "tipo_archivo", "tipo_cuota",
            "cuota_actual", "cuota_total", "cuotas_pendientes",
            "monto_original", neto_col, "fecha_venta", "fecha_abono",
            "codigo_autorizacion", "tipo_tarjeta"
        ]
        cols_ok = [c for c in cols_show if c in pend.columns]
        st.dataframe(pend[cols_ok], use_container_width=True, hide_index=True)

    # Descarga CSV
    csv_bytes = pend.to_csv(index=False, sep=";").encode("latin-1", errors="replace")
    st.download_button(
        "📥 Descargar Pendientes CSV",
        data=csv_bytes,
        file_name=f"Pendientes_{st.session_state.get('periodo_activo', 'sin_periodo')}.csv",
        mime="text/csv",
        use_container_width=True,
    )


def _render_proyeccion(df: pd.DataFrame):
    """Proyección de cuotas futuras."""
    st.markdown("### 📈 Proyección de Flujo Futuro")
    st.caption("Montos estimados por cobrar en períodos siguientes según cuotas activas.")

    proyeccion = calcular_proyeccion_cuotas(df)

    if proyeccion.empty:
        st.success("✅ No hay cuotas activas con proyección futura.")
        return

    # Resumen global
    col1, col2 = st.columns(2)
    with col1:
        st.metric("💰 Total por Cobrar", f"${proyeccion['monto_por_cobrar'].sum():,.0f}")
    with col2:
        st.metric("📋 Transacciones", f"{len(proyeccion):,}")

    # Por sucursal
    grp_proy = proyeccion.groupby("local_nombre", as_index=False).agg(
        por_cobrar  = ("monto_por_cobrar", "sum"),
        ya_abonado  = ("monto_ya_abonado", "sum"),
        transacciones = ("monto_original", "count"),
    )

    fig = px.bar(
        grp_proy.sort_values("por_cobrar", ascending=False),
        x="local_nombre", y="por_cobrar",
        color_discrete_sequence=["#ff9800"],
        labels={"local_nombre": "Sucursal", "por_cobrar": "Por Cobrar ($)"},
        height=350,
    )
    fig.update_xaxes(tickangle=45)
    fig.update_layout(margin=dict(l=20, r=20, t=20, b=100))
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        grp_proy.rename(columns={
            "local_nombre": "Sucursal",
            "por_cobrar": "Por Cobrar ($)",
            "ya_abonado": "Ya Abonado ($)",
            "transacciones": "Transacciones"
        }),
        use_container_width=True,
        hide_index=True,
    )


def _render_detalle_tipo_cuota(df: pd.DataFrame, neto_col: str):
    """Análisis por tipo de cuota."""
    st.markdown("### 🔍 Análisis por Tipo de Cuota")

    if "tipo_cuota" not in df.columns:
        st.info("Sin información de cuotas.")
        return

    grp = df.groupby(["tipo_cuota", "cuota_desc" if "cuota_desc" in df.columns else "tipo_cuota"],
                     as_index=False).agg(
        Cantidad    = ("monto_original", "count"),
        Ventas      = ("monto_original", "sum"),
        Neto        = (neto_col, "sum"),
    )
    grp["Ventas"] = grp["Ventas"].apply(lambda x: f"${x:,.0f}")
    grp["Neto"]   = grp["Neto"].apply(lambda x: f"${x:,.0f}")

    st.dataframe(grp, use_container_width=True, hide_index=True)

    # Gráfico
    raw_grp = df.groupby("tipo_cuota", as_index=False)["monto_original"].sum()
    fig = px.pie(
        raw_grp, names="tipo_cuota", values="monto_original",
        color_discrete_sequence=px.colors.qualitative.Set3,
        height=300,
    )
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
