# renta

Herramienta Python para calcular la declaración de la renta española en materia de inversiones financieras.

## Funcionalidades

- **ETFs y acciones**: ganancias/pérdidas patrimoniales con FIFO y regla antiaplicación (Art. 33.5.d / 37.2 LIRPF)
- **Dividendos**: rendimientos del capital mobiliario con deducción por doble imposición (Art. 25.1.a / 80 LIRPF)
- **Cuentas remuneradas y depósitos**: rendimientos del capital mobiliario *(próximamente)*

> Trabajo en progreso, utilizar readme previo y contrastar hasta validación completada.
> Al comparar con el informe de Degiro, nótese que se dice: "Tenga en cuenta que el tipo de cambio utilizado en este informe es el cambio a final del día, por lo que difiere con el utilizado en su cuenta de DEGIRO."

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install pip-tools
pip-sync
```

---

## Uso — ETFs y acciones

### 1. Obtén el fichero de DeGiro

En DeGiro: **Buzón → Transacciones → Seleccionar rango de fechas (todo, 01/01/2020 > Fecha actual) → Exportar → Excel**

Guarda el fichero como `Transactions.xlsx` en `data/input/degiro/` (está en `.gitignore`).

> El informe anual se puede descargar de Buzón → Documentos → Informe anual XXXX (con XXXX igual al año), y puede servir para verificar resultados,
> aunque puede haber diferencias, los valores deberían ser cercanos. Las diferencias pueden deberse a que el resultado "no incluye las comisiones de
> compra/venta. Las Ganancias y Pérdidas (G/P) se calculan usando el cambio de divisa al final del día como se expone en la primera página de
> este informe"

### 2. Genera el informe

```bash
# Imprimir en pantalla
renta etfs Transactions.xlsx 2024

# Guardar en fichero
renta etfs Transactions.xlsx 2024 -o informe_2024.txt
```

También disponible como módulo Python:

```bash
python -m renta etfs Transactions.xlsx 2024
```

Ayuda:

```bash
renta --help
renta etfs --help
```

### 3. Interpreta el informe

Para cada transmisión del ejercicio el informe muestra:

| Campo | Descripción |
|---|---|
| Descripción / ISIN | Para identificar el valor en Renta Web |
| Fecha y valor de adquisición | Precio de compra **con** comisiones incluidas |
| Fecha y valor de transmisión | Precio de venta **neto** de comisiones |
| Resultado | Ganancia o pérdida patrimonial |
| ⚠ Pérdida diferida | Si aplica la regla antiaplicación (Art. 33.5.d LIRPF) |

Al final: totales, casillas IRPF afectadas y cuota estimada.

### 4. Introduce los datos en Renta Web

Navega en tu declaración a:

> **Apdo. C2 › Ganancias y pérdidas patrimoniales derivadas de transmisiones**

Pulsa **Añadir** para cada operación e introduce exactamente los valores del informe.
Los gastos ya están incorporados en adquisición/transmisión — no los añadas por separado.

---

## Uso — Dividendos

### 1. Obtén el fichero de DeGiro

En DeGiro: **Buzón → Estado de cuenta → Seleccionar rango de fechas (todo) → Exportar → Excel**

Guarda el fichero como `Account.xlsx` en `data/input/degiro/` (está en `.gitignore`).

> **Nota**: es un fichero distinto al de ETFs (`Account.xlsx` vs `Transactions.xlsx`).

> El informe anual se puede descargar de Buzón → Documentos → Informe anual XXXX (con XXXX igual al año), y puede servir para verificar resultados,
> aunque puede haber diferencias, los valores deberían ser cercanos. Las diferencias pueden deberse a que el resultado "tipo de cambio utilizado en este informe es el cambio a final del día, por lo que difiere con el utilizado en su cuenta de DEGIRO".


### 2. Genera el informe

Actualmente disponible como API Python:

```python
from pathlib import Path
from renta.dividends import calculate, build_summary

# Informe completo en texto
report = calculate(Path("data/input/degiro/Account.xlsx"), tax_year=2024)
print(report)

# O accede al modelo de datos directamente
summary = build_summary(Path("data/input/degiro/Account.xlsx"), tax_year=2024)
for event in summary.events:
    print(event.ticker, event.gross_amount, event.fx_source)
```

Con un fichero de configuración YAML (via `renta.yaml`):

```yaml
base_path: .
dividends:
  input: data/input/degiro/Account.xlsx
  year: 2024
```

### 3. Conversión de divisas

El módulo resuelve el tipo de cambio en este orden de prioridad:

1. **Override manual** — si proporcionas `fx_overrides={(isin, fecha): Decimal("1.0897")}`, ese tipo prevalece siempre.
2. **DeGiro** — si el fichero contiene filas "Retirada Cambio de Divisa" + "Ingreso Cambio de Divisa" asociadas al dividendo, se usa el tipo implícito en esas filas.
3. **BCE (fallback automático)** — si no se encuentran las filas anteriores, se consulta el histórico de tipos del BCE (`eurofxref-hist.zip`).

El informe indica la fuente de cada tipo con `[ECB]` o `[OVERRIDE]` y explica qué patrón DeGiro se esperaba pero no se encontró.

### 4. Interpreta el informe

El informe muestra por cada dividendo:

| Campo | Descripción |
|---|---|
| Ticker / ISIN | Para identificar el valor en Renta Web |
| Divisa / Tipo FX | Moneda original y tipo de cambio aplicado |
| Bruto EUR | Importe íntegro en euros (casilla 0029) |
| Retención ext. | Impuesto extranjero retenido (para casilla 0588) |
| Deducible | Retención deducible, cap 19% del bruto (Art. 80 LIRPF) |
| ⚠IE | ETF irlandés: retención aplicada internamente, 0% declarada |

Al final: totales, casillas IRPF (0029, 0031, 0595, 0588) y nota sobre doble imposición.

### 5. Introduce los datos en Renta Web

- **Casilla 0029** — Importe íntegro de dividendos
- **Casilla 0031** — Gastos deducibles (normalmente 0)
- **Casilla 0595** — Retenciones practicadas en España (normalmente 0 para dividendos extranjeros)
- **Casilla 0588** — Deducción por doble imposición internacional (retención extranjera deducible)

Navega a:

> **Apdo. D1 › Rendimientos del capital mobiliario → Dividendos y demás rendimientos**

---

## Desarrollo

```bash
# Tests
pytest

# Tests con cobertura
pytest --cov=renta --cov-report=term-missing

# Formatear
black src/ tests/

# Linting
ruff check src/ tests/

# Type checking
mypy src/
```

## Estructura

Ver [CLAUDE.md](CLAUDE.md) para guía de estilo y convenciones completas.

## Base legal

Ley 35/2006, de 28 de noviembre, del Impuesto sobre la Renta de las Personas Físicas.
Ver [docs/referencia/](docs/referencia/) para referencias normativas detalladas.

---

## Aviso legal / Disclaimer

**Esta herramienta se proporciona exclusivamente con fines informativos y educativos.**

Los cálculos que genera pueden contener errores. **No constituye asesoramiento fiscal.**
Verifica siempre los resultados con un asesor fiscal cualificado o con las herramientas
oficiales de la AEAT antes de presentar tu declaración.

Los autores no asumen ninguna responsabilidad por errores, omisiones ni consecuencias
económicas derivadas del uso de este software.

---

*This software is provided for informational and educational purposes only. It does not
constitute tax advice. Results may contain errors. Always verify with a qualified tax
advisor or official AEAT tools. The authors accept no liability for any errors, omissions,
or financial consequences arising from use of this software.*

*Licensed under the [Apache License 2.0](LICENSE).*
