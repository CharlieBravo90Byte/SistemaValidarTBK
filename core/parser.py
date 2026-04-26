"""
core/parser.py
───────────────
Parsea los 3 archivos CSV de Transbank:
  - extraccion-masiva-debito-pesos.csv
  - extraccion-masiva-credito-pesos.csv
  - cartola bancaria (formato flexible)

Maneja:
  - Cabecera de metadatos (RUT, período, totales)
  - Separador ';'
  - Números chilenos '1.234.567' → 1234567
  - Cuotas '03/3' → (cuota_actual=3, cuota_total=3)
  - Local '32187803 - AURUS COPIAPO' → (codigo, nombre)
  - Encoding latin-1 / cp1252
"""

import re
import pandas as pd
from typing import Tuple, Dict
from config import KEYWORDS_CREDITO, KEYWORDS_DEBITO

ENCODINGS = ["latin-1", "cp1252", "utf-8", "utf-8-sig"]


# ─── Utilidades numéricas y de texto ─────────────────────────────────────────

def clean_number(value) -> float:
    """Convierte '1.234.567' o '1234567' → float. Retorna 0.0 si inválido."""
    if value is None:
        return 0.0
    s = str(value).strip().replace(" ", "")
    if not s or s in ("-", "N/A"):
        return 0.0
    # Formato chileno: punto como miles, coma como decimal
    # Ej: '1.234.567' → '1234567'  |  '1.234,56' → '1234.56'
    if s.count(".") > 1:
        s = s.replace(".", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_cuota(value: str) -> Tuple[int, int]:
    """'03/3' → (3,3) | '01/6' → (1,6) | '' → (1,1)"""
    if not value or not str(value).strip():
        return (1, 1)
    m = re.match(r"(\d+)/(\d+)", str(value).strip())
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (1, 1)


def parse_local(value: str) -> Tuple[str, str]:
    """'32187803 - AURUS COPIAPO' → ('32187803', 'AURUS COPIAPO')"""
    if not value or not str(value).strip():
        return ("", "")
    parts = str(value).strip().split(" - ", 1)
    if len(parts) == 2:
        return (parts[0].strip(), parts[1].strip())
    return (value.strip(), value.strip())


def detect_encoding(raw: bytes) -> str:
    for enc in ENCODINGS:
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "latin-1"


# ─── Detección de tipo de archivo ────────────────────────────────────────────

def detect_tipo_archivo(lines: list) -> str:
    """Detecta si el CSV es CREDITO o DEBITO leyendo la cabecera."""
    sample = " ".join(lines[:20]).lower()
    if any(k in sample for k in KEYWORDS_CREDITO):
        return "CREDITO"
    if any(k in sample for k in KEYWORDS_DEBITO):
        return "DEBITO"
    return "CREDITO"  # default


# ─── Parser de metadatos ─────────────────────────────────────────────────────

def parse_metadata(lines: list) -> Dict[str, str]:
    """Extrae RUT, nombre, período y totales de la cabecera del CSV."""
    meta = {}
    for line in lines[:40]:
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 2:
            continue
        key = parts[0].lower()
        val = parts[1] if len(parts) > 1 else ""

        if "rut" in key and ":" in key:
            meta["rut"] = val
        elif "nombre" in key or "raz" in key:
            meta["nombre"] = val
        elif "producto" in key:
            meta["producto"] = val
            meta["tipo_archivo"] = detect_tipo_archivo([val])
        elif "período" in key or "periodo" in key:
            # '12/2025' → '2025-12'
            m = re.match(r"(\d{1,2})/(\d{4})", val)
            if m:
                meta["periodo"] = f"{m.group(2)}-{m.group(1).zfill(2)}"
            else:
                meta["periodo"] = val
        elif "ventas (+)" in key:
            meta["total_ventas_header"] = val
    return meta


# ─── Búsqueda de inicio de datos ─────────────────────────────────────────────

def find_data_header_line(lines: list) -> int:
    """Retorna el índice de la línea que contiene los encabezados de columnas."""
    for i, line in enumerate(lines):
        low = line.lower()
        # La línea de encabezado real comienza con "tipo transac"
        if "tipo transac" in low and "fecha" in low:
            return i
    return -1


# ─── Parser principal de Transbank ───────────────────────────────────────────

def parse_transbank_csv(
    file_content: bytes,
    tipo_archivo_override: str = None
) -> Tuple[Dict, pd.DataFrame]:
    """
    Parsea un CSV de Transbank (débito o crédito).

    Retorna:
        meta  : dict con RUT, nombre, período, tipo_archivo
        df    : DataFrame normalizado con todos los movimientos
    """
    encoding = detect_encoding(file_content)
    text = file_content.decode(encoding, errors="replace")
    lines = text.splitlines()

    # Metadatos
    meta = parse_metadata(lines)
    if tipo_archivo_override:
        meta["tipo_archivo"] = tipo_archivo_override
    elif "tipo_archivo" not in meta:
        meta["tipo_archivo"] = detect_tipo_archivo(lines)

    # Encontrar encabezado de datos
    header_idx = find_data_header_line(lines)
    if header_idx == -1:
        return meta, pd.DataFrame()

    columns_raw = [c.strip() for c in lines[header_idx].split(";")]

    # Leer filas de datos
    rows = []
    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        parts = line.split(";")
        tipo = parts[0].strip() if parts else ""
        if tipo not in ("Venta", "Anulación", "Anulacion", "Cobro",
                        "Retención", "Retencion", "Devolución", "Devolucion"):
            continue
        # Padding si la fila tiene menos columnas que el header
        while len(parts) < len(columns_raw):
            parts.append("")
        row = {columns_raw[j]: parts[j].strip() for j in range(len(columns_raw))}
        rows.append(row)

    if not rows:
        return meta, pd.DataFrame()

    df = pd.DataFrame(rows)
    df = _normalize_df(df, meta["tipo_archivo"])
    return meta, df


# ─── Normalización de columnas ───────────────────────────────────────────────

# ─── Normalización de columnas ───────────────────────────────────────────────
# Clave: nombre exacto en minúsculas tal como viene en el CSV (decodificado en latin-1)
# Valor: nombre canónico interno
_COL_ALIAS = {
    # ── COMUNES débito y crédito ────────────────────────────────────────────
    "tipo transacción":                              "tipo_transaccion",
    "tipo transacci\u00f3n":                         "tipo_transaccion",
    "tipo transaccion":                              "tipo_transaccion",
    "fecha venta":                                   "fecha_venta",
    "tipo tarjeta":                                  "tipo_tarjeta",
    "identificador":                                 "identificador",
    "tipo cuota":                                    "tipo_cuota",
    "tipo venta":                                    "tipo_cuota",       # usado en débito
    "código autorización venta":                     "codigo_autorizacion",
    "c\u00f3digo autorizaci\u00f3n venta":           "codigo_autorizacion",
    "codigo autorizacion venta":                     "codigo_autorizacion",
    # n° cuota – crédito usa '°' (grado \u00b0), débito usa 'º' (ordinal \u00ba)
    "n\u00b0 cuota":                                 "numero_cuota",   # crédito
    "n\u00ba cuota":                                 "numero_cuota",   # débito (Nº)
    "n° cuota":                                      "numero_cuota",
    "nº cuota":                                      "numero_cuota",
    "numero cuota":                                  "numero_cuota",
    "n° boleta":                                     "numero_boleta",
    "n\u00b0 boleta":                                "numero_boleta",
    "nº boleta":                                     "numero_boleta",
    "n\u00ba boleta":                                "numero_boleta",
    "comisi\u00f3n e iva comisi\u00f3n":             "comision_iva",
    "comisión e iva comisión":                       "comision_iva",
    "comision e iva comision":                       "comision_iva",
    "comisi\u00f3n adicional e iva comisi\u00f3n adicional": "comision_adicional_iva",
    "comisión adicional e iva comisión adicional":   "comision_adicional_iva",
    "comision adicional e iva comision adicional":   "comision_adicional_iva",
    "monto anulaci\u00f3n":                          "monto_anulacion",
    "monto anulación":                               "monto_anulacion",
    "monto anulacion":                               "monto_anulacion",
    "devoluci\u00f3n comisi\u00f3n e iva comisi\u00f3n": "devolucion_comision",
    "devolución comisión e iva comisión":            "devolucion_comision",
    "devolucion comision e iva comision":            "devolucion_comision",
    "devoluci\u00f3n comisi\u00f3n":                 "devolucion_comision",   # débito (sin "e IVA")
    "devolución comisión":                           "devolucion_comision",
    "devolucion comision":                           "devolucion_comision",
    "devoluci\u00f3n comisi\u00f3n adicional e iva comisi\u00f3n": "devolucion_comision_adicional",
    "devolución comisión adicional e iva comisión":  "devolucion_comision_adicional",
    "devolucion comision adicional e iva comision":  "devolucion_comision_adicional",
    "monto retenci\u00f3n":                          "monto_retencion",
    "monto retención":                               "monto_retencion",
    "monto retencion":                               "monto_retencion",
    "monto retenido":                                "monto_retencion",   # alias débito
    "per\u00edodo de cobro":                         "periodo_cobro",
    "período de cobro":                              "periodo_cobro",
    "periodo de cobro":                              "periodo_cobro",
    "motivo":                                        "motivo",
    "detalle de cobros u observaci\u00f3n":          "detalle_cobro",
    "detalle de cobros u observación":               "detalle_cobro",
    "detalle de cobros u observacion":               "detalle_cobro",
    "fecha abono":                                   "fecha_abono",
    "cuenta de abono":                               "cuenta_abono",
    "local":                                         "local",
    "tipo documento":                                "tipo_documento",
    # ── CRÉDITO ─────────────────────────────────────────────────────────────
    "monto original venta":                          "monto_original",
    "monto para abono":                              "monto_abono",
    "monto":                                         "monto_cobro",      # columna literal "Monto"
    "iva":                                           "iva_cobro",        # columna literal "IVA"
    # ── DÉBITO ──────────────────────────────────────────────────────────────
    "monto transacci\u00f3n":                        "monto_original",   # = monto total en débito
    "monto transacción":                             "monto_original",
    "monto transaccion":                             "monto_original",
    "monto afecto":                                  "monto_afecto",
    "monto exento":                                  "monto_exento",
    "monto vuelto":                                  "monto_vuelto",
}


def _normalize_df(df: pd.DataFrame, tipo_archivo: str) -> pd.DataFrame:
    """Renombra columnas, convierte tipos y agrega campos calculados."""
    # Eliminar columnas sin nombre (artefacto del ';' final en el CSV)
    df = df.loc[:, df.columns.str.strip() != ""]

    # Renombrar columnas por alias – solo coincidencia EXACTA (col_low == alias)
    # Esto evita que "Monto" capture "Monto Transacción", "IVA" capture "Comisión e IVA...", etc.
    rename_map = {}
    for col in df.columns:
        col_low = col.lower().strip()
        if col_low in _COL_ALIAS:
            rename_map[col] = _COL_ALIAS[col_low]
    df = df.rename(columns=rename_map)

    # Protección: si tras el rename quedan columnas duplicadas, mantener solo la primera
    df = df.loc[:, ~df.columns.duplicated(keep="first")]


    # Etiquetar CPC como categoría aparte
    def categorizar(row):
        tipo_cuota = str(row.get("tipo_cuota", "")).upper()
        tipo_tarjeta = str(row.get("tipo_tarjeta", "")).upper()
        if tipo_cuota in {"CFE", "CPC", "CIC"} or tipo_tarjeta == "CFE":
            return "CPC"
        return row.get("tipo_archivo", tipo_archivo)
    df["categoria"] = df.apply(categorizar, axis=1)
    df["tipo_archivo"] = tipo_archivo

    # Parsear Local
    if "local" in df.columns:
        loc = df["local"].apply(parse_local)
        df["local_codigo"] = loc.apply(lambda x: x[0])
        df["local_nombre"] = loc.apply(lambda x: x[1])
    else:
        df["local_codigo"] = ""
        df["local_nombre"] = ""

    # Parsear cuota
    if "numero_cuota" in df.columns:
        cuotas = df["numero_cuota"].apply(parse_cuota)
        df["cuota_actual"] = cuotas.apply(lambda x: x[0])
        df["cuota_total"]  = cuotas.apply(lambda x: x[1])
    else:
        df["cuota_actual"] = 1
        df["cuota_total"]  = 1

    if "tipo_cuota" not in df.columns:
        df["tipo_cuota"] = "SC"

    # Columnas numéricas (lista comprehension evita FutureWarning de pandas 2.x)
    num_cols = [
        "monto_original", "monto_abono", "comision_iva",
        "comision_adicional_iva", "monto_anulacion",
        "devolucion_comision", "monto_retencion", "monto_cobro", "iva_cobro",
        "monto_afecto", "monto_exento", "monto_vuelto",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = [clean_number(v) for v in df[c]]
        else:
            df[c] = 0.0

    # Para DÉBITO: monto_abono = monto_original si no viene Monto Para Abono
    # (el débito no tiene campo de abono separado, el monto original ES el abono)
    if "monto_abono" not in df.columns or df["monto_abono"].sum() == 0:
        if "monto_original" in df.columns and df["monto_original"].sum() > 0:
            df["monto_abono"] = df["monto_original"]

    # Fechas
    for dc in ["fecha_venta", "fecha_abono"]:
        if dc in df.columns:
            df[dc] = pd.to_datetime(
                df[dc].str.strip(), format="%d/%m/%Y", errors="coerce"
            )

    # Neto calculado: monto_abono - comision_iva + devoluciones
    df["neto"] = (
        df["monto_abono"]
        - df["comision_iva"]
        - df.get("comision_adicional_iva", 0)
        + df.get("devolucion_comision", 0)
    )

    # Hash único para deduplicación
    hash_fields = ["tipo_transaccion", "fecha_venta", "identificador",
                   "monto_original", "codigo_autorizacion"]
    available = [f for f in hash_fields if f in df.columns]
    if available:
        df["hash_unico"] = df[available].astype(str).apply(
            lambda r: str(hash(tuple(r))), axis=1
        )

    return df


# ─── Parser de cartola bancaria ──────────────────────────────────────────────

def parse_cartola_bancaria(file_content: bytes) -> pd.DataFrame:
    """
    Parsea una cartola bancaria en formato CSV o Excel (bytes).
    Detecta automáticamente columnas: fecha, descripción, monto, saldo.
    """
    encoding = detect_encoding(file_content)
    text = file_content.decode(encoding, errors="replace")
    lines = text.splitlines()

    # Detectar separador
    sep = ";" if lines and lines[0].count(";") > lines[0].count(",") else ","

    # Cargar como DataFrame
    import io
    df = pd.read_csv(io.StringIO(text), sep=sep, encoding=encoding,
                     on_bad_lines="skip", dtype=str)

    # Normalizar nombres de columna
    df.columns = [c.strip().lower() for c in df.columns]
    rename = {}
    for c in df.columns:
        if "fecha" in c:
            rename[c] = "fecha"
        elif "descripci" in c or "glosa" in c or "detalle" in c:
            rename[c] = "descripcion"
        elif "monto" in c or "importe" in c or "cargo" in c or "abono" in c:
            if "monto" not in rename.values():
                rename[c] = "monto"
        elif "saldo" in c:
            rename[c] = "saldo"
        elif "refer" in c or "n°" in c or "folio" in c:
            rename[c] = "referencia"

    df = df.rename(columns=rename)

    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce").astype(str)
    if "monto" in df.columns:
        df["monto"] = df["monto"].apply(clean_number)
    if "referencia" not in df.columns:
        df["referencia"] = ""
    if "descripcion" not in df.columns:
        df["descripcion"] = ""

    cols = [c for c in ["fecha", "descripcion", "monto", "referencia"] if c in df.columns]
    return df[cols].dropna(subset=["fecha"]) if "fecha" in df.columns else pd.DataFrame()


# ─── Aliases de columnas para Cartola de Movimientos ─────────────────────────

_CARTOLA_MOV_COL_ALIAS = {
    "fecha venta":                    "fecha_venta",
    "local":                          "local_codigo",
    "identificaci\u00f3n local":      "local_nombre",   # Identificación Local
    "identificacion local":           "local_nombre",
    "tipo movimiento":                "tipo_transaccion",
    "tipo tarjeta":                   "tipo_tarjeta",
    "identificador":                  "identificador",
    "tipo cuota":                     "tipo_cuota",
    "monto afecto":                   "monto_original",
    "monto exento":                   "monto_exento",
    "c\u00f3digo autorizaci\u00f3n":  "codigo_autorizacion",  # Código Autorización
    "codigo autorizacion":            "codigo_autorizacion",
    "n\u00b0 cuotas":                 "numero_cuota",   # N° Cuotas
    "n° cuotas":                      "numero_cuota",
    "numero cuotas":                  "numero_cuota",
    "monto cuota":                    "monto_cuota_unit",
    "primer abono":                   "fecha_abono",
    "n\u00b0 boleta":                 "numero_boleta",  # N° Boleta
    "n° boleta":                      "numero_boleta",
    "monto vuelto":                   "monto_vuelto",
}


def _find_cartola_header(lines: list) -> int:
    """Detecta la línea de encabezado de la Cartola de Movimientos."""
    for i, line in enumerate(lines):
        low = line.lower()
        # Encabezado específico de cartola-movimientos
        if "fecha venta" in low and "local" in low and (
            "tipo movimiento" in low or "tipo tarjeta" in low
        ):
            return i
    return -1


def _normalize_cartola_mov_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza el DataFrame de la Cartola de Movimientos Transbank."""

    # ── Renombrar columnas ────────────────────────────────────────────────────
    # Primero coincidencia exacta, luego por substring (evita que "local"
    # capture "identificación local" antes de que este último tenga su alias)
    rename_map = {}
    for col in df.columns:
        col_low = col.lower().strip()
        # 1) exacto
        if col_low in _CARTOLA_MOV_COL_ALIAS:
            rename_map[col] = _CARTOLA_MOV_COL_ALIAS[col_low]
            continue
        # 2) alias como substring del nombre de columna (aliases largos)
        for alias, canonical in _CARTOLA_MOV_COL_ALIAS.items():
            if len(alias) > 6 and alias in col_low:
                rename_map[col] = canonical
                break

    df = df.rename(columns=rename_map)
    df["tipo_archivo"] = "CARTOLA"

    # ── local_codigo: solo el número ─────────────────────────────────────────
    if "local_codigo" in df.columns:
        df["local_codigo"] = df["local_codigo"].astype(str).str.strip()
    else:
        df["local_codigo"] = ""

    # ── local_nombre: quitar dirección, dejar solo nombre tienda ─────────────
    if "local_nombre" in df.columns:
        df["local_nombre"] = df["local_nombre"].apply(_extract_nombre_local)
    else:
        df["local_nombre"] = ""

    # ── tipo_transaccion: quitar " $" al final ────────────────────────────────
    if "tipo_transaccion" in df.columns:
        df["tipo_transaccion"] = (
            df["tipo_transaccion"]
            .str.replace(r"\s*\$\s*$", "", regex=True)
            .str.replace("Anulaci\u00f3n", "Anulacion", regex=False)
            .str.strip()
        )
    else:
        df["tipo_transaccion"] = "Venta"

    # ── tipo_cuota: normalizar "-" y "Venta $" → "SC" ────────────────────────
    if "tipo_cuota" in df.columns:
        df["tipo_cuota"] = (
            df["tipo_cuota"]
            .str.replace("-", "SC", regex=False)
            .str.replace(r"Venta\s*\$?", "SC", regex=True)
            .str.strip()
        )
    else:
        df["tipo_cuota"] = "SC"

    # ── Parsear N° Cuotas: "S/C" → (1,1) | "1/3" → (1,3) ───────────────────
    cuota_col = "numero_cuota"
    if cuota_col in df.columns:
        cuotas = df[cuota_col].apply(parse_cuota)
        df["cuota_actual"] = cuotas.apply(lambda x: x[0])
        df["cuota_total"]  = cuotas.apply(lambda x: x[1])
    else:
        df["cuota_actual"] = 1
        df["cuota_total"]  = 1

    # ── Columnas numéricas ────────────────────────────────────────────────────
    for c in ["monto_original", "monto_exento", "monto_cuota_unit", "monto_vuelto"]:
        if c in df.columns:
            df[c] = [clean_number(v) for v in df[c]]
        else:
            df[c] = 0.0

    # ── monto_abono: cuota única o monto cuota ────────────────────────────────
    if "monto_cuota_unit" in df.columns:
        df["monto_abono"] = df.apply(
            lambda r: r["monto_cuota_unit"] if r["cuota_total"] > 1 else r["monto_original"],
            axis=1,
        )
    else:
        df["monto_abono"] = df.get("monto_original", 0)

    # ── Comisión: la cartola no la trae, se pone en 0 ────────────────────────
    for c in ["comision_iva", "comision_adicional_iva", "devolucion_comision",
              "monto_anulacion", "monto_retencion"]:
        df[c] = 0.0

    df["neto"] = df["monto_abono"]

    # ── Fechas ────────────────────────────────────────────────────────────────
    if "fecha_venta" in df.columns:
        df["fecha_venta"] = pd.to_datetime(
            df["fecha_venta"].str.strip(),
            format="%d/%m/%Y %H:%M",
            errors="coerce",
        )
    if "fecha_abono" in df.columns:
        df["fecha_abono"] = pd.to_datetime(
            df["fecha_abono"].str.strip(),
            format="%d/%m/%Y",
            errors="coerce",
        )

    # ── Hash único ────────────────────────────────────────────────────────────
    hash_fields = ["tipo_transaccion", "fecha_venta", "identificador",
                   "monto_original", "codigo_autorizacion"]
    available = [f for f in hash_fields if f in df.columns]
    if available:
        df["hash_unico"] = df[available].astype(str).apply(
            lambda r: str(hash(tuple(r))), axis=1
        )

    return df


def _extract_nombre_local(full_name: str) -> str:
    """
    Extrae solo el nombre de la tienda quitando la dirección.
    'AURUS PRAT M A MATTA 2604SN'          → 'AURUS PRAT'
    'AURUS LA SERENA ARTURO PRAT 597SN'    → 'AURUS LA SERENA'
    'AURUS ALTO HOSPICIO LOS ALAMOS 3048SN'→ 'AURUS ALTO HOSPICIO'
    """
    if not full_name or not str(full_name).strip():
        return ""
    name = str(full_name).strip().upper()

    # Cortar antes del primer dígito (número de calle)
    m = re.search(r'\s+\d', name)
    if m:
        name = name[:m.start()].strip()

    # Quitar palabras típicas de dirección que quedaron
    street_words = [
        "M A", "CALLE", "AVENIDA", "ALMTE", "ARTURO", "JOSE SANTOS",
        "LATORRE", "OHIGGINS", "MAIPU", "THOMPSON", "ALDUNATE",
        "GOROSTIAGA", "VIVAR", "CHACABUCO", "LOS ALAMOS", "OSSA",
        "ARTURO PRAT", "ARTURO GALLO", "BALMACEDA", "VICUNA MACKENNA",
        "21 DE MAYO", "18 DE SEPTIEMBRE", "ARTURO GALLO",
    ]
    for word in street_words:
        if name.endswith(" " + word):
            name = name[: -(len(word) + 1)].strip()

    return name


def parse_cartola_movimientos(file_content: bytes) -> Tuple[Dict, pd.DataFrame]:
    """
    Parsea el archivo 'cartola-movimientos-YYYYMM.csv' de Transbank.

    Columnas reales del archivo:
        Fecha Venta ; Local ; Identificación Local ; Tipo Movimiento ;
        Tipo Tarjeta ; Identificador ; Tipo Cuota ; Monto Afecto ;
        Monto Exento ; Código Autorización ; N° Cuotas ; Monto Cuota ;
        Primer Abono ; N° Boleta ; Monto Vuelto

    Retorna:
        meta : dict con RUT, nombre, período
        df   : DataFrame normalizado
    """
    encoding = detect_encoding(file_content)
    text = file_content.decode(encoding, errors="replace")
    lines = text.splitlines()

    # Metadatos (RUT, nombre, período)
    meta = parse_metadata(lines)
    meta["tipo_archivo"] = "CARTOLA"

    # Buscar encabezado de datos
    header_idx = _find_cartola_header(lines)
    if header_idx == -1:
        return meta, pd.DataFrame()

    columns_raw = [c.strip() for c in lines[header_idx].split(";")]
    # Quitar columna vacía final si existe
    if columns_raw and columns_raw[-1] == "":
        columns_raw = columns_raw[:-1]

    rows = []
    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        parts = line.split(";")
        # La primera columna debe ser una fecha (dd/mm/yyyy hh:mm)
        if not re.match(r"\d{2}/\d{2}/\d{4}", parts[0].strip() if parts else ""):
            continue
        # Padding si tiene menos columnas
        while len(parts) < len(columns_raw):
            parts.append("")
        row = {columns_raw[j]: parts[j].strip() for j in range(len(columns_raw))}
        rows.append(row)

    if not rows:
        return meta, pd.DataFrame()

    df = pd.DataFrame(rows)
    df = _normalize_cartola_mov_df(df)
    return meta, df
