"""
core/matcher.py
────────────────
Motor de conciliación:
  Cruza movimientos (Transbank) vs liquidaciones (cartola bancaria).
  Clasifica cada movimiento como: CONCILIADO / PENDIENTE / PARCIAL
"""

import pandas as pd
from config import ESTADO_CONCILIADO, ESTADO_PENDIENTE, ESTADO_PARCIAL


def conciliar_por_fecha_monto(
    df_movimientos: pd.DataFrame,
    df_liquidaciones: pd.DataFrame,
    tolerancia: float = 1.0
) -> pd.DataFrame:
    """
    Conciliación simple: agrupa movimientos por fecha_abono y
    busca el total en liquidaciones con esa fecha.

    Retorna df_movimientos con columna 'estado_conciliacion'.
    """
    if df_movimientos.empty:
        return df_movimientos

    df_mov = df_movimientos.copy()
    df_mov["estado_conciliacion"] = ESTADO_PENDIENTE

    if df_liquidaciones.empty:
        return df_mov

    # Agrupar movimientos por fecha_abono → suma neto
    if "fecha_abono" not in df_mov.columns:
        return df_mov

    df_mov["_fecha_str"] = pd.to_datetime(df_mov["fecha_abono"], errors="coerce").dt.strftime("%Y-%m-%d")
    df_liq = df_liquidaciones.copy()
    df_liq["_fecha_str"] = pd.to_datetime(df_liq["fecha"], errors="coerce").dt.strftime("%Y-%m-%d")

    # Total neto esperado por fecha de abono (mov)
    neto_col = "neto_final" if "neto_final" in df_mov.columns else "neto"
    resumen_mov = df_mov.groupby("_fecha_str")[neto_col].sum().reset_index()
    resumen_mov.columns = ["_fecha_str", "_total_mov"]

    # Total recibido por fecha (liquidaciones)
    resumen_liq = df_liq.groupby("_fecha_str")["monto"].sum().reset_index()
    resumen_liq.columns = ["_fecha_str", "_total_liq"]

    cruce = resumen_mov.merge(resumen_liq, on="_fecha_str", how="left")
    cruce["_diferencia"] = (cruce["_total_mov"] - cruce["_total_liq"]).abs()

    # Marcar fechas conciliadas
    fechas_conciliadas = set(
        cruce[cruce["_diferencia"] <= tolerancia]["_fecha_str"].tolist()
    )
    fechas_parciales = set(
        cruce[
            (cruce["_diferencia"] > tolerancia) &
            (cruce["_total_liq"].notna()) &
            (cruce["_total_liq"] > 0)
        ]["_fecha_str"].tolist()
    )

    def asignar_estado(fecha):
        if fecha in fechas_conciliadas:
            return ESTADO_CONCILIADO
        elif fecha in fechas_parciales:
            return ESTADO_PARCIAL
        return ESTADO_PENDIENTE

    df_mov["estado_conciliacion"] = df_mov["_fecha_str"].apply(asignar_estado)
    df_mov.drop(columns=["_fecha_str"], inplace=True)
    return df_mov


def identificar_pendientes_simples(df: pd.DataFrame) -> pd.DataFrame:
    """Movimientos sin match en liquidaciones (cuota 1/1 o SC)."""
    if df.empty:
        return pd.DataFrame()
    mask = (
        (df.get("estado_conciliacion", ESTADO_PENDIENTE) == ESTADO_PENDIENTE) &
        (df.get("cuota_total", 1) == 1)
    )
    return df[mask].copy()


def identificar_pendientes_cuotas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Movimientos con cuotas aún no recibidas.
    Incluye: la cuota actual pendiente Y las cuotas futuras (ej. 1/3 → faltan 2/3 y 3/3).
    """
    if df.empty:
        return pd.DataFrame()
    mask = df.get("cuota_total", 1) > 1
    cuotas_df = df[mask].copy()
    if cuotas_df.empty:
        return pd.DataFrame()

    # Pendientes = cuotas donde cuota_actual < cuota_total
    cuotas_pendientes = cuotas_df[cuotas_df["cuota_actual"] < cuotas_df["cuota_total"]].copy()
    return cuotas_pendientes


def resumen_conciliacion(df: pd.DataFrame) -> dict:
    """KPIs de conciliación."""
    if df.empty:
        return {"total": 0, "conciliados": 0, "pendientes": 0, "parciales": 0, "pct_conciliacion": 0.0}

    if "estado_conciliacion" not in df.columns:
        return {"total": len(df), "conciliados": 0, "pendientes": len(df), "parciales": 0, "pct_conciliacion": 0.0}

    total       = len(df)
    conciliados = (df["estado_conciliacion"] == ESTADO_CONCILIADO).sum()
    parciales   = (df["estado_conciliacion"] == ESTADO_PARCIAL).sum()
    pendientes  = (df["estado_conciliacion"] == ESTADO_PENDIENTE).sum()
    pct         = round(conciliados / total * 100, 1) if total > 0 else 0.0

    neto_col = "neto_final" if "neto_final" in df.columns else "neto"
    return {
        "total":             total,
        "conciliados":       int(conciliados),
        "pendientes":        int(pendientes),
        "parciales":         int(parciales),
        "pct_conciliacion":  pct,
        "monto_conciliado":  df[df["estado_conciliacion"] == ESTADO_CONCILIADO][neto_col].sum(),
        "monto_pendiente":   df[df["estado_conciliacion"] == ESTADO_PENDIENTE][neto_col].sum(),
    }
