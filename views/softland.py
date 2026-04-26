"""
views/softland.py
──────────────────
Vista de generación y descarga de archivos Softland:
  - CSV Centralización mensual
  - CSV Diario por fecha de abono
  - Excel reporte global completo
"""

import streamlit as st
import pandas as pd
from core.database  import get_movimientos
from core.calculator import enriquecer_movimientos
from core.exporter  import (
    generar_softland_centralizacion,
    generar_softland_diario,
    generar_excel_global,
)


def render_softland():
    st.markdown("## 📁 Exportación Softland y Reportes")
    st.markdown("Genera los archivos listos para importar en Softland y el reporte global de gestión.")

    periodo = st.session_state.get("periodo_activo")
    if not periodo:
        st.info("📂 Selecciona un período en el menú lateral.")
        return

    with st.spinner("Preparando datos para exportación..."):
        df_raw = get_movimientos(periodo, solo_ventas=True)
        if df_raw.empty:
            st.warning(f"⚠️ No hay datos para el período **{periodo}**.")
            return
        df = enriquecer_movimientos(df_raw)

    neto_col = "neto_final" if "neto_final" in df.columns else "neto"

    st.markdown(f"### 📅 Período: `{periodo}`")
    st.markdown("---")

    # ── Configuración de Softland ────────────────────────────────────────────
    with st.expander("⚙️ Configuración del comprobante Softland", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            n_comprobante = st.text_input("N° Comprobante", value="001")
            tipo_comprobante = st.text_input("Tipo Comprobante", value="VC")
        with col2:
            cuenta_por_cobrar = st.text_input("Cuenta Por Cobrar (Debe)",  value="11050001")
            cuenta_ingresos   = st.text_input("Cuenta Ingresos (Haber)",   value="41100001")
            cuenta_comision   = st.text_input("Cuenta Comisión (Debe)",    value="64100001")

    st.markdown("---")

    # ── Resumen previo ────────────────────────────────────────────────────────
    st.markdown("### 📊 Resumen antes de exportar")

    grp = df.groupby(["local_nombre", "tipo_archivo"], as_index=False).agg(
        Transacciones  = ("monto_original", "count"),
        Ventas         = ("monto_original", "sum"),
        Comisión       = ("comision_iva", "sum"),
        Neto           = (neto_col, "sum"),
    )
    grp["Ventas"]   = grp["Ventas"].apply(lambda x: f"${x:,.0f}")
    grp["Comisión"] = grp["Comisión"].apply(lambda x: f"${x:,.0f}")
    grp["Neto"]     = grp["Neto"].apply(lambda x: f"${x:,.0f}")
    grp.columns = ["Sucursal", "Tipo", "Transacciones", "Ventas", "Comisión", "Neto"]
    st.dataframe(grp, use_container_width=True, hide_index=True)

    # Totales
    total_ventas   = df["monto_original"].sum()
    total_comision = df["comision_iva"].sum()
    total_neto     = df[neto_col].sum()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("💰 Total Ventas",   f"${total_ventas:,.0f}")
    with col2:
        st.metric("📉 Total Comisión", f"${total_comision:,.0f}")
    with col3:
        st.metric("✅ Total Neto",     f"${total_neto:,.0f}")

    st.markdown("---")

    # ── Botones de descarga ───────────────────────────────────────────────────
    st.markdown("### 📥 Descargar Archivos")

    col_a, col_b, col_c = st.columns(3)

    # ── Softland Centralización ───────────────────────────────────────────────
    with col_a:
        st.markdown("#### 📄 Softland Centralización")
        st.caption("Asiento mensual consolidado por sucursal")

        if st.button("🔄 Generar CSV Centralización", use_container_width=True, key="gen_central"):
            with st.spinner("Generando..."):
                csv_bytes = generar_softland_centralizacion(df, periodo, n_comprobante)

            if csv_bytes:
                st.download_button(
                    label="📥 Descargar CSV Centralización",
                    data=csv_bytes,
                    file_name=f"Softland_Centralizacion_{periodo}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="dl_central",
                )
                _preview_csv(csv_bytes, "Previsualización Centralización")
            else:
                st.error("No se pudo generar el archivo.")

    # ── Softland Diario ───────────────────────────────────────────────────────
    with col_b:
        st.markdown("#### 📄 Softland Diario")
        st.caption("Asiento diario por fecha de abono × sucursal")

        if st.button("🔄 Generar CSV Diario", use_container_width=True, key="gen_diario"):
            with st.spinner("Generando..."):
                csv_bytes_d = generar_softland_diario(df, periodo)

            if csv_bytes_d:
                st.download_button(
                    label="📥 Descargar CSV Diario",
                    data=csv_bytes_d,
                    file_name=f"Softland_Diario_{periodo}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="dl_diario",
                )
                _preview_csv(csv_bytes_d, "Previsualización Diario")
            else:
                st.error("No se pudo generar el archivo.")

    # ── Excel Global ──────────────────────────────────────────────────────────
    with col_c:
        st.markdown("#### 📊 Excel Global")
        st.caption("Reporte completo con todas las hojas")

        if st.button("🔄 Generar Excel Global", use_container_width=True, key="gen_excel"):
            with st.spinner("Generando Excel..."):
                excel_bytes = generar_excel_global(df, periodo)

            if excel_bytes:
                st.download_button(
                    label="📥 Descargar Excel Global",
                    data=excel_bytes,
                    file_name=f"Reporte_Transbank_{periodo}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dl_excel",
                )
                st.success("✅ Excel global generado correctamente.")
            else:
                st.error("No se pudo generar el Excel.")

    st.markdown("---")

    # ── Exportación Débito y Crédito por separado ─────────────────────────────
    st.markdown("### 📂 Exportar por Tipo")
    col_d2, col_c2 = st.columns(2)

    with col_d2:
        df_deb = df[df["tipo_archivo"] == "DEBITO"]
        st.metric("💚 Débito", f"${df_deb['monto_original'].sum():,.0f}", f"{len(df_deb)} transacciones")
        if not df_deb.empty:
            csv_d = df_deb.to_csv(index=False, sep=";").encode("latin-1", errors="replace")
            st.download_button(
                "📥 CSV Débito completo",
                data=csv_d,
                file_name=f"Debito_{periodo}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with col_c2:
        df_cred = df[df["tipo_archivo"] == "CREDITO"]
        st.metric("🔵 Crédito", f"${df_cred['monto_original'].sum():,.0f}", f"{len(df_cred)} transacciones")
        if not df_cred.empty:
            csv_c = df_cred.to_csv(index=False, sep=";").encode("latin-1", errors="replace")
            st.download_button(
                "📥 CSV Crédito completo",
                data=csv_c,
                file_name=f"Credito_{periodo}.csv",
                mime="text/csv",
                use_container_width=True,
            )


def _preview_csv(csv_bytes: bytes, titulo: str):
    """Muestra una previsualización del CSV generado."""
    with st.expander(f"🔍 {titulo}", expanded=False):
        try:
            text = csv_bytes.decode("latin-1", errors="replace")
            lines = text.splitlines()
            st.code("\n".join(lines[:20]), language="")
            if len(lines) > 20:
                st.caption(f"... y {len(lines) - 20} filas más.")
        except Exception:
            st.warning("No se puede previsualizar el archivo.")
