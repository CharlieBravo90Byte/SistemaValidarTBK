"""
core/database.py
────────────────
Capa de persistencia. Soporta dos motores transparentemente:

- SQLite local (por defecto, en `data/transbank.db`)
- Postgres (si la variable de entorno o secret `DATABASE_URL` está definida,
  por ejemplo Neon: postgresql+psycopg2://user:pass@host/db?sslmode=require)

El API público de funciones se mantiene idéntico al original basado en sqlite3.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable, Sequence

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import DATA_DIR, DB_PATH, DATABASE_URL


# ─── Engine ───────────────────────────────────────────────────────────────────

_engine: Engine | None = None


def _normalize_url(url: str) -> str:
    """Acepta el formato que entregan Neon/Supabase y lo adapta a psycopg v3."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _build_engine() -> Engine:
    if DATABASE_URL:
        return create_engine(_normalize_url(DATABASE_URL), pool_pre_ping=True, future=True)
    # SQLite local
    os.makedirs(DATA_DIR, exist_ok=True)
    return create_engine(
        f"sqlite:///{DB_PATH}",
        future=True,
        connect_args={"check_same_thread": False},
    )


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def _is_postgres() -> bool:
    return get_engine().dialect.name == "postgresql"


# ─── DDL (esquema) ────────────────────────────────────────────────────────────

def _ddl_statements() -> list[str]:
    """Retorna los CREATE TABLE adaptados al dialecto activo."""
    if _is_postgres():
        pk = "BIGSERIAL PRIMARY KEY"
        text_t = "TEXT"
        real_t = "DOUBLE PRECISION"
        int_t = "INTEGER"
    else:  # sqlite
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
        text_t = "TEXT"
        real_t = "REAL"
        int_t = "INTEGER"

    return [
        f"""
        CREATE TABLE IF NOT EXISTS periodos (
            id              {pk},
            periodo         {text_t} NOT NULL UNIQUE,
            empresa_rut     {text_t},
            empresa_nombre  {text_t},
            fecha_proceso   {text_t},
            total_ventas    {real_t} DEFAULT 0,
            total_comision  {real_t} DEFAULT 0,
            total_neto      {real_t} DEFAULT 0
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS movimientos (
            id                        {pk},
            periodo                   {text_t} NOT NULL,
            tipo_archivo              {text_t} NOT NULL,
            tipo_transaccion          {text_t},
            fecha_venta               {text_t},
            tipo_tarjeta              {text_t},
            identificador             {text_t},
            tipo_cuota                {text_t},
            monto_original            {real_t} DEFAULT 0,
            codigo_autorizacion       {text_t},
            cuota_actual              {int_t}  DEFAULT 1,
            cuota_total               {int_t}  DEFAULT 1,
            monto_abono               {real_t} DEFAULT 0,
            comision_iva              {real_t} DEFAULT 0,
            comision_adicional_iva    {real_t} DEFAULT 0,
            numero_boleta             {text_t},
            monto_anulacion           {real_t} DEFAULT 0,
            devolucion_comision       {real_t} DEFAULT 0,
            monto_retencion           {real_t} DEFAULT 0,
            fecha_abono               {text_t},
            cuenta_abono              {text_t},
            local_codigo              {text_t},
            local_nombre              {text_t},
            tipo_documento            {text_t},
            neto                      {real_t} DEFAULT 0,
            estado_conciliacion       {text_t} DEFAULT 'PENDIENTE',
            hash_unico                {text_t} UNIQUE
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS liquidaciones (
            id                  {pk},
            periodo             {text_t} NOT NULL,
            fecha               {text_t},
            descripcion         {text_t},
            monto               {real_t} DEFAULT 0,
            referencia          {text_t},
            estado_conciliacion {text_t} DEFAULT 'PENDIENTE'
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS sucursales (
            codigo          {text_t} PRIMARY KEY,
            nombre          {text_t} NOT NULL,
            cuenta_contable {text_t},
            activa          {int_t} DEFAULT 1
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_mov_periodo     ON movimientos(periodo)",
        "CREATE INDEX IF NOT EXISTS idx_mov_sucursal    ON movimientos(local_codigo)",
        "CREATE INDEX IF NOT EXISTS idx_mov_fecha_abono ON movimientos(fecha_abono)",
        "CREATE INDEX IF NOT EXISTS idx_mov_hash        ON movimientos(hash_unico)",
        "CREATE INDEX IF NOT EXISTS idx_liq_periodo     ON liquidaciones(periodo)",
    ]


def init_db() -> None:
    """Crea todas las tablas si no existen."""
    eng = get_engine()
    with eng.begin() as conn:
        for stmt in _ddl_statements():
            conn.execute(text(stmt))


# ─── Helpers internos ────────────────────────────────────────────────────────

def _read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    eng = get_engine()
    with eng.connect() as conn:
        return pd.read_sql_query(text(query), conn, params=params or {})


def _exec(query: str, params: dict | None = None) -> None:
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text(query), params or {})


def _exec_many(query: str, rows: Sequence[dict]) -> None:
    if not rows:
        return
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text(query), list(rows))


# ─── Períodos ─────────────────────────────────────────────────────────────────

def get_periodos() -> list:
    df = _read_sql("SELECT * FROM periodos ORDER BY periodo DESC")
    return df.to_dict(orient="records")


def upsert_periodo(periodo: str, empresa_rut: str = "", empresa_nombre: str = "") -> int:
    _exec(
        """
        INSERT INTO periodos (periodo, empresa_rut, empresa_nombre, fecha_proceso)
        VALUES (:periodo, :empresa_rut, :empresa_nombre, :fecha_proceso)
        ON CONFLICT(periodo) DO UPDATE SET
            empresa_rut    = EXCLUDED.empresa_rut,
            empresa_nombre = EXCLUDED.empresa_nombre,
            fecha_proceso  = EXCLUDED.fecha_proceso
        """,
        {
            "periodo": periodo,
            "empresa_rut": empresa_rut,
            "empresa_nombre": empresa_nombre,
            "fecha_proceso": datetime.now().isoformat(),
        },
    )
    df = _read_sql("SELECT id FROM periodos WHERE periodo = :periodo", {"periodo": periodo})
    return int(df.iloc[0]["id"]) if not df.empty else 0


def actualizar_totales_periodo(periodo: str) -> None:
    _exec(
        """
        UPDATE periodos SET
            total_ventas   = COALESCE((SELECT SUM(monto_original) FROM movimientos WHERE periodo=:p AND tipo_transaccion='Venta'),0),
            total_comision = COALESCE((SELECT SUM(comision_iva)   FROM movimientos WHERE periodo=:p AND tipo_transaccion='Venta'),0),
            total_neto     = COALESCE((SELECT SUM(neto)           FROM movimientos WHERE periodo=:p AND tipo_transaccion='Venta'),0)
        WHERE periodo = :p
        """,
        {"p": periodo},
    )


# ─── Movimientos ──────────────────────────────────────────────────────────────

_MOV_COLS = [
    'periodo', 'tipo_archivo', 'tipo_transaccion', 'fecha_venta', 'tipo_tarjeta',
    'identificador', 'tipo_cuota', 'monto_original', 'codigo_autorizacion',
    'cuota_actual', 'cuota_total', 'monto_abono', 'comision_iva',
    'comision_adicional_iva', 'monto_anulacion', 'devolucion_comision',
    'monto_retencion', 'fecha_abono', 'cuenta_abono',
    'local_codigo', 'local_nombre', 'neto', 'hash_unico',
]


def save_movimientos(df: pd.DataFrame, periodo: str, sobrescribir: bool = False) -> int:
    """Guarda movimientos evitando duplicados por hash_unico."""
    if df.empty:
        return 0

    if sobrescribir:
        _exec(
            "DELETE FROM movimientos WHERE periodo = :p AND tipo_archivo = :t",
            {"p": periodo, "t": df['tipo_archivo'].iloc[0]},
        )

    df = df.copy()
    df['periodo'] = periodo

    for c in ('fecha_venta', 'fecha_abono'):
        if c in df.columns:
            df[c] = df[c].astype(str).replace('NaT', '')

    cols_disponibles = [c for c in _MOV_COLS if c in df.columns]

    # Filtrado previo de hashes existentes (rápido y portable)
    existing = _read_sql(
        "SELECT hash_unico FROM movimientos WHERE periodo = :p",
        {"p": periodo},
    )
    existing_hashes = set(existing['hash_unico'].dropna().tolist()) if not existing.empty else set()

    df_nuevos = df[~df['hash_unico'].isin(existing_hashes)] if 'hash_unico' in df.columns else df

    if df_nuevos.empty:
        actualizar_totales_periodo(periodo)
        return 0

    rows = df_nuevos[cols_disponibles].to_dict(orient='records')

    placeholders = ', '.join(f":{c}" for c in cols_disponibles)
    col_str = ', '.join(cols_disponibles)
    on_conflict = "ON CONFLICT (hash_unico) DO NOTHING" if 'hash_unico' in cols_disponibles else ""

    _exec_many(
        f"INSERT INTO movimientos ({col_str}) VALUES ({placeholders}) {on_conflict}",
        rows,
    )

    actualizar_totales_periodo(periodo)
    return len(rows)


def get_movimientos(periodo: str, solo_ventas: bool = True) -> pd.DataFrame:
    query = "SELECT * FROM movimientos WHERE periodo = :p"
    if solo_ventas:
        query += " AND tipo_transaccion='Venta'"
    return _read_sql(query, {"p": periodo})


def get_movimientos_por_sucursal(periodo: str) -> pd.DataFrame:
    query = """
        SELECT
            local_codigo,
            local_nombre,
            tipo_archivo,
            COUNT(*)              AS cantidad,
            SUM(monto_original)   AS total_ventas,
            SUM(comision_iva)     AS total_comision,
            SUM(neto)             AS total_neto,
            SUM(CASE WHEN cuota_total > 1 THEN monto_original ELSE 0 END) AS ventas_cuotas
        FROM movimientos
        WHERE periodo = :p AND tipo_transaccion='Venta'
        GROUP BY local_codigo, local_nombre, tipo_archivo
        ORDER BY total_ventas DESC
    """
    return _read_sql(query, {"p": periodo})


def get_resumen_diario(periodo: str) -> pd.DataFrame:
    query = """
        SELECT
            fecha_abono,
            tipo_archivo,
            COUNT(*)            AS cantidad,
            SUM(monto_abono)    AS total_abono,
            SUM(neto)           AS total_neto
        FROM movimientos
        WHERE periodo = :p AND tipo_transaccion='Venta'
        GROUP BY fecha_abono, tipo_archivo
        ORDER BY fecha_abono
    """
    return _read_sql(query, {"p": periodo})


def get_pendientes(periodo: str) -> pd.DataFrame:
    query = """
        SELECT *
        FROM movimientos
        WHERE periodo = :p AND tipo_transaccion='Venta'
          AND cuota_total > 1
          AND cuota_actual < cuota_total
        ORDER BY local_nombre, fecha_venta
    """
    return _read_sql(query, {"p": periodo})


# ─── Sucursales ───────────────────────────────────────────────────────────────

def sync_sucursales(df_movimientos: pd.DataFrame) -> None:
    """Actualiza la tabla de sucursales a partir de los movimientos cargados."""
    if 'local_codigo' not in df_movimientos.columns:
        return
    sucursales = (
        df_movimientos[['local_codigo', 'local_nombre']]
        .dropna()
        .drop_duplicates('local_codigo')
    )
    if sucursales.empty:
        return
    rows = [
        {"codigo": r['local_codigo'], "nombre": r['local_nombre']}
        for _, r in sucursales.iterrows()
    ]
    _exec_many(
        "INSERT INTO sucursales (codigo, nombre) VALUES (:codigo, :nombre) "
        "ON CONFLICT (codigo) DO NOTHING",
        rows,
    )


def get_sucursales() -> list:
    df = _read_sql("SELECT * FROM sucursales ORDER BY nombre")
    return df.to_dict(orient="records")


# ─── Liquidaciones (cartola bancaria) ────────────────────────────────────────

def save_liquidaciones(df: pd.DataFrame, periodo: str, sobrescribir: bool = False) -> int:
    if df.empty:
        return 0
    if sobrescribir:
        _exec("DELETE FROM liquidaciones WHERE periodo = :p", {"p": periodo})

    df = df.copy()
    df['periodo'] = periodo
    cols = ['periodo', 'fecha', 'descripcion', 'monto', 'referencia']
    cols_disponibles = [c for c in cols if c in df.columns]
    rows = df[cols_disponibles].to_dict(orient='records')
    placeholders = ', '.join(f":{c}" for c in cols_disponibles)
    col_str = ', '.join(cols_disponibles)
    _exec_many(
        f"INSERT INTO liquidaciones ({col_str}) VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def get_liquidaciones(periodo: str) -> pd.DataFrame:
    return _read_sql(
        "SELECT * FROM liquidaciones WHERE periodo = :p",
        {"p": periodo},
    )


def periodo_tiene_datos(periodo: str, tipo: str) -> bool:
    """Verifica si ya existen datos cargados para ese período y tipo."""
    df = _read_sql(
        "SELECT COUNT(*) AS n FROM movimientos WHERE periodo = :p AND tipo_archivo = :t",
        {"p": periodo, "t": tipo},
    )
    return int(df.iloc[0]["n"]) > 0
