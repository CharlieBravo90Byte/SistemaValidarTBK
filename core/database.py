"""
core/database.py
────────────────
Gestión de la base de datos SQLite.
Guarda historial por período, movimientos, sucursales y conciliación.
"""
import sqlite3
import os
import pandas as pd
from datetime import datetime
from config import DB_PATH, DATA_DIR


# ─── Inicialización ───────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Crea todas las tablas si no existen."""
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS periodos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo         TEXT NOT NULL,          -- 'YYYY-MM'
            empresa_rut     TEXT,
            empresa_nombre  TEXT,
            fecha_proceso   TEXT,
            total_ventas    REAL DEFAULT 0,
            total_comision  REAL DEFAULT 0,
            total_neto      REAL DEFAULT 0,
            UNIQUE(periodo)
        );

        CREATE TABLE IF NOT EXISTS movimientos (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo                   TEXT NOT NULL,
            tipo_archivo              TEXT NOT NULL,   -- DEBITO / CREDITO
            tipo_transaccion          TEXT,
            fecha_venta               TEXT,
            tipo_tarjeta              TEXT,
            identificador             TEXT,
            tipo_cuota                TEXT,
            monto_original            REAL DEFAULT 0,
            codigo_autorizacion       TEXT,
            cuota_actual              INTEGER DEFAULT 1,
            cuota_total               INTEGER DEFAULT 1,
            monto_abono               REAL DEFAULT 0,
            comision_iva              REAL DEFAULT 0,
            comision_adicional_iva    REAL DEFAULT 0,
            numero_boleta             TEXT,
            monto_anulacion           REAL DEFAULT 0,
            devolucion_comision       REAL DEFAULT 0,
            monto_retencion           REAL DEFAULT 0,
            fecha_abono               TEXT,
            cuenta_abono              TEXT,
            local_codigo              TEXT,
            local_nombre              TEXT,
            tipo_documento            TEXT,
            neto                      REAL DEFAULT 0,
            estado_conciliacion       TEXT DEFAULT 'PENDIENTE',
            hash_unico                TEXT
        );

        CREATE TABLE IF NOT EXISTS liquidaciones (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo             TEXT NOT NULL,
            fecha               TEXT,
            descripcion         TEXT,
            monto               REAL DEFAULT 0,
            referencia          TEXT,
            estado_conciliacion TEXT DEFAULT 'PENDIENTE'
        );

        CREATE TABLE IF NOT EXISTS sucursales (
            codigo          TEXT PRIMARY KEY,
            nombre          TEXT NOT NULL,
            cuenta_contable TEXT,
            activa          INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_mov_periodo    ON movimientos(periodo);
        CREATE INDEX IF NOT EXISTS idx_mov_sucursal   ON movimientos(local_codigo);
        CREATE INDEX IF NOT EXISTS idx_mov_fecha_abono ON movimientos(fecha_abono);
        CREATE INDEX IF NOT EXISTS idx_mov_hash       ON movimientos(hash_unico);
        CREATE INDEX IF NOT EXISTS idx_liq_periodo    ON liquidaciones(periodo);
        """)


# ─── Períodos ─────────────────────────────────────────────────────────────────

def get_periodos() -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM periodos ORDER BY periodo DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_periodo(periodo: str, empresa_rut: str = "", empresa_nombre: str = "") -> int:
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO periodos (periodo, empresa_rut, empresa_nombre, fecha_proceso)
            VALUES (?,?,?,?)
            ON CONFLICT(periodo) DO UPDATE SET
                empresa_rut    = excluded.empresa_rut,
                empresa_nombre = excluded.empresa_nombre,
                fecha_proceso  = excluded.fecha_proceso
        """, (periodo, empresa_rut, empresa_nombre, datetime.now().isoformat()))
        row = conn.execute("SELECT id FROM periodos WHERE periodo=?", (periodo,)).fetchone()
    return row["id"]


def actualizar_totales_periodo(periodo: str):
    with get_connection() as conn:
        conn.execute("""
            UPDATE periodos SET
                total_ventas   = (SELECT COALESCE(SUM(monto_original),0) FROM movimientos WHERE periodo=? AND tipo_transaccion='Venta'),
                total_comision = (SELECT COALESCE(SUM(comision_iva),0)   FROM movimientos WHERE periodo=? AND tipo_transaccion='Venta'),
                total_neto     = (SELECT COALESCE(SUM(neto),0)           FROM movimientos WHERE periodo=? AND tipo_transaccion='Venta')
            WHERE periodo=?
        """, (periodo, periodo, periodo, periodo))


# ─── Movimientos ──────────────────────────────────────────────────────────────

def save_movimientos(df: pd.DataFrame, periodo: str, sobrescribir: bool = False) -> int:
    """Guarda movimientos evitando duplicados por hash_unico."""
    if df.empty:
        return 0

    if sobrescribir:
        with get_connection() as conn:
            conn.execute("DELETE FROM movimientos WHERE periodo=? AND tipo_archivo=?",
                         (periodo, df['tipo_archivo'].iloc[0]))

    cols = [
        'periodo', 'tipo_archivo', 'tipo_transaccion', 'fecha_venta', 'tipo_tarjeta',
        'identificador', 'tipo_cuota', 'monto_original', 'codigo_autorizacion',
        'cuota_actual', 'cuota_total', 'monto_abono', 'comision_iva',
        'comision_adicional_iva', 'monto_anulacion', 'devolucion_comision',
        'monto_retencion', 'fecha_abono', 'cuenta_abono',
        'local_codigo', 'local_nombre', 'neto', 'hash_unico'
    ]

    df = df.copy()
    df['periodo'] = periodo

    # Convertir fechas a string
    for c in ['fecha_venta', 'fecha_abono']:
        if c in df.columns:
            df[c] = df[c].astype(str).replace('NaT', '')

    # Solo columnas que existen
    cols_disponibles = [c for c in cols if c in df.columns]
    registros = df[cols_disponibles].values.tolist()

    placeholders = ','.join(['?' for _ in cols_disponibles])
    col_str      = ','.join(cols_disponibles)

    inserted = 0
    with get_connection() as conn:
        existing_hashes = set(
            r[0] for r in conn.execute(
                "SELECT hash_unico FROM movimientos WHERE periodo=?", (periodo,)
            ).fetchall()
        )
        nuevos = [r for r in registros if r[cols_disponibles.index('hash_unico')] not in existing_hashes]
        if nuevos:
            conn.executemany(
                f"INSERT OR IGNORE INTO movimientos ({col_str}) VALUES ({placeholders})",
                nuevos
            )
            inserted = len(nuevos)

    actualizar_totales_periodo(periodo)
    return inserted


def get_movimientos(periodo: str, solo_ventas: bool = True) -> pd.DataFrame:
    query = "SELECT * FROM movimientos WHERE periodo=?"
    params = [periodo]
    if solo_ventas:
        query += " AND tipo_transaccion='Venta'"
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df


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
        WHERE periodo=? AND tipo_transaccion='Venta'
        GROUP BY local_codigo, local_nombre, tipo_archivo
        ORDER BY total_ventas DESC
    """
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=[periodo])


def get_resumen_diario(periodo: str) -> pd.DataFrame:
    query = """
        SELECT
            fecha_abono,
            tipo_archivo,
            COUNT(*)            AS cantidad,
            SUM(monto_abono)    AS total_abono,
            SUM(neto)           AS total_neto
        FROM movimientos
        WHERE periodo=? AND tipo_transaccion='Venta'
        GROUP BY fecha_abono, tipo_archivo
        ORDER BY fecha_abono
    """
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=[periodo])


def get_pendientes(periodo: str) -> pd.DataFrame:
    query = """
        SELECT *
        FROM movimientos
        WHERE periodo=? AND tipo_transaccion='Venta'
          AND cuota_total > 1
          AND cuota_actual < cuota_total
        ORDER BY local_nombre, fecha_venta
    """
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=[periodo])


# ─── Sucursales ───────────────────────────────────────────────────────────────

def sync_sucursales(df_movimientos: pd.DataFrame):
    """Actualiza la tabla de sucursales a partir de los movimientos cargados."""
    if 'local_codigo' not in df_movimientos.columns:
        return
    sucursales = (
        df_movimientos[['local_codigo', 'local_nombre']]
        .dropna()
        .drop_duplicates('local_codigo')
    )
    with get_connection() as conn:
        for _, row in sucursales.iterrows():
            conn.execute("""
                INSERT OR IGNORE INTO sucursales (codigo, nombre)
                VALUES (?,?)
            """, (row['local_codigo'], row['local_nombre']))


def get_sucursales() -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sucursales ORDER BY nombre"
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Liquidaciones (cartola bancaria) ────────────────────────────────────────

def save_liquidaciones(df: pd.DataFrame, periodo: str, sobrescribir: bool = False) -> int:
    if df.empty:
        return 0
    if sobrescribir:
        with get_connection() as conn:
            conn.execute("DELETE FROM liquidaciones WHERE periodo=?", (periodo,))
    df = df.copy()
    df['periodo'] = periodo
    cols = ['periodo', 'fecha', 'descripcion', 'monto', 'referencia']
    cols_disponibles = [c for c in cols if c in df.columns]
    registros = df[cols_disponibles].values.tolist()
    placeholders = ','.join(['?' for _ in cols_disponibles])
    col_str = ','.join(cols_disponibles)
    with get_connection() as conn:
        conn.executemany(
            f"INSERT INTO liquidaciones ({col_str}) VALUES ({placeholders})",
            registros
        )
    return len(registros)


def get_liquidaciones(periodo: str) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM liquidaciones WHERE periodo=?",
            conn, params=[periodo]
        )


def periodo_tiene_datos(periodo: str, tipo: str) -> bool:
    """Verifica si ya existen datos cargados para ese período y tipo."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n FROM movimientos WHERE periodo=? AND tipo_archivo=?",
            (periodo, tipo)
        ).fetchone()
    return row["n"] > 0
