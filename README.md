# Sistema de Conciliación Transbank
**INVERSIONES DEL NORTE LIMITADA · RUT 76421171-5**

Aplicación web interna que reemplaza el proceso manual en Excel (`TemplateTransbankV022026.xlsm`) para conciliar, analizar y exportar las transacciones Transbank de las sucursales **AURUS**.

---

## ¿Para qué sirve?

Cada mes Transbank genera 3 archivos CSV que antes se procesaban a mano en un libro Excel de 9 hojas. Este sistema automatiza ese proceso completo:

1. **Carga** los 3 CSV del portal Transbank
2. **Parsea y normaliza** cada archivo detectando su estructura automáticamente
3. **Guarda** en base de datos SQLite (los datos persisten entre sesiones)
4. **Muestra** dashboards por sucursal, cuotas pendientes y resúmenes globales
5. **Exporta** archivos listos para importar en Softland ERP

---

## Archivos que procesa

| Archivo | Descripción |
|---|---|
| `extraccion-masiva-debito-pesos-*.CSV` | Ventas con tarjeta débito (DB) del período |
| `extraccion-masiva-credito-pesos-*.CSV` | Ventas con tarjeta crédito (VI/MC/AX) del período |
| `cartola-movimientos-YYYYMM.CSV` | Cartola de movimientos Transbank (todos los tipos) |

> Los archivos se descargan manualmente desde el portal Transbank y se suben a través de la interfaz web.

---

## Cómo ejecutar

```bash
# Desde la carpeta del proyecto
cd d:\06.-Proyectos\Transbank\SistemaTransbank

# Instalar dependencias (solo la primera vez)
pip install -r requirements.txt

# Iniciar la aplicación
python -m streamlit run app.py
```

La aplicación queda disponible en **http://localhost:8501**

---

## Estructura del proyecto

```
SistemaTransbank/
│
├── app.py                  # Punto de entrada Streamlit, navegación y CSS
├── config.py               # Constantes globales (rutas, mapas de tipos, estados)
├── requirements.txt        # Dependencias Python
│
├── core/
│   ├── parser.py           # Parsea los 3 CSV de Transbank → DataFrames normalizados
│   ├── database.py         # CRUD SQLite (periodos, movimientos, sucursales)
│   ├── calculator.py       # Cálculo de comisión, IVA, neto y cuotas pendientes
│   ├── matcher.py          # Motor de conciliación (CONCILIADO / PENDIENTE / PARCIAL)
│   └── exporter.py         # Genera archivos de exportación (Excel, Softland CSV)
│
├── views/
│   ├── upload.py           # Pantalla de carga de los 3 archivos CSV
│   ├── dashboard.py        # Resumen global del período con gráficos
│   ├── sucursales.py       # Detalle por sucursal AURUS
│   ├── pendientes.py       # Cuotas pendientes de abono
│   └── softland.py         # Exportación para Softland ERP
│
└── data/
    └── transbank.db        # Base de datos SQLite (se crea automáticamente)
```

---

## Flujo de uso mensual

```
Portal Transbank
      │
      ▼
  Descargar 3 CSV
      │
      ▼
  📤 Carga (upload.py)
  ├─ Seleccionar mes/año
  ├─ Subir CSV Débito
  ├─ Subir CSV Crédito
  └─ Subir Cartola Movimientos
      │
      ▼
  Parseo automático (parser.py)
  ├─ Detecta encoding (latin-1/cp1252)
  ├─ Detecta encabezados y metadatos
  ├─ Normaliza columnas y tipos
  └─ Calcula hash único (deduplicación)
      │
      ▼
  Enriquecimiento (calculator.py)
  ├─ comision_neta = comision_iva * 100/119
  ├─ iva_comision  = comision_iva * 19/119
  ├─ neto_final    = monto_abono - comision_iva + devoluciones
  └─ cuotas_pendientes = cuota_total - cuota_actual
      │
      ▼
  Guardado en SQLite (database.py)
  ├─ Tabla: movimientos
  ├─ Tabla: sucursales
  └─ Tabla: periodos
      │
      ▼
  Consulta y visualización
  ├─ 📊 Dashboard   → KPIs globales + gráficos Plotly
  ├─ 🏪 Sucursales  → Detalle por tienda AURUS
  ├─ ⏳ Pendientes  → Cuotas que aún no se han abonado
  └─ 📁 Softland    → Exporta centralización y asiento diario
```

---

## Sucursales AURUS procesadas

El sistema reconoce automáticamente las ~26 sucursales a partir del campo **Local** de los CSV:

- AURUS COPIAPO · AURUS CALAMA · AURUS ANTOFAGASTA
- AURUS LA SERENA · AURUS COQUIMBO · AURUS OVALLE
- AURUS IQUIQUE · AURUS ARICA · AURUS ALTO HOSPICIO
- AURUS PRAT · AURUS AMATISTA · AURUS LA MINA DE ORO
- _(y otras según período)_

---

## Tipos de tarjeta reconocidos

| Código | Nombre |
|---|---|
| `VI` | VISA |
| `MC` | MASTERCARD |
| `DB` | DÉBITO |
| `AX` | AMEX |
| `CFE` | CRÉDITO FEE |
| `DC` | DINERS |

## Tipos de cuota

| Código | Descripción |
|---|---|
| `SC` | Sin cuota (pago único) |
| `C3C` | 3 cuotas |
| `C6C` | 6 cuotas |
| `C12C` | 12 cuotas |
| `C18C` | 18 cuotas |
| `C24C` | 24 cuotas |

---

## Base de datos

SQLite en `data/transbank.db`. Tablas principales:

| Tabla | Descripción |
|---|---|
| `movimientos` | Todas las transacciones de todos los períodos |
| `sucursales` | Catálogo de sucursales AURUS detectadas |
| `periodos` | Períodos cargados con metadatos (RUT, empresa, totales) |

La deduplicación se hace por `hash_unico` (hash de tipo_transaccion + fecha + identificador + monto + código autorización), por lo que subir el mismo archivo dos veces no duplica datos.

---

## Exportación Softland

Desde la vista **Softland** se generan dos archivos CSV:

- **Centralización** (`softland_centralizacion_YYYY-MM.csv`) — asiento contable agrupado por cuenta
- **Diario** (`softland_diario_YYYY-MM.csv`) — asiento detallado por movimiento
- **Excel global** (`reporte_global_YYYY-MM.xlsx`) — resumen completo del período

Separador: `;` · Encoding: `latin-1`

---

## Dependencias

| Paquete | Uso |
|---|---|
| `streamlit` | Interfaz web |
| `pandas` | Procesamiento de datos |
| `plotly` | Gráficos interactivos |
| `openpyxl` | Lectura/escritura Excel |
| `xlsxwriter` | Exportación Excel avanzada |

```
Python 3.12+
```
