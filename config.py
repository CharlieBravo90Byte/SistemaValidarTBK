import os

# ─── Rutas base ───────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH    = os.path.join(DATA_DIR, "transbank.db")

# ─── Base de datos ────────────────────────────────────────────────────────────
# Si DATABASE_URL está definida (variable de entorno o Streamlit secret),
# se usa ese motor (ej. Postgres en Neon/Supabase). Si no, SQLite local.
# Ejemplo Postgres: postgresql+psycopg2://user:pass@host/dbname?sslmode=require
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
try:
    import streamlit as _st  # type: ignore
    if not DATABASE_URL and hasattr(_st, "secrets"):
        DATABASE_URL = str(_st.secrets.get("DATABASE_URL", "")).strip()
except Exception:
    pass

# ─── Tipo de tarjeta (VI / MC → nombre legible) ───────────────────────────────
TIPO_TARJETA_MAP = {
    "VI":  "VISA",
    "MC":  "MASTERCARD",
    "AX":  "AMEX",
    "DC":  "DINERS",
    "MG":  "MAGNA",
    "PR":  "PRESTO",
    "DB":  "DÉBITO",       # usado en cartola de movimientos
    "CFE": "CRÉDITO FEE",  # cuota sin interés
    "VN":  "VENTA NORMAL",
}

# ─── Tipo de cuota ────────────────────────────────────────────────────────────
TIPO_CUOTA_MAP = {
    "SC":   "SIN CUOTA",
    "C3C":  "3 CUOTAS",
    "C6C":  "6 CUOTAS",
    "C12C": "12 CUOTAS",
    "C18C": "18 CUOTAS",
    "C24C": "24 CUOTAS",
    "CIC":  "CUOTAS IGUALES",
    "CPC":  "CUOTAS SIN INTERÉS",
    "VN":   "VENTA NORMAL",
}

# ─── Detección del tipo de archivo por producto ───────────────────────────────
KEYWORDS_CREDITO = ["crédito", "credito", "tarjetas de cr"]
KEYWORDS_DEBITO  = ["débito", "debito"]

# ─── Estados de conciliación ──────────────────────────────────────────────────
ESTADO_CONCILIADO  = "CONCILIADO"
ESTADO_PENDIENTE   = "PENDIENTE"
ESTADO_PARCIAL     = "PARCIAL"

# ─── Softland ─────────────────────────────────────────────────────────────────
SOFTLAND_TIPO_COMPROBANTE = "VC"
SOFTLAND_SEPARADOR        = ";"
SOFTLAND_ENCODING         = "latin-1"

# ─── Paleta de colores ────────────────────────────────────────────────────────
COLOR_PRIMARIO    = "#1f4e79"
COLOR_SECUNDARIO  = "#2196f3"
COLOR_EXITO       = "#28a745"
COLOR_ALERTA      = "#ffc107"
COLOR_PELIGRO     = "#dc3545"
COLOR_CREDITO     = "#1565c0"
COLOR_DEBITO      = "#2e7d32"
