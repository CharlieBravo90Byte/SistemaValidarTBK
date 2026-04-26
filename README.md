# Sistema de Conciliación Transbank

Aplicación web que automatiza la conciliación, análisis y exportación de transacciones Transbank a partir de los archivos CSV descargados desde el portal.

## Despliegue

- App online: https://sistemavalidartbk-mzjina8xyu64i5pwe34tjf.streamlit.app/
- Repositorio: https://github.com/CharlieBravo90Byte/SistemaValidarTBK

## ¿Qué hace?

Reemplaza un proceso manual basado en una plantilla Excel y automatiza el ciclo completo:

1. **Carga** los archivos CSV del portal Transbank.
2. **Parsea y normaliza** cada archivo detectando encoding, encabezados y metadatos.
3. **Persiste** los datos en base de datos (SQLite local o Postgres si está configurado).
4. **Visualiza** dashboards con KPIs, resúmenes diarios y cuotas pendientes.
5. **Exporta** archivos listos para importar en Softland ERP.

## Archivos que procesa

| Archivo | Descripción |
|---|---|
| `extraccion-masiva-debito-pesos-*.CSV` | Ventas con tarjeta débito |
| `extraccion-masiva-credito-pesos-*.CSV` | Ventas con tarjeta crédito |
| `cartola-movimientos-YYYYMM.CSV` | Cartola de movimientos Transbank |

## Cómo ejecutar localmente

```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

La aplicación queda disponible en `http://localhost:8501`.

## Estructura

```
SistemaTransbank/
├── app.py                  # Entrada Streamlit, navegación y CSS
├── config.py               # Constantes globales
├── requirements.txt        # Dependencias Python
├── assets/                 # Plantilla Excel para flujo manual
├── core/
│   ├── parser.py           # Parseo de los CSV
│   ├── database.py         # Persistencia (SQLite / Postgres)
│   ├── calculator.py       # Cálculo de comisión, IVA, neto y cuotas
│   ├── matcher.py          # Conciliación
│   └── exporter.py         # Exportación a Excel y Softland
├── views/
│   ├── upload.py           # Carga de archivos CSV
│   ├── dashboard.py        # Dashboard global del período
│   ├── sucursales.py       # Detalle por sucursal
│   ├── pendientes.py       # Cuotas pendientes
│   └── softland.py         # Exportación Softland
└── data/                   # Base de datos SQLite local (no versionada)
```

## Flujo de uso

```
Portal Transbank → Descargar CSV → 📤 Cargar → Parseo → Enriquecimiento
                                                          → Persistencia
                                                          → 📊 Dashboard
                                                          → 🏪 Por Sucursal
                                                          → ⏳ Pendientes
                                                          → 📁 Exportación Softland
```

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

## Base de datos

- Por defecto: **SQLite** en `data/transbank.db` (creada automáticamente).
- Si la variable `DATABASE_URL` está definida (variable de entorno o `st.secrets`), se usa ese motor (por ejemplo, Postgres en Neon/Supabase). Formato:

```
postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

La deduplicación se hace por `hash_unico`, por lo que subir el mismo archivo dos veces no genera duplicados.

## Exportación Softland

- Centralización (`softland_centralizacion_YYYY-MM.csv`).
- Diario (`softland_diario_YYYY-MM.csv`).
- Excel global (`reporte_global_YYYY-MM.xlsx`).

Separador `;` · Encoding `latin-1`.

## Flujo manual alternativo

Desde la pantalla de **Cargar Archivos** se puede descargar la plantilla Excel original (`TemplateTransbankV032026.xlsm`) por si se prefiere realizar el proceso manualmente.

## Dependencias principales

| Paquete | Uso |
|---|---|
| `streamlit` | Interfaz web |
| `pandas` | Procesamiento de datos |
| `plotly` | Gráficos interactivos |
| `openpyxl` / `xlsxwriter` | Lectura/escritura Excel |
| `SQLAlchemy` | Acceso a base de datos |
| `psycopg` | Driver Postgres (opcional) |

Requiere Python 3.12+.
