# Especificación: Cálculo de Ganancias y Pérdidas Patrimoniales — Acciones y ETFs

## 1. Objetivo

Calcular las ganancias y pérdidas patrimoniales derivadas de la transmisión de valores negociados en mercados organizados (acciones e ETFs/IIC cotizadas), determinando los importes a introducir en la declaración del IRPF mediante la plataforma Renta Web de la AEAT.

## 2. Base normativa

| Concepto | Referencia |
|---|---|
| Ganancias y pérdidas patrimoniales | Art. 33 Ley 35/2006 IRPF |
| Valor de adquisición y transmisión | Art. 35 Ley 35/2006 IRPF |
| Criterio FIFO para valores homogéneos | Art. 37.2 Ley 35/2006 IRPF |
| Regla antiaplicación — cotizados (2 meses) | Art. 33.5.d Ley 35/2006 IRPF |
| Regla antiaplicación — no cotizados (1 año) | Art. 33.5.e Ley 35/2006 IRPF |
| Transmisiones de IIC (ETFs/fondos) | Art. 94 Ley 35/2006 IRPF |
| Integración en base imponible del ahorro | Art. 49 Ley 35/2006 IRPF |

## 3. Ámbito de aplicación

Esta especificación cubre:

- **ETFs cotizados** en mercados organizados (UCITS, p. ej. iShares, Vanguard, Amundi)
- **Acciones** cotizadas en mercados nacionales e internacionales
- Operativas reportadas en el **formato de exportación XLSX de DeGiro**

No cubre (fuera de alcance v1):

- Fondos de inversión no cotizados (SICAV, fondo tradicional)
- Warrants, opciones y otros derivados
- Dividendos y retenciones en origen
- Acciones no cotizadas

## 4. Formato de entrada — Exportación XLSX de DeGiro

### 4.1 Estructura del fichero

El fichero contiene una hoja (`Transacciones`) con las siguientes columnas en posición fija:

| Pos. | Nombre | Tipo | Notas |
|---|---|---|---|
| 0 | Fecha | String `DD-MM-YYYY` | Fecha de ejecución |
| 1 | Hora | String `HH:MM` | |
| 2 | Producto | String | Nombre del valor |
| 3 | ISIN | String | Identificador del valor |
| 4 | Bolsa de referencia | String | Mercado de referencia |
| 5 | Centro de ejecución | String | Venue de ejecución real |
| 6 | Número | Float | **Positivo = compra, negativo = venta** |
| 7 | Precio | Float | Precio unitario |
| 8 | *(moneda precio)* | String | |
| 9 | Valor local | Float | Importe en moneda local |
| 10 | *(moneda local)* | String | |
| 11 | Valor EUR | Float | Importe en EUR antes de gastos |
| 12 | Tipo de cambio | Float o `None` | `None` para operaciones en EUR |
| 13 | Comisión AutoFX | Float | Comisión por conversión de divisa |
| 14 | Costes de transacción EUR | Float o `None` | Comisiones de DeGiro |
| 15 | **Total EUR** | Float | **Valor definitivo** (incl. todos los gastos) |
| 16 | ID Orden | String (UUID) | Identificador único del pedido |

### 4.2 Convención de signos

- `Número > 0` → compra; `Total EUR < 0` (dinero sale de la cuenta)
- `Número < 0` → venta; `Total EUR > 0` (dinero entra en la cuenta)

### 4.3 Ejecuciones parciales (split)

Una misma orden puede dar lugar a varias filas si se ejecuta en múltiples venues. La clave de agrupación es `(ID Orden, Fecha)`:

- **Mismo día + mismo ID Orden** → se suman las filas en una sola transacción (mismo lote de adquisición)
- **Distinto día + mismo ID Orden** → se mantienen como lotes separados (distinta fecha de adquisición)

**Ejemplo** — compra de 500 acciones de Banco Alfa, ejecutada en dos venues el mismo día:

| Fila | Número | Total EUR | ID Orden |
|---|---|---|---|
| 1 | +300 | −3.000,00 | ORD-2024-0999 |
| 2 | +200 | −1.983,00 | ORD-2024-0999 |
| **Merged** | **+500** | **−4.983,00** | ORD-2024-0999 |

### 4.4 Ejemplo de fichero de muestra

Véase [`docs/referencia/sample_transactions.xlsx`](../referencia/sample_transactions.xlsx) para un fichero ficticio con los 4 escenarios cubiertos por las pruebas.

## 5. Algoritmo FIFO (Art. 37.2 LIRPF)

### 5.1 Descripción

Cuando se transmiten valores homogéneos (mismo ISIN), se considera que se transmiten primero los adquiridos en primer lugar. Para cada ISIN se mantiene una **cola FIFO de lotes de adquisición**.

### 5.2 Valor de adquisición (Art. 35.1 LIRPF)

```
Valor_adquisicion = abs(Total_EUR_compra)
```

DeGiro incluye en `Total EUR` el precio de compra **más** todos los gastos y comisiones inherentes. No se aplica ningún ajuste adicional.

### 5.3 Valor de transmisión (Art. 35.2 LIRPF)

```
Valor_transmision = abs(Total_EUR_venta)
```

DeGiro incluye en `Total EUR` de ventas el precio de venta **menos** comisiones. No se aplica ningún ajuste adicional.

### 5.4 Ganancia o pérdida patrimonial

```
G/P = Valor_transmision - Valor_adquisicion
```

### 5.5 Consumo parcial de lote

Cuando una venta consume solo una fracción de un lote:

```
adquisicion_fraccion = (participaciones_vendidas / participaciones_lote) × coste_total_lote
transmision_fraccion = (participaciones_vendidas / participaciones_totales_venta) × Total_EUR_venta
```

El lote residual mantiene el mismo coste unitario; solo se reduce la cantidad.

### 5.6 Ejemplo completo — FIFO con dos lotes

**Datos:**

| Fecha | Tipo | Participaciones | Total EUR | Lote |
|---|---|---|---|---|
| 10/01/2024 | Compra | 100 | −10.002,00 | A |
| 15/03/2024 | Compra | 50 | −5.252,00 | B |
| 20/06/2024 | Venta | −80 | +8.718,00 | — |

**Cálculo:**

- Coste unitario Lote A = 10.002,00 / 100 = **100,02 €/participación**
- La venta de 80 consume parcialmente el Lote A (80 < 100):
  - Valor adquisición = 80 × 100,02 = **8.001,60 €**
  - Valor transmisión = **8.718,00 €**
  - G/P = 8.718,00 − 8.001,60 = **+716,40 €** (ganancia)
- Lote A residual: 20 participaciones @ 100,02 €
- Lote B: 50 participaciones @ 105,04 € (íntegro, no afectado)

## 6. Regla antiaplicación (Art. 33.5.d LIRPF)

### 6.1 Descripción

Para valores **cotizados en mercados organizados** (acciones y ETFs): si se transmite a pérdida Y se adquieren valores homogéneos (mismo ISIN) en los **2 meses anteriores o posteriores** a la transmisión, la pérdida queda diferida. No se integra en el ejercicio de la venta.

La pérdida diferida **no desaparece**: se suma al coste de adquisición de los valores recomprados y se reconoce cuando estos se vendan.

> Para valores **no cotizados** (Art. 33.5.e), la ventana es **1 año** antes o después.

### 6.2 Implementación

La ventana se calcula como ±61 días naturales desde la fecha de transmisión (aproximación conservadora de "2 meses"; favorece al contribuyente al diferir la pérdida, que es el tratamiento correcto).

**Condición de activación:**
1. El evento genera `capital_gain < 0` (pérdida).
2. Existe una compra del mismo ISIN cuya fecha `d` cumple `|d - fecha_venta| ≤ 61 días`.
3. Esa compra NO es el lote que está siendo vendido (no es la propia adquisición del lote).

### 6.3 Ejemplo completo — Wash sale

**Datos:**

| Fecha | Tipo | Participaciones | Total EUR | Notas |
|---|---|---|---|---|
| 01/03/2024 | Compra | 100 | −10.002,00 | Lote original |
| 10/07/2024 | Venta | −100 | +8.498,00 | Pérdida bruta −1.504 € |
| 20/08/2024 | Compra | 50 | −4.302,00 | Recompra 41 días después → **wash sale** |

**Cálculo:**

- G/P bruta = 8.498,00 − 10.002,00 = **−1.504,00 €** (pérdida)
- Recompra el 20/08/2024: 41 días < 61 días → regla antiaplicación activada
- **Pérdida diferida: 1.504,00 €** → NO declarar como pérdida en 2024
- G/P efectiva en 2024 = **0,00 €**
- La pérdida de 1.504,00 € se imputará al vender el lote de recompra (50 participaciones)

### 6.4 Pérdidas diferidas y ejercicios futuros

Las pérdidas diferidas se registran en el informe pero **no aparecen en ninguna casilla** del ejercicio de la venta. Deben anotarse para declaraciones futuras.

## 7. Informe de salida y casillas IRPF

### 7.1 Cómo introducir los datos en Renta Web

Para cada par adquisición-transmisión (cada `CapitalGainEvent`), navegar en Renta Web a:

> **Apdo. C2 › Ganancias y pérdidas patrimoniales derivadas de transmisiones de otros elementos patrimoniales**
> › Acciones y derechos cotizados *(para acciones individuales)*
> › Transmisiones de IIC cotizadas *(para ETFs/fondos cotizados)*

Introducir por cada operación:

| Campo | Valor |
|---|---|
| Descripción del elemento | Nombre del valor (ISIN) |
| Fecha de adquisición | Fecha de compra del lote |
| Valor de adquisición | `acquisition_value` (gastos ya incluidos) |
| Fecha de transmisión | Fecha de la venta |
| Valor de transmisión | `transfer_value` (gastos ya deducidos) |

Renta Web calcula el resultado automáticamente. No introducir los gastos por separado (ya están incorporados en los valores anteriores).

### 7.2 Casillas de resumen (Modelo IRPF 2023 — verificar cada año)

Tras introducir todas las operaciones, el neto se refleja en:

| Casilla | Nombre | Cuándo |
|---|---|---|
| **0380** | Saldo positivo de G/P patrimoniales — base del ahorro | Si el resultado neto es ganancia |
| **0390** | Saldo negativo de G/P patrimoniales — base del ahorro | Si el resultado neto es pérdida |

> ⚠ Los números de casilla pueden variar entre ejercicios. Verificar en el Modelo 100 oficial del año declarado.

### 7.3 Compensación de pérdidas (Art. 49 LIRPF)

Las pérdidas patrimoniales del ahorro pueden compensarse con:

1. Ganancias patrimoniales del mismo ejercicio (mismo cuadro).
2. Rendimientos del capital mobiliario del ahorro, hasta el **25%** de dichos rendimientos.
3. El saldo negativo restante se compensará en los **4 ejercicios siguientes**.

### 7.4 Tramos del ahorro (IRPF 2023/2024)

| Base liquidable del ahorro | Tipo |
|---|---|
| Hasta 6.000 € | 19% |
| 6.001 € – 50.000 € | 21% |
| 50.001 € – 200.000 € | 23% |
| 200.001 € – 300.000 € | 27% |
| Más de 300.000 € | 28% |

## 8. Casos límite y advertencias

| Situación | Tratamiento |
|---|---|
| Venta con pérdida justo 61 días después de recompra | Dentro de la ventana: pérdida diferida |
| Venta con pérdida + recompra el mismo día | Regla antiaplicación aplica |
| Misma orden ejecutada en 2 días distintos | Lotes separados (fechas de adquisición distintas) |
| Operación en USD | `Total EUR` ya incluye la conversión; no aplicar FX adicional |
| Venta de más participaciones de las compradas | Error `NegativeStockError`; revisar el extracto |
| Pérdida diferida al final del año sin recompra futura detectada | Se reporta como advertencia; no se integra ese año |
| ETF de acumulación vs. distribución | Mismo tratamiento de G/P; los dividendos/repartos se tratan por separado |

## 9. Módulos de implementación

| Módulo | Responsabilidad |
|---|---|
| `renta.etfs.parser` | Parsear XLSX DeGiro y consolidar ejecuciones split |
| `renta.etfs.fifo` | Motor FIFO: consumir lotes y generar `CapitalGainEvent` |
| `renta.etfs.wash_sale` | Detectar y aplicar la regla antiaplicación |
| `renta.etfs.report` | Generar el informe de texto con casillas IRPF |
| `renta.etfs` | Función pública `calculate(path, tax_year) -> str` |
