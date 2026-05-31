# CLAUDE.md — Guía de estilo y convenciones del proyecto

## Propósito del proyecto

Herramienta Python para calcular y generar información fiscal relativa a la declaración de la renta española, enfocada en:

- Compraventa de ETFs y acciones (ganancias/pérdidas patrimoniales, regla FIFO, regla antiaplicación)
- Dividendos (rendimientos del capital mobiliario, Art. 25.1.a LIRPF; conversión FX via DeGiro o BCE)
- Cuentas remuneradas y depósitos (rendimientos del capital mobiliario)

## Estructura del proyecto

```
renta/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .gitignore
├── requirements.in      # todas las dependencias (editables)
├── requirements.txt     # compiladas con pip-compile
├── src/
│   └── renta/
│       ├── etfs/        # cálculos de ETFs y acciones
│       ├── dividends/   # dividendos: parser, calculadora, report, ECB FX
│       ├── cuentas/     # cuentas remuneradas y depósitos
│       └── utils/       # utilidades compartidas
├── tests/
│   ├── conftest.py
│   ├── etfs/
│   ├── dividends/
│   └── cuentas/
└── docs/
    ├── spec/            # especificaciones de software
    └── referencia/      # documentos de referencia (normativa AEAT, etc.)
```

## Idioma

- **Todo el código** (Python, configs, comentarios, docstrings): **inglés obligatorio**
- **Documentos Markdown** (CLAUDE.md, README.md, docs/): inglés por defecto, español opcional

## Convenciones de código

### Estilo general

- **Python 3.11+**
- Formateo: `black` (line length 100)
- Linting: `ruff`
- Type checking: `mypy` (modo strict)
- Todas las funciones públicas deben tener type hints completos

### Nombres

- Variables y funciones: `snake_case`
- Clases: `PascalCase`
- Constantes: `UPPER_SNAKE_CASE`
- Módulos y paquetes: `snake_case`
- Evitar abreviaturas salvo las estándar del dominio fiscal: `irpf`, `isin`, `fifo`

### Dominio fiscal — terminología preferida

El código es en inglés, pero los nombres deben mapear inequívocamente a los conceptos fiscales de la AEAT:

| Concepto AEAT | Nombre en código |
|---|---|
| Ganancia/pérdida patrimonial | `capital_gain` / `capital_loss` |
| Rendimiento del capital mobiliario | `capital_income` |
| Valor de adquisición | `acquisition_value` |
| Valor de transmisión | `transfer_value` |
| Regla antiaplicación (2 meses / 1 año) | `wash_sale_rule` |
| Criterio FIFO | `fifo` |
| Gastos de compraventa | `transaction_costs` |

### Importes monetarios

- Usar `decimal.Decimal` para todos los cálculos monetarios. Nunca `float`.
- Redondear a 2 decimales solo en la capa de presentación/output.

### Fechas

- Usar `datetime.date` para fechas de operación (sin hora).
- Formato de entrada/salida: `ISO 8601` (`YYYY-MM-DD`).

### Errores y validación

- Definir excepciones propias en `renta/utils/exceptions.py`.
- Validar entradas en los puntos de entrada públicos; confiar en los tipos internamente.
- No capturar excepciones genéricas (`except Exception`).

## Tests

- Framework: `pytest`
- Cobertura mínima: 90% en módulos de cálculo
- Un fichero de test por módulo: `tests/etfs/test_fifo.py` ↔ `src/renta/etfs/fifo.py`
- Usar fixtures en `conftest.py` para datos fiscales reutilizables
- Los tests no deben acceder a red, ficheros externos, ni estado global

Ejecutar tests:
```bash
pytest
pytest --cov=renta --cov-report=term-missing
```

## Gestión de dependencias

Usamos `pip-tools` (`pip-compile` / `pip-sync`). Todas las dependencias (producción y desarrollo) están en `requirements.in`.

### Añadir una dependencia

1. Añadir el paquete a `requirements.in`
2. `pip-compile requirements.in -o requirements.txt`
3. `pip-sync requirements.txt`

### Actualizar todas las dependencias

```bash
pip-compile --upgrade requirements.in -o requirements.txt
pip-sync requirements.txt
```

## Documentación

- `docs/spec/` — especificaciones funcionales y técnicas del software
- `docs/referencia/` — normativa AEAT, manuales IRPF, resoluciones DGT relevantes

Los documentos de especificación deben referenciar la normativa concreta (artículo de la Ley 35/2006 IRPF, etc.) que justifica cada cálculo implementado.

## Comandos útiles

```bash
# Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Instalar entorno de desarrollo
pip install pip-tools
pip-sync requirements.txt

# Formatear
black src/ tests/

# Linting
ruff check src/ tests/

# Type checking
mypy src/

# Tests con cobertura
pytest --cov=renta --cov-report=term-missing
```
