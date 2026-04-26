"""
core/calculator.py
───────────────────
Reproduce la lógica del GLOBAL del Excel:
  - Comisión por tipo de tarjeta
  - IVA sobre comisión
  - Neto final
  - Consolidados por sucursal, por fecha y global
"""

import pandas as pd
from config import TIPO_TARJETA_MAP, TIPO_CUOTA_MAP

# Tasas de comisión por defecto (se reemplazan si vienen del CSV)
TASAS_DEFECTO = {
    "DEBITO":   0.0077,   # 0.77%
    "CREDITO":  0.0150,   # 1.50%
}


def enriquecer_movimientos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega columnas calculadas al DataFrame de movimientos:
      - tarjeta_nombre  : nombre legible del tipo de tarjeta
      - cuota_desc      : descripción del tipo de cuota
      - es_cuota        : True si tiene más de 1 cuota
      - cuotas_pendientes: cuotas que aún no han sido abonadas
      - comision_neta   : comisión sin IVA (estimada)
      - iva_comision    : IVA sobre comisión
    """
    df = df.copy()

    # Nombre de tarjeta
    df["tarjeta_nombre"] = df["tipo_tarjeta"].map(TIPO_TARJETA_MAP).fillna(df["tipo_tarjeta"])

    # Descripción tipo cuota
    df["cuota_desc"] = df["tipo_cuota"].map(TIPO_CUOTA_MAP).fillna(df["tipo_cuota"])

    # Flags de cuotas
    df["es_cuota"]           = df["cuota_total"] > 1
    df["cuotas_pendientes"]  = (df["cuota_total"] - df["cuota_actual"]).clip(lower=0)
    df["es_ultima_cuota"]    = df["cuota_actual"] == df["cuota_total"]

    # Comisión base (sin IVA) y su IVA
    # El CSV ya trae 'comision_iva' que incluye IVA.
    # Descomponemos: IVA = comision_iva * 19/119
    df["iva_comision"]    = (df["comision_iva"] * 19 / 119).round(0)
    df["comision_neta"]   = (df["comision_iva"] - df["iva_comision"]).round(0)

    # Monto abono neto final
    df["neto_final"] = (
        df["monto_abono"] - df["comision_iva"] + df.get("devolucion_comision", 0)
    ).round(0)

    return df


def consolidar_por_sucursal(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa por sucursal y tipo_archivo.
    Devuelve KPIs: ventas, comisión, neto, cuotas pendientes.
    """
    if df.empty:
        return pd.DataFrame()

    grp = df.groupby(["local_codigo", "local_nombre", "tipo_archivo"], as_index=False).agg(
        cantidad        = ("monto_original", "count"),
        total_ventas    = ("monto_original", "sum"),
        total_abono     = ("monto_abono", "sum"),
        total_comision  = ("comision_iva", "sum"),
        total_neto      = ("neto_final", "sum"),
        ventas_cuotas   = ("monto_original", lambda s: s[df.loc[s.index, "es_cuota"]].sum()),
        pendiente_cuotas= ("cuotas_pendientes", "sum"),
    )
    grp["pct_comision"] = (grp["total_comision"] / grp["total_ventas"].replace(0, 1) * 100).round(2)
    return grp.sort_values("total_ventas", ascending=False)


def consolidar_global(df: pd.DataFrame) -> dict:
    """Resumen global del período."""
    if df.empty:
        return {}
    ventas = df[df["tipo_transaccion"] == "Venta"] if "tipo_transaccion" in df.columns else df
    return {
        "total_transacciones": len(ventas),
        "total_ventas":        ventas["monto_original"].sum(),
        "total_abono":         ventas["monto_abono"].sum(),
        "total_comision":      ventas["comision_iva"].sum(),
        "total_neto":          ventas["neto_final"].sum() if "neto_final" in ventas.columns else ventas["neto"].sum(),
        "total_debito":        ventas[ventas["tipo_archivo"] == "DEBITO"]["monto_original"].sum(),
        "total_credito":       ventas[ventas["tipo_archivo"] == "CREDITO"]["monto_original"].sum(),
        "sucursales_activas":  ventas["local_codigo"].nunique(),
        "cuotas_pendientes":   int(ventas["cuotas_pendientes"].sum()) if "cuotas_pendientes" in ventas.columns else 0,
    }


def resumen_por_fecha_abono(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa por fecha_abono para ver flujo de caja."""
    if df.empty:
        return pd.DataFrame()
    if "fecha_abono" not in df.columns:
        return pd.DataFrame()
    grp = df.groupby(["fecha_abono", "tipo_archivo"], as_index=False).agg(
        cantidad       = ("monto_abono", "count"),
        total_abono    = ("monto_abono", "sum"),
        total_comision = ("comision_iva", "sum"),
        total_neto     = ("neto_final", "sum") if "neto_final" in df.columns else ("neto", "sum"),
    )
    return grp.sort_values("fecha_abono")


def calcular_proyeccion_cuotas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Para ventas en cuotas, calcula cuánto falta recibir (cuotas futuras).
    Útil para proyectar flujo de caja del siguiente mes.
    """
    if df.empty:
        return pd.DataFrame()
    cuotas_df = df[df["cuota_total"] > 1].copy()
    if cuotas_df.empty:
        return pd.DataFrame()

    cuotas_df["monto_por_cuota"]   = (cuotas_df["monto_original"] / cuotas_df["cuota_total"]).round(0)
    cuotas_df["monto_ya_abonado"]  = cuotas_df["monto_por_cuota"] * cuotas_df["cuota_actual"]
    cuotas_df["monto_por_cobrar"]  = cuotas_df["monto_original"] - cuotas_df["monto_ya_abonado"]
    cuotas_df["cuotas_restantes"]  = cuotas_df["cuota_total"] - cuotas_df["cuota_actual"]

    return cuotas_df[[
        "local_nombre", "tipo_cuota", "cuota_actual", "cuota_total",
        "cuotas_restantes", "monto_original", "monto_ya_abonado", "monto_por_cobrar",
        "fecha_venta", "codigo_autorizacion"
    ]].sort_values("monto_por_cobrar", ascending=False)
