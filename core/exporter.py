"""
core/exporter.py
─────────────────
Genera los outputs del sistema:
  - CSV Softland Centralización
  - CSV Softland Diario
  - Excel reporte por sucursal
  - Excel reporte global
"""

import io
import pandas as pd
from datetime import datetime
from config import SOFTLAND_TIPO_COMPROBANTE, SOFTLAND_SEPARADOR, SOFTLAND_ENCODING


# ─── Softland Centralización ─────────────────────────────────────────────────

def generar_softland_centralizacion(
    df: pd.DataFrame,
    periodo: str,
    n_comprobante: str = "001"
) -> bytes:
    """
    Genera el CSV de centralización mensual para Softland.
    Estructura: Tipo;N°Doc;Fecha;Cuenta;Debe;Haber;CC;Glosa;Referencia
    """
    if df.empty:
        return b""

    # Fecha del período (último día del mes)
    try:
        year, month = map(int, periodo.split("-"))
        fecha_str = f"{pd.Timestamp(year, month, 1).days_in_month:02d}/{month:02d}/{year}"
    except Exception:
        fecha_str = datetime.now().strftime("%d/%m/%Y")

    rows = []
    neto_col = "neto_final" if "neto_final" in df.columns else "neto"

    # Una fila por sucursal y tipo

    group_cols = ["local_codigo", "local_nombre"]
    if "categoria" in df.columns:
        group_cols.append("categoria")
    else:
        group_cols.append("tipo_archivo")
    grp = df.groupby(group_cols, as_index=False).agg(
        total_ventas   = ("monto_original", "sum"),
        total_comision = ("comision_iva", "sum"),
        total_neto     = (neto_col, "sum"),
    )

    for _, row in grp.iterrows():
        glosa = f"VENTAS TRANSBANK {row['tipo_archivo']} {row['local_nombre']}"
        cuenta_debito  = "11050001"  # Cuentas por cobrar Transbank (ajustar según PUC)
        cuenta_haber   = "41100001"  # Ingresos ventas (ajustar según PUC)

        # Cargo (Debe)
        rows.append({
            "Tipo":       SOFTLAND_TIPO_COMPROBANTE,
            "N_Doc":      n_comprobante,
            "Fecha":      fecha_str,
            "Cuenta":     cuenta_debito,
            "Debe":       f"{row['total_neto']:.0f}",
            "Haber":      "0",
            "Centro_Costo": row["local_codigo"],
            "Glosa":      glosa,
            "Referencia": f"TBK-{periodo}",
        })
        # Abono (Haber)
        rows.append({
            "Tipo":       SOFTLAND_TIPO_COMPROBANTE,
            "N_Doc":      n_comprobante,
            "Fecha":      fecha_str,
            "Cuenta":     cuenta_haber,
            "Debe":       "0",
            "Haber":      f"{row['total_ventas']:.0f}",
            "Centro_Costo": row["local_codigo"],
            "Glosa":      glosa,
            "Referencia": f"TBK-{periodo}",
        })
        # Comisión
        rows.append({
            "Tipo":       SOFTLAND_TIPO_COMPROBANTE,
            "N_Doc":      n_comprobante,
            "Fecha":      fecha_str,
            "Cuenta":     "64100001",  # Gastos comisión (ajustar)
            "Debe":       f"{row['total_comision']:.0f}",
            "Haber":      "0",
            "Centro_Costo": row["local_codigo"],
            "Glosa":      f"COMISION TRANSBANK {row['tipo_archivo']} {row['local_nombre']}",
            "Referencia": f"TBK-{periodo}",
        })

    df_out = pd.DataFrame(rows)
    buf = io.StringIO()
    df_out.to_csv(buf, sep=SOFTLAND_SEPARADOR, index=False, encoding=SOFTLAND_ENCODING)
    return buf.getvalue().encode(SOFTLAND_ENCODING, errors="replace")


# ─── Softland Diario ─────────────────────────────────────────────────────────

def generar_softland_diario(df: pd.DataFrame, periodo: str) -> bytes:
    """
    Genera el CSV de asiento diario para Softland.
    Un asiento por fecha de abono × sucursal × tipo.
    """
    if df.empty:
        return b""

    neto_col = "neto_final" if "neto_final" in df.columns else "neto"

    group_cols = ["fecha_abono", "local_codigo", "local_nombre"]
    if "categoria" in df.columns:
        group_cols.append("categoria")
    else:
        group_cols.append("tipo_archivo")
    grp = df.groupby(group_cols, as_index=False).agg(
        total_ventas   = ("monto_original", "sum"),
        total_comision = ("comision_iva", "sum"),
        total_neto     = (neto_col, "sum"),
    )

    rows = []
    for _, row in grp.iterrows():
        try:
            fecha_fmt = pd.to_datetime(str(row["fecha_abono"])).strftime("%d/%m/%Y")
        except Exception:
            fecha_fmt = str(row["fecha_abono"])

        glosa = f"TBK {row['tipo_archivo']} {row['local_nombre']}"
        n_doc = f"{pd.to_datetime(str(row['fecha_abono'])).strftime('%d%m%Y')}-{row['local_codigo']}"

        rows.append({
            "Tipo": SOFTLAND_TIPO_COMPROBANTE, "N_Doc": n_doc,
            "Fecha": fecha_fmt, "Cuenta": "11050001",
            "Debe": f"{row['total_neto']:.0f}", "Haber": "0",
            "Centro_Costo": row["local_codigo"], "Glosa": glosa, "Referencia": n_doc,
        })
        rows.append({
            "Tipo": SOFTLAND_TIPO_COMPROBANTE, "N_Doc": n_doc,
            "Fecha": fecha_fmt, "Cuenta": "41100001",
            "Debe": "0", "Haber": f"{row['total_ventas']:.0f}",
            "Centro_Costo": row["local_codigo"], "Glosa": glosa, "Referencia": n_doc,
        })

    df_out = pd.DataFrame(rows)
    buf = io.StringIO()
    df_out.to_csv(buf, sep=SOFTLAND_SEPARADOR, index=False, encoding=SOFTLAND_ENCODING)
    return buf.getvalue().encode(SOFTLAND_ENCODING, errors="replace")


# ─── Excel Reporte Global ────────────────────────────────────────────────────

def generar_excel_global(df: pd.DataFrame, periodo: str) -> bytes:
    """
    Genera un Excel con múltiples hojas:
      - Resumen Global
      - Por Sucursal
      - Detalle Movimientos
      - Pendientes
      - Cuotas Pendientes
    """
    buf = io.BytesIO()

    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        wb  = writer.book
        neto_col = "neto_final" if "neto_final" in df.columns else "neto"

        # Formatos
        fmt_titulo   = wb.add_format({"bold": True, "font_size": 14, "bg_color": "#1f4e79", "font_color": "white"})
        fmt_header   = wb.add_format({"bold": True, "bg_color": "#2196f3", "font_color": "white", "border": 1})
        fmt_money    = wb.add_format({"num_format": "#,##0", "border": 1})
        fmt_pct      = wb.add_format({"num_format": "0.00%", "border": 1})
        fmt_text     = wb.add_format({"border": 1})
        fmt_verde    = wb.add_format({"bg_color": "#c8e6c9", "border": 1})
        fmt_rojo     = wb.add_format({"bg_color": "#ffcdd2", "border": 1})

        # ── Hoja 1: Resumen Global ──
        ws = wb.add_worksheet("Resumen Global")
        writer.sheets["Resumen Global"] = ws
        ws.write(0, 0, f"REPORTE TRANSBANK - PERÍODO {periodo}", fmt_titulo)
        ws.write(0, 4, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", fmt_text)

        kpis = [
            ("Total Transacciones",  len(df[df.get("tipo_transaccion", "") == "Venta"]) if "tipo_transaccion" in df.columns else len(df)),
            ("Total Ventas ($)",     df["monto_original"].sum()),
            ("Total Comisión ($)",   df["comision_iva"].sum()),
            ("Total Neto ($)",       df[neto_col].sum()),
            ("Sucursales Activas",   df["local_codigo"].nunique()),
        ]
        for i, (label, val) in enumerate(kpis):
            ws.write(i + 2, 0, label, fmt_header)
            ws.write(i + 2, 1, val, fmt_money)

        # ── Hoja 2: Por Sucursal ──
        group_cols = ["local_codigo", "local_nombre"]
        if "categoria" in df.columns:
            group_cols.append("categoria")
        else:
            group_cols.append("tipo_archivo")
        grp_suc = df.groupby(group_cols, as_index=False).agg(
            Cantidad       = ("monto_original", "count"),
            Ventas         = ("monto_original", "sum"),
            Comision       = ("comision_iva", "sum"),
            Neto           = (neto_col, "sum"),
        )
        grp_suc.to_excel(writer, sheet_name="Por Sucursal", index=False)

        # ── Hoja 3: Detalle Movimientos ──
        cols_detalle = [
            "tipo_archivo", "tipo_transaccion", "fecha_venta", "local_nombre",
            "tipo_tarjeta", "tipo_cuota", "cuota_actual", "cuota_total",
            "monto_original", "monto_abono", "comision_iva", neto_col,
            "fecha_abono", "codigo_autorizacion"
        ]
        cols_disponibles = [c for c in cols_detalle if c in df.columns]
        df[cols_disponibles].to_excel(writer, sheet_name="Detalle Movimientos", index=False)

        # ── Hoja 4: Cuotas Pendientes ──
        if "cuota_total" in df.columns:
            pend = df[
                (df["cuota_total"] > 1) &
                (df.get("cuota_actual", 1) < df["cuota_total"])
            ]
            if not pend.empty:
                pend[cols_disponibles].to_excel(writer, sheet_name="Cuotas Pendientes", index=False)

    return buf.getvalue()


# ─── Excel Reporte por Sucursal ──────────────────────────────────────────────

def generar_excel_sucursal(df: pd.DataFrame, local_nombre: str, periodo: str) -> bytes:
    """Genera un Excel detallado para una sucursal específica."""
    df_suc = df[df["local_nombre"] == local_nombre].copy()
    if df_suc.empty:
        return b""

    buf = io.BytesIO()
    neto_col = "neto_final" if "neto_final" in df_suc.columns else "neto"


    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        # Resumen
        group_col = "categoria" if "categoria" in df_suc.columns else "tipo_archivo"
        resumen = df_suc.groupby(group_col, as_index=False).agg(
            Cantidad  = ("monto_original", "count"),
            Ventas    = ("monto_original", "sum"),
            Comision  = ("comision_iva", "sum"),
            Neto      = (neto_col, "sum"),
        )
        resumen.to_excel(writer, sheet_name="Resumen", index=False)

        # Detalle
        df_suc.to_excel(writer, sheet_name="Detalle", index=False)

    return buf.getvalue()
