"""
views/reporte_sucursal.py
─────────────────────────
Vista que reproduce el formato del Excel descargable:
  - Ingresos (por tipo: débito, crédito, CPC, devoluciones)
  - Egresos
  - Gastos administración
  - Pendiente por cobrar (cuotas)
  - Total general
"""

import streamlit as st
import pandas as pd
from core.database import get_movimientos
from core.calculator import enriquecer_movimientos


def render_reporte_sucursal():
    st.markdown("## 📑 Reporte Sucursal (Formato Excel)")

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

    # Separar CPC, Crédito, Débito, Devoluciones
    df["categoria"] = df.apply(lambda row: (
        "CPC" if (str(row.get("tipo_cuota", "")).upper() in ["CFE", "CPC", "CIC"] or str(row.get("tipo_tarjeta", "")).upper() == "CFE")
        else row["tipo_archivo"]
    ), axis=1)

    sucursales = sorted(df["local_nombre"].dropna().unique().tolist())
    sel = st.selectbox("Sucursal", sucursales, index=0)
    df_suc = df[df["local_nombre"] == sel].copy()

    # Ingresos
    ingresos = df_suc[df_suc["tipo_transaccion"] == "Venta"].groupby("categoria")["monto_original"].sum().to_dict()
    devoluciones = df_suc[df_suc["tipo_transaccion"].str.contains("Devol", case=False, na=False)]["monto_original"].sum()
    # Egresos (anulaciones, retenciones, etc.)
    egresos = df_suc[df_suc["tipo_transaccion"].str.contains("Anul|Reten", case=False, na=False)]["monto_original"].sum()
    # Gastos admin (comisión)
    gastos_admin = df_suc["comision_iva"].sum()
    # Pendiente por cobrar (cuotas)
    pendiente = df_suc["cuotas_pendientes"].sum() if "cuotas_pendientes" in df_suc.columns else 0
    # Total general
    total_general = sum(ingresos.values()) - devoluciones - egresos - gastos_admin

    st.markdown(f"### {sel}")
    st.write("#### Ingresos")
    st.write(ingresos)
    st.write(f"**Devoluciones:** ${devoluciones:,.0f}")
    st.write(f"**Egresos:** ${egresos:,.0f}")
    st.write(f"**Gastos administración:** ${gastos_admin:,.0f}")
    st.write(f"**Pendiente por cobrar:** ${pendiente:,.0f}")
    st.write(f"**Total general:** ${total_general:,.0f}")

    # Tabla detalle
    with st.expander("📋 Ver detalle de movimientos", expanded=False):
        st.dataframe(df_suc, use_container_width=True, hide_index=True)
