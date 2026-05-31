# Especificación: Rendimientos del Capital Mobiliario — Dividendos

## 1. Objetivo

Calcular los rendimientos del capital mobiliario derivados de dividendos y distribuciones de acciones y ETFs cotizados, determinando los importes a introducir en la declaración del IRPF mediante la plataforma Renta Web de la AEAT. Se incluye el tratamiento de retenciones en origen nacionales y extranjeras, y la deducción por doble imposición internacional.

## 2. Base normativa

| Concepto | Referencia |
|---|---|
| Dividendos como rendimientos del capital mobiliario | Art. 25.1.a Ley 35/2006 IRPF |
| Rendimiento neto (gastos deducibles) | Art. 26 Ley 35/2006 IRPF |
| Integración en base imponible del ahorro | Art. 46.a y Art. 49 Ley 35/2006 IRPF |
| Retención a cuenta (tipo general 19%) | Art. 101.4 Ley 35/2006 IRPF |
| Deducción por doble imposición internacional | Art. 80 Ley 35/2006 IRPF |
| Convenios de doble imposición | Red de CDI de España (OCDE) |

## 3. Ámbito de aplicación

Esta especificación cubre:

- **Dividendos de acciones** cotizadas nacionales e internacionales
- **Distribuciones de ETFs** cotizados de reparto (distributing/income share class)
- Retenciones practicadas **en España** (19%) por custodios nacionales
- Retenciones practicadas **en origen** (impuesto extranjero) por el país de la entidad emisora
- Operativas reportadas en el **formato de exportación XLSX del extracto de cuenta (Cuenta) de DeGiro**

No cubre (fuera de alcance v1):

- Dividendos de fondos no cotizados (SICAV, fondo tradicional)
- Dividendos de acciones no cotizadas
- ETFs de acumulación (no distribuyen; tributan solo en transmisión)
- Prima de asistencia a juntas (tratamiento específico según importe y entidad)
- Dividendos en especie

## 4. Conceptos fiscales clave

### 4.1 Rendimiento íntegro

El rendimiento íntegro es el dividendo **bruto**: el importe antes de aplicar cualquier retención, tanto española como extranjera.

```
rendimiento_integro = dividendo_bruto
```

DeGiro abona el importe **neto** en cuenta (tras retención en origen). El importe bruto debe reconstruirse sumando la retención deducida.

### 4.2 Gastos deducibles (Art. 26 LIRPF)

En la práctica, los gastos deducibles en dividendos de valores cotizados en cuenta de valores son **cero**. Las comisiones de custodia y administración de DeGiro no son deducibles como gasto del capital mobiliario (no son gastos de administración y depósito directamente imputables a la obtención del rendimiento según criterio AEAT).

### 4.3 Retención española (19%)

Para valores custodiados en España, el custodio retiene el 19% del importe bruto. Para valores en DeGiro (custodio neerlandés), **DeGiro no practica retención española**; el contribuyente declara el bruto y los importes retenidos en origen se deducen vía doble imposición internacional (§ 6).

### 4.4 Rendimiento neto

```
rendimiento_neto = rendimiento_integro - gastos_deducibles
                 = rendimiento_integro  (gastos = 0 en práctica)
```

## 5. Formato de entrada — Extracto de cuenta XLSX de DeGiro

### 5.1 Estructura del fichero

DeGiro ofrece dos exportaciones distintas:

| Exportación | Contenido | Módulo que la consume |
|---|---|---|
| **Transacciones** (`Transacciones_YYYY.xlsx`) | Órdenes de compra/venta | `renta.etfs` |
| **Cuenta** (`Cuenta_YYYY.xlsx`) | Movimientos de efectivo: dividendos, retenciones, intereses, comisiones | `renta.dividends` |

Esta especificación usa únicamente el fichero **Cuenta**.

### 5.2 Columnas del fichero Cuenta

El fichero tiene 12 columnas. Las columnas de importe (Variación y Saldo) están cada una **partidas en dos**: primero la moneda, luego el importe numérico. Solo la columna de moneda tiene cabecera en la fila de encabezados; la columna de importe contigua no tiene nombre.

| Pos. | Cabecera | Tipo | Notas |
|---|---|---|---|
| 0 | `Fecha` | String `DD-MM-YYYY` | Fecha del movimiento (contable) |
| 1 | `Hora` | String `HH:MM` | |
| 2 | `Fecha valor` | String `DD-MM-YYYY` | Fecha de liquidación efectiva |
| 3 | `Producto` | String o `None` | Nombre del valor; `None` en movimientos de efectivo |
| 4 | `ISIN` | String o `None` | Identificador del valor; `None` en movimientos de efectivo |
| 5 | `Descripción` | String | Tipo de movimiento (ver § 5.3) |
| 6 | `Tipo` | Float o `None` | **Tipo de cambio** (divisa/EUR) en filas `Retirada Cambio de Divisa`; `None` en el resto |
| 7 | `Variación` *(moneda)* | String o `None` | Moneda del movimiento (`EUR`, `USD`, etc.); `None` si sin importe |
| 8 | *(sin cabecera)* | Float o `None` | **Importe** del movimiento; positivo = entrada, negativo = salida |
| 9 | `Saldo` *(moneda)* | String | Moneda del saldo (normalmente `EUR`) |
| 10 | *(sin cabecera)* | Float | Saldo de la cuenta tras el movimiento |
| 11 | `ID Orden` | String o `None` | UUID de la orden; `None` para dividendos y movimientos no operativos |

### 5.3 Tipos de descripción relevantes

| Descripción (campo pos. 5) | Significado | ISIN (pos. 4) | Variación (pos. 8) |
|---|---|---|---|
| `Dividendo` | Dividendo neto abonado al inversor (tras retención en origen si la hay) | Presente | Positivo, en divisa del valor |
| `Retención del dividendo` | Retención practicada en el país de origen | Presente | Negativo, en divisa del valor |
| `Retirada Cambio de Divisa` | Cargo en divisa extranjera al convertir a EUR | **`None`** para dividendos; presente para ventas | Negativo |
| `Ingreso Cambio de Divisa` | Abono en EUR resultado de la conversión | `None` | Positivo, en EUR |

Las últimas dos filas solo aparecen cuando la divisa del dividendo ≠ EUR. **La presencia o ausencia de ISIN distingue si la conversión corresponde a un dividendo (ISIN=None) o a una venta (ISIN presente).**

Filas con otras descripciones se ignoran en este módulo.

### 5.4 Vinculación dividendo ↔ retención

Un evento fiscal de dividendo se compone de **una o dos filas** del extracto:

1. Fila de dividendo (`Variación > 0`) con un ISIN.
2. Fila de retención (`Variación < 0`) con el mismo ISIN y la **misma fecha**.

La clave de agrupación es `(ISIN, Fecha)`. Si no existe fila de retención, la retención en origen es cero (p. ej. algunos ETFs domiciliados en Irlanda sobre índices no-americanos).

### 5.5 Dividendos en moneda extranjera — conversión a EUR

**DeGiro no convierte automáticamente los dividendos a EUR** en el momento del pago. Los registra en la divisa original (p. ej. USD). Sin embargo, **DeGiro realiza la conversión en el día hábil siguiente** y la materializa como dos filas adicionales en el extracto:

| Descripción | Moneda | Importe | Tipo (pos. 6) |
|---|---|---|---|
| `Retirada Cambio de Divisa` | Divisa original (USD) | Negativo (importe neto del dividendo) | **Tipo de cambio** (divisa/EUR) |
| `Ingreso Cambio de Divisa` | EUR | Positivo (equivalente en EUR) | `None` |

Estas dos filas **no tienen ISIN** (pos. 4 = `None`) ni ID Orden (pos. 11 = `None`), lo que las distingue de conversiones de compraventa (que sí tienen ISIN).

#### Criterio de vinculación (confirmado en todos los casos del dataset)

```
Retirada.FechaValor == Dividendo.Fecha
```

El `Fecha valor` (pos. 2) de la fila `Retirada Cambio de Divisa` es siempre igual a la `Fecha` (pos. 0) de su evento de dividendo. Esto permite vincularlas sin ambigüedad.

Validación adicional: `abs(Retirada.importe)` ≈ `sum(Dividendo.neto)` para el mismo ISIN y fecha.

#### Cálculo de importes en EUR

```
net_eur      = Ingreso.importe                          # abonado en EUR por DeGiro
fx_rate      = Retirada.Tipo                            # divisa/EUR, p. ej. 1.0566
withholding_eur = withholding_divisa / fx_rate          # retención convertida
gross_eur    = net_eur + withholding_eur                # rendimiento íntegro a declarar
```

No se necesita consultar el BCE; DeGiro proporciona el tipo y el importe convertido directamente.

#### Caso sin conversión (divisa == EUR)

Si la moneda del dividendo es EUR (pos. 7 = `'EUR'`), no hay filas de Retirada/Ingreso. Los importes de `Dividendo` y `Retención del dividendo` se usan directamente sin conversión.

### 5.6 Ejemplo de filas del fichero Cuenta (datos reales)

**Caso 1 — Acción americana con retención (Apple):**

| Fecha | FechaValor | ISIN | Descripción | Tipo | Mon. | Importe |
|---|---|---|---|---|---|---|
| 17-05-2024 | 16-05-2024 | US0378331005 | Dividendo | — | USD | 1,25 |
| 17-05-2024 | 16-05-2024 | US0378331005 | Retención del dividendo | — | USD | −0,19 |
| 18-05-2024 | **17-05-2024** | **None** | Retirada Cambio de Divisa | **1,0897** | USD | −1,06 |
| 18-05-2024 | **17-05-2024** | **None** | Ingreso Cambio de Divisa | — | EUR | 0,97 |

- `Retirada.FechaValor (17-05-2024)` = `Dividendo.Fecha (17-05-2024)` ✓
- `abs(Retirada) = 1,06` = `1,25 − 0,19` ✓
- `net_eur = 0,97`; `fx_rate = 1,0897`; `withholding_eur = 0,19 / 1,0897 ≈ 0,17`; `gross_eur = 0,97 + 0,17 = 1,14`

**Caso 2 — ETF irlandés sin retención (iShares S&P 500):**

| Fecha | FechaValor | ISIN | Descripción | Tipo | Mon. | Importe |
|---|---|---|---|---|---|---|
| 27-06-2024 | 26-06-2024 | IE0031442068 | Dividendo | — | USD | 6,25 |
| 28-06-2024 | **27-06-2024** | **None** | Retirada Cambio de Divisa | **1,0731** | USD | −6,25 |
| 28-06-2024 | **27-06-2024** | **None** | Ingreso Cambio de Divisa | — | EUR | 5,82 |

- Sin retención → `foreign_withholding = 0`; `gross_eur = net_eur = 5,82`
- ⚠ **ETF irlandés**: esta distribución es íntegramente rendimiento del capital mobiliario sin deducción por doble imposición (ver § 6.3)

### 5.7 Fallback BCE cuando no se encuentran las filas de conversión FX

Cuando para un dividendo con moneda ≠ EUR no se localiza la fila `Retirada Cambio de Divisa` (o existe pero `Tipo = None`), el módulo **no falla ni interrumpe el cálculo**. En su lugar aplica automáticamente el tipo de cambio de referencia del BCE para la fecha del dividendo.

#### Fuente BCE

El BCE publica tipos de cambio diarios de referencia (días hábiles desde 1999) en:

```
https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip
```

El ZIP contiene un CSV con columnas `Date, USD, GBP, ...` donde cada valor es unidades de divisa por 1 EUR. Si la fecha del dividendo es fin de semana o festivo, se usa el tipo del **día hábil anterior**.

#### Prioridad de fuentes de tipo de cambio

```
1. Retirada Cambio de Divisa (Tipo, pos. 6)   ← fuente preferida
2. BCE (eurofxref-hist)                        ← fallback automático
3. fx_overrides proporcionados al llamar       ← anula 1 y 2 para ese evento
```

Los `fx_overrides` permiten correcciones puntuales en casos excepcionales (p. ej. `Retirada.Tipo = None` sin dato BCE disponible):

```python
fx_overrides: dict[tuple[str, date], Decimal]  # (isin, fecha_dividendo) → tipo divisa/EUR
result = calculate(path, tax_year=2021, fx_overrides={
    ("US0378331005", date(2021, 8, 13)): Decimal("1.1807"),
})
```

#### Modelo: campo `fx_source`

```python
class FxSource(str, Enum):
    DEGIRO   = "degiro"    # Retirada Cambio de Divisa encontrada
    ECB      = "ecb"       # fallback BCE
    OVERRIDE = "override"  # fx_overrides del llamador
```

`DividendEvent.fx_source` registra qué fuente se usó. Los eventos con `fx_source != DEGIRO` se agrupan en una sección específica del informe.

#### Sección del informe para eventos en fallback

El informe de salida incluye, al final del apartado de dividendos, una sección **"Conversiones FX en modo fallback"** que aparece únicamente si hay al menos un evento afectado:

```
═══════════════════════════════════════════════════════════
CONVERSIONES FX — MODO FALLBACK (N eventos)
═══════════════════════════════════════════════════════════

Los siguientes dividendos no tenían en el extracto de cuenta
las filas de conversión automática que DeGiro genera normalmente:

  Patrón esperado:
  • "Retirada Cambio de Divisa" (ISIN vacío, FechaValor = Fecha
    del dividendo, importe USD negativo, tipo de cambio en col. Tipo)
  • "Ingreso Cambio de Divisa"  (ISIN vacío, misma Fecha y Hora
    que la Retirada, importe EUR positivo)

  Causa más probable: el extracto no cubre el día siguiente al
  último dividendo del periodo. Exportar con rango +1 día no altera
  los cálculos pero puede hacer desaparecer esta sección.

  Para estos eventos se ha usado el tipo de referencia del BCE
  (eurofxref-hist) correspondiente a la fecha del dividendo.
  Verificar que los importes EUR son correctos antes de declarar.

  Fecha        ISIN           Valor            Divisa  Bruto divisa  FX (BCE)   Bruto EUR
  -----------  -------------  ---------------  ------  ------------  ---------  ---------
  2021-08-13   US0378331005   APPLE INC        USD         1,44      1,1807     1,22
  ...

  [OVERRIDE] 2021-08-13  US0378331005  tipo manual: 1,1807
═══════════════════════════════════════════════════════════
```

La sección incluye:
- Explicación del patrón que se buscaba y no se encontró
- Causa probable y cómo resolverla (re-exportar el extracto)
- Tabla con todos los eventos afectados, la fuente usada y el tipo aplicado
- Marcado explícito `[OVERRIDE]` para los eventos con tipo manual

## 6. Doble imposición internacional (Art. 80 LIRPF)

### 6.1 Descripción

Cuando un dividendo ha sido sometido a retención en el país de la entidad emisora (impuesto extranjero), el contribuyente puede deducir dicho importe de la cuota íntegra española, evitando la doble imposición.

La deducción se limita al **menor** de:

```
deduccion_maxima = min(retencion_extranjera, cuota_espanola_sobre_ese_dividendo)
```

donde:

```
cuota_espanola_sobre_ese_dividendo = rendimiento_integro × tipo_marginal_ahorro
```

El tipo marginal del ahorro depende de la base liquidable total del contribuyente (ver § 8.4). En la práctica, para contribuyentes con base del ahorro ≤ 50.000 €, el tipo es 19–21%, y las retenciones del 15% (EEUU vía W-8BEN) son siempre deducibles íntegramente.

### 6.2 Países y tipos de retención habituales

| País emisor | Tipo CDI habitual | Tipo sin CDI | Notas |
|---|---|---|---|
| EEUU (W-8BEN presentado) | 15% | 30% | Acciones individuales americanas |
| Alemania | 15% | 25% | |
| Francia | 12,8% | 30% | |
| Países Bajos | 15% | 15% | |
| **Irlanda (ETFs UCITS)** | **0%** | 0% | Ver § 6.3 |
| España | 19% (retención doméstica) | — | DeGiro no practica retención española |

> Estos tipos son orientativos. El tipo aplicable depende del CDI vigente y de si se ha presentado la documentación correcta al custodio.

### 6.3 ETFs UCITS domiciliados en Irlanda

Los ETFs con ISIN `IE` (p. ej. iShares, Vanguard UCITS) distribuyen dividendos a inversores no residentes en Irlanda **sin retención en origen** (0%). Esto está confirmado por los datos reales de DeGiro: los dividendos de `IE0031442068` (iShares Core S&P 500 Dist) no generan fila de `Retención del dividendo`.

**Por qué el subyacente americano no genera retención reclamable por el inversor español:**

El ETF irlandés sí paga el 15% de WHT estadounidense sobre los dividendos que recibe de las acciones americanas en cartera. Sin embargo, este impuesto se absorbe **dentro del fondo** (reduce el NAV/distribución) y no se traslada como un crédito fiscal al inversor final. El inversor español solo ve la distribución neta del ETF, declarable íntegramente como rendimiento del capital mobiliario sin deducción por doble imposición.

En consecuencia: para ISIN con prefijo `IE`, `foreign_withholding = 0` y `deductible_foreign_tax = 0`, aunque el subyacente sea de renta variable americana.

### 6.3 Tratamiento en el informe

El módulo calcula y reporta por dividendo:

| Campo | Descripción |
|---|---|
| `gross_amount` | Rendimiento íntegro (bruto reconstituido) |
| `foreign_withholding` | Retención en origen (del extracto de cuenta) |
| `deductible_foreign_tax` | Mínimo entre retención y cuota española estimada |
| `net_amount` | Importe neto abonado por DeGiro |

La cuota española estimada se calcula usando el tipo marginal del tramo inferior del ahorro (19%) como aproximación conservadora. El contribuyente ajustará en Renta Web según su base real.

## 7. Algoritmo de cálculo

```
FASE 1 — Agrupar eventos de dividendo
  Filtrar filas: Descripción ∈ {'Dividendo', 'Retención del dividendo'} AND ISIN no vacío
  Para cada grupo (ISIN, Fecha):
    dividendo_row  = fila con Descripción='Dividendo'
    retencion_row  = fila con Descripción='Retención del dividendo' (puede no existir)
    currency       = dividendo_row.moneda (pos. 7)
    net_divisa     = dividendo_row.importe (pos. 8)
    ret_divisa     = abs(retencion_row.importe) si existe, si no 0

FASE 2 — Conversión a EUR
  Si currency == 'EUR':
    net_eur = net_divisa
    ret_eur = ret_divisa
    fx_rate = None

  Si currency ≠ 'EUR':
    Buscar fila 'Retirada Cambio de Divisa' donde:
      ISIN es None
      FechaValor == Fecha del dividendo
      moneda == currency
    retirada_row = fila encontrada
    ingreso_row  = fila 'Ingreso Cambio de Divisa' con mismos (Fecha, Hora) que retirada_row

    fx_rate  = retirada_row.Tipo (pos. 6)
    net_eur  = ingreso_row.importe
    ret_eur  = ret_divisa / fx_rate

    Validación: abs(retirada_row.importe) ≈ net_divisa  → si no coincide, emitir advertencia

FASE 3 — Calcular evento fiscal
  gross_amount          = net_eur + ret_eur
  foreign_withholding   = ret_eur
  deductible_foreign_tax = min(foreign_withholding, gross_amount × Decimal('0.19'))

  Crear DividendEvent(
    date=Fecha, isin, ticker=Producto,
    gross_amount, foreign_withholding,
    deductible_foreign_tax, net_amount=net_eur,
    original_currency=currency, fx_rate
  )

Filtrar por ejercicio fiscal: year(Fecha) == tax_year
Calcular DividendSummary: sumas de gross_amount, foreign_withholding, deductible_foreign_tax
Agrupar por country_code (prefijo de ISIN: 'US' → EEUU, 'IE' → Irlanda, etc.)
```

## 8. Informe de salida y casillas IRPF

### 8.1 Cómo introducir los datos en Renta Web

Navegar a:

> **Apdo. B1 › Rendimientos del capital mobiliario a integrar en la base imponible del ahorro**
> › Dividendos y demás rendimientos por la participación en fondos propios de entidades

Para cada valor (o introduciendo el total agregado si se prefiere):

| Campo Renta Web | Valor a introducir |
|---|---|
| Ingresos íntegros | `gross_amount` total del valor |
| Gastos deducibles | 0,00 |
| Retenciones e ingresos a cuenta | Retención española practicada (0 para DeGiro) |

Para la deducción por doble imposición internacional, navegar a:

> **Apdo. I › Deducciones › Deducción por doble imposición internacional**

Introducir por cada país de origen:

| Campo | Valor |
|---|---|
| País | País de la entidad emisora |
| Rentas sometidas a imposición en el extranjero | `gross_amount` (suma de dividendos de ese país) |
| Impuesto satisfecho en el extranjero | `foreign_withholding` (suma de retenciones de ese país) |

### 8.2 Casillas de resumen (Modelo IRPF 2024 — verificar cada año)

| Casilla | Nombre | Valor |
|---|---|---|
| **0029** | Dividendos íntegros — rendimientos capital mobiliario ahorro | Suma `gross_amount` |
| **0031** | Gastos deducibles capital mobiliario ahorro | 0,00 |
| **0595** | Retenciones sobre rendimientos capital mobiliario | Retención española (0 para DeGiro) |
| **0588** | Deducción doble imposición internacional — cuota íntegra | Suma `deductible_foreign_tax` |

> ⚠ Los números de casilla pueden variar entre ejercicios. Verificar en el Modelo 100 oficial del año declarado.

### 8.3 Compensación con pérdidas patrimoniales (Art. 49 LIRPF)

Los rendimientos del capital mobiliario del ahorro (dividendos) se integran en la base del ahorro junto con las ganancias patrimoniales. Las pérdidas patrimoniales pueden compensar hasta el **25%** de los rendimientos positivos del capital mobiliario del ahorro en el mismo ejercicio.

### 8.4 Tramos del ahorro (IRPF 2023/2024)

| Base liquidable del ahorro | Tipo |
|---|---|
| Hasta 6.000 € | 19% |
| 6.001 € – 50.000 € | 21% |
| 50.001 € – 200.000 € | 23% |
| 200.001 € – 300.000 € | 27% |
| Más de 300.000 € | 28% |

## 9. Casos límite y advertencias

| Situación | Tratamiento |
|---|---|
| Dividendo sin fila de `Retención del dividendo` | `foreign_withholding = 0`; no error (habitual en ETFs irlandeses) |
| Más de una fila de retención para el mismo (ISIN, Fecha) | Sumar todas las retenciones del grupo |
| Dividendo en USD sin `Retirada Cambio de Divisa` asociada | Fallback BCE automático; `fx_source = ECB`; aparece en sección fallback del informe (§ 5.7) |
| `Retirada` encontrada pero `Ingreso Cambio de Divisa` no existe | Fallback BCE; las dos filas son siempre par, su ausencia indica fichero probablemente truncado |
| `Retirada.Tipo = None` con moneda ≠ EUR (observado en 2021) | Fallback BCE; si tampoco hay dato BCE disponible, requiere `fx_overrides` (§ 5.7) |
| `abs(Retirada.importe)` ≠ `net_divisa` del dividendo | Advertencia de validación; continuar usando los importes del Ingreso Cambio de Divisa |
| `Retirada Cambio de Divisa` con `Tipo = None` y moneda EUR | Caso antiguo (2021); importe ya en EUR, usar directamente sin conversión |
| ETF de acumulación (no distributing) | No genera filas de dividendo; ignorar en este módulo |
| Retención extranjera > cuota española estimada (19%) | Deducción limitada a la cuota española; exceso no recuperable |
| ETF ISIN `IE...` con subyacente americano (p. ej. iShares S&P 500) | `foreign_withholding = 0`; el WHT USA se absorbe en el fondo (§ 6.3); **el informe lo indica explícitamente** |
| Fila con descripción `Dividendo` pero `ISIN = None` | Marcar como advertencia; excluir del cálculo |

## 10. Módulos de implementación

| Módulo | Responsabilidad |
|---|---|
| `renta.dividends.models` | Modelos de dominio: `DividendEvent`, `DividendSummary` |
| `renta.dividends.parser` | Parsear XLSX Cuenta de DeGiro; agrupar por `(ISIN, Fecha)` |
| `renta.dividends.calculator` | Calcular `gross_amount`, `deductible_foreign_tax` por evento y totales anuales |
| `renta.dividends.report` | Generar informe de texto con casillas IRPF y desglose por país |
| `renta.dividends` | Función pública `calculate(path, tax_year) -> str` |

### 10.1 Modelo de datos principal

```python
@dataclass
class DividendEvent:
    date: date
    isin: str
    ticker: str
    gross_amount: Decimal            # rendimiento íntegro en EUR
    foreign_withholding: Decimal     # retención en origen en EUR (≥ 0)
    deductible_foreign_tax: Decimal  # min(foreign_withholding, gross × 0.19)
    net_amount: Decimal              # importe neto abonado en EUR
    original_currency: str           # moneda original ('EUR', 'USD', ...)
    fx_rate: Decimal | None          # tipo de cambio (divisa/EUR); None si EUR
    fx_source: FxSource              # DEGIRO | ECB | OVERRIDE
    irish_etf_note: bool             # True si ISIN prefix 'IE' → informe lo señala explícitamente

@dataclass
class DividendSummary:
    tax_year: int
    events: list[DividendEvent]
    total_gross: Decimal
    total_foreign_withholding: Decimal
    total_deductible_foreign_tax: Decimal
    by_country: dict[str, Decimal]   # country_code (ISIN prefix) → gross_amount EUR
```
