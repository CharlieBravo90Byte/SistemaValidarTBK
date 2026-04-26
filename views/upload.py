"""
views/upload.py
────────────────
Página de carga de los 3 archivos CSV de Transbank.
Parsea, valida y guarda en SQLite.
"""

import os
import streamlit as st
import pandas as pd
from core.parser   import parse_transbank_csv, parse_cartola_movimientos
from core.database import (
    upsert_periodo, save_movimientos,
    sync_sucursales, periodo_tiene_datos
)
from core.calculator import enriquecer_movimientos


_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "TemplateTransbankV032026.xlsm",
)


def _render_template_download():
    """Botón para descargar la plantilla Excel del flujo manual."""
    if not os.path.exists(_TEMPLATE_PATH):
        return
    with open(_TEMPLATE_PATH, "rb") as fh:
        data = fh.read()
    st.download_button(
        label="⬇️ Descargar plantilla Excel (flujo manual)",
        data=data,
        file_name="TemplateTransbankV032026.xlsm",
        mime="application/vnd.ms-excel.sheet.macroEnabled.12",
        use_container_width=True,
        help="Descarga la plantilla Excel original con macros para procesar los archivos manualmente.",
    )


def render_upload():
    st.markdown("## 📤 Cargar Archivos Transbank")
    st.markdown("Sube los **3 archivos CSV** descargados desde el portal Transbank para el período a procesar.")

    _render_template_download()

    st.markdown("---")

    # ── Selector de período ──────────────────────────────────────────────────
    col1, col2 = st.columns([1, 2])
    with col1:
        meses = {
            "Enero": "01", "Febrero": "02", "Marzo": "03",
            "Abril": "04", "Mayo": "05", "Junio": "06",
            "Julio": "07", "Agosto": "08", "Septiembre": "09",
            "Octubre": "10", "Noviembre": "11", "Diciembre": "12",
        }
        mes_sel = st.selectbox("Mes", list(meses.keys()), index=11)
    with col2:
        import datetime
        anio_sel = st.number_input("Año", min_value=2020, max_value=2030,
                                   value=datetime.datetime.now().year)

    periodo = f"{anio_sel}-{meses[mes_sel]}"
    st.info(f"📅 Período seleccionado: **{mes_sel} {anio_sel}** → `{periodo}`")

    # ── Verificar si ya existen datos ────────────────────────────────────────
    tiene_debito  = periodo_tiene_datos(periodo, "DEBITO")
    tiene_credito = periodo_tiene_datos(periodo, "CREDITO")
    tiene_cartola = periodo_tiene_datos(periodo, "CARTOLA")

    if tiene_debito or tiene_credito or tiene_cartola:
        st.warning(
            f"⚠️ Ya existen datos para **{periodo}**. "
            "Si cargas nuevamente, se omitirán transacciones duplicadas (por hash único)."
        )
        sobrescribir = st.checkbox("🔄 Sobrescribir datos existentes del período", value=False)
    else:
        sobrescribir = False

    st.markdown("---")
    st.markdown("### 📂 Archivos")

    # ── Upload de los 3 archivos ─────────────────────────────────────────────
    col_d, col_c, col_b = st.columns(3)

    with col_d:
        st.markdown("#### 💳 Débito")
        st.caption("extraccion-masiva-**debito**-pesos-*.csv")
        file_debito = st.file_uploader(
            "Subir CSV Débito", type=["csv", "txt"],
            key="upload_debito", label_visibility="collapsed"
        )
        if file_debito:
            st.success(f"✅ {file_debito.name}")

    with col_c:
        st.markdown("#### 💳 Crédito")
        st.caption("extraccion-masiva-**credito**-pesos-*.csv")
        file_credito = st.file_uploader(
            "Subir CSV Crédito", type=["csv", "txt"],
            key="upload_credito", label_visibility="collapsed"
        )
        if file_credito:
            st.success(f"✅ {file_credito.name}")

    with col_b:
        st.markdown("#### 📋 Cartola de Movimientos")
        st.caption("cartola-**movimientos**-YYYYMM.csv")
        file_cartola = st.file_uploader(
            "Subir Cartola Movimientos", type=["csv", "txt"],
            key="upload_cartola", label_visibility="collapsed"
        )
        if file_cartola:
            st.success(f"✅ {file_cartola.name}")

    st.markdown("---")

    # ── Botón de procesamiento ───────────────────────────────────────────────
    procesar = st.button(
        "🚀 Procesar y Guardar",
        type="primary",
        disabled=not (file_debito or file_credito),
        use_container_width=True,
    )

    if procesar:
        _procesar_archivos(
            periodo, file_debito, file_credito, file_cartola, sobrescribir
        )


def _procesar_archivos(periodo, file_debito, file_credito, file_cartola, sobrescribir):
    """Procesa y guarda todos los archivos cargados."""
    progress = st.progress(0, text="Iniciando procesamiento...")
    resultados = {}

    # ── Metadatos empresa (de cualquier archivo disponible) ──────────────────
    empresa_rut    = ""
    empresa_nombre = ""

    # ── Débito ───────────────────────────────────────────────────────────────
    if file_debito:
        progress.progress(15, text="📥 Parseando archivo de Débito...")
        try:
            content = file_debito.read()
            meta, df_d = parse_transbank_csv(content, tipo_archivo_override="DEBITO")
            empresa_rut    = meta.get("rut", "")
            empresa_nombre = meta.get("nombre", "")

            if not df_d.empty:
                df_d = enriquecer_movimientos(df_d)
                n = save_movimientos(df_d, periodo, sobrescribir=sobrescribir)
                sync_sucursales(df_d)
                resultados["debito"] = {"registros": n, "total_df": len(df_d), "ok": True}
                st.success(f"✅ Débito: **{n}** transacciones nuevas guardadas de {len(df_d)} leídas.")
            else:
                st.warning("⚠️ El archivo de débito no contiene datos de detalle.")
                resultados["debito"] = {"ok": False}
        except Exception as e:
            st.error(f"❌ Error al parsear Débito: {e}")
            resultados["debito"] = {"ok": False, "error": str(e)}

    progress.progress(35, text="📥 Parseando archivo de Crédito...")

    # ── Crédito ───────────────────────────────────────────────────────────────
    if file_credito:
        try:
            content = file_credito.read()
            meta, df_c = parse_transbank_csv(content, tipo_archivo_override="CREDITO")
            if not empresa_rut:
                empresa_rut    = meta.get("rut", "")
                empresa_nombre = meta.get("nombre", "")

            if not df_c.empty:
                df_c = enriquecer_movimientos(df_c)
                n = save_movimientos(df_c, periodo, sobrescribir=sobrescribir)
                sync_sucursales(df_c)
                resultados["credito"] = {"registros": n, "total_df": len(df_c), "ok": True}
                st.success(f"✅ Crédito: **{n}** transacciones nuevas guardadas de {len(df_c)} leídas.")
            else:
                st.warning("⚠️ El archivo de crédito no contiene datos de detalle.")
                resultados["credito"] = {"ok": False}
        except Exception as e:
            st.error(f"❌ Error al parsear Crédito: {e}")
            resultados["credito"] = {"ok": False, "error": str(e)}

    progress.progress(60, text="📥 Parseando Cartola de Movimientos...")

    # ── Cartola de Movimientos Transbank ─────────────────────────────────────
    if file_cartola:
        try:
            content = file_cartola.read()
            meta_c, df_b = parse_cartola_movimientos(content)
            if not empresa_rut:
                empresa_rut    = meta_c.get("rut", "")
                empresa_nombre = meta_c.get("nombre", "")

            if not df_b.empty:
                df_b = enriquecer_movimientos(df_b)
                n = save_movimientos(df_b, periodo, sobrescribir=sobrescribir)
                sync_sucursales(df_b)
                resultados["cartola"] = {"registros": n, "total_df": len(df_b), "ok": True}
                st.success(f"✅ Cartola Movimientos: **{n}** transacciones nuevas guardadas de {len(df_b)} leídas.")
            else:
                st.warning("⚠️ No se encontraron datos en la Cartola de Movimientos.")
                resultados["cartola"] = {"ok": False}
        except Exception as e:
            st.error(f"❌ Error al parsear Cartola de Movimientos: {e}")
            resultados["cartola"] = {"ok": False, "error": str(e)}

    progress.progress(85, text="💾 Guardando período...")

    # ── Guardar período ───────────────────────────────────────────────────────
    upsert_periodo(periodo, empresa_rut, empresa_nombre)

    progress.progress(100, text="✅ ¡Proceso completado!")

    # ── Resumen final ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 Resumen del procesamiento")

    col1, col2, col3 = st.columns(3)
    with col1:
        r = resultados.get("debito", {})
        total = r.get("registros", 0)
        st.metric("💳 Débito guardado", f"{total:,} transacciones", delta="nuevo" if total > 0 else None)
    with col2:
        r = resultados.get("credito", {})
        total = r.get("registros", 0)
        st.metric("💳 Crédito guardado", f"{total:,} transacciones", delta="nuevo" if total > 0 else None)
    with col3:
        r = resultados.get("cartola", {})
        total = r.get("registros", 0)
        st.metric("📋 Cartola Movimientos", f"{total:,} transacciones", delta="nuevo" if total > 0 else None)

    st.session_state["periodo_activo"] = periodo
    st.info("💡 Ve al **Dashboard** para ver el análisis completo del período.")
