# Especificación: Módulo de Gastos Deducibles (Deducciones Autonómicas CV)

## Objetivo

Leer un fichero Excel con gastos personales del ejercicio, calcular las deducciones autonómicas aplicables a la Comunitat Valenciana (IRPF 2025), y generar un informe con el importe deducible por categoría.

## Base normativa

- Ley 13/1997, de 23 de diciembre (Comunitat Valenciana, tramo autonómico IRPF)
- Manual Práctico IRPF 2025, AEAT — Deducciones autonómicas CV
- Ver detalle en: [docs/referencia/deducciones_autonomicas_cv_2025.md](../referencia/deducciones_autonomicas_cv_2025.md)

---

## Estructura del fichero Excel (`gastos_deducibles_YYYY.xlsx`)

### Hoja `config`

Parámetros del contribuyente necesarios para aplicar límites de renta y porcentajes de edad/discapacidad.

| Campo | Tipo | Descripción |
|---|---|---|
| `base_liquidable_general` | Decimal | Casilla [0500] de la declaración |
| `base_liquidable_ahorro` | Decimal | Casilla [0510] de la declaración |
| `tipo_declaracion` | Texto | `individual` o `conjunta` |
| `edad_contribuyente` | Entero | Edad a 31/12 del ejercicio |
| `grado_discapacidad` | Entero | Porcentaje (0 si no aplica) |
| `tiene_familia_numerosa` | Booleano | `TRUE`/`FALSE` |

### Hoja `gastos`

Un gasto por fila. Las filas con `importe` vacío o cero se ignoran.

| Columna | Tipo | Descripción |
|---|---|---|
| `fecha` | Fecha (YYYY-MM-DD) | Fecha del pago |
| `categoria` | Texto (ver tabla) | Categoría de gasto (determina % y límite) |
| `descripcion` | Texto | Descripción libre del gasto |
| `proveedor` | Texto | Nombre del proveedor |
| `nif_proveedor` | Texto | NIF/CIF del proveedor (obligatorio) |
| `importe` | Decimal | Importe pagado (en euros, sin IVA si profesional exento) |
| `metodo_pago` | Texto | `tarjeta`, `transferencia`, `cheque`, `ingreso` |
| `beneficiario` | Texto | `contribuyente`, `conyuge`, `descendiente` |
| `tiene_factura` | Booleano | `TRUE` si dispone de factura o factura simplificada |
| `tiene_justificante_pago` | Booleano | `TRUE` si dispone de extracto/confirmación de pago |
| `notas` | Texto | Observaciones libres |

#### Valores válidos para `categoria`

| Código | Descripción | % deducción | Límite anual |
|---|---|---|---|
| `deporte_saludable` | Gimnasio, cuotas club, entrenador, fisio, dietista... | 30% (ver edad/discap.) | 150 € |
| `salud_bucodental` | Dentista (no estético) | 30% | 150 € |
| `salud_mental` | Psicólogo clínico, psiquiatra | 30% | 150 € |
| `optica` | Gafas graduadas, lentes de contacto | 30% | 100 € |
| `enfermedad_cronica` | Enfermedades crónicas complejas, raras, Alzheimer | hasta 100 € fijo | 100 € |
| `formacion_musical` | Conservatorio, escuela música inscrita CV, instrumentos | 100% | 150 € |
| `abonos_culturales` | Abonos "Abono Cultural Valenciano" (Culturarts) | 21% | base 165 € |
| `guarderia` | Guardería / 1er ciclo infantil (< 3 años) | 15% | 297 €/menor |
| `material_escolar` | Material escolar (solo si contribuyente en paro) | fijo 110 €/hijo | — |

---

## Algoritmo de cálculo

### 1. Validación de datos de entrada

Para cada fila:
- `nif_proveedor` no puede estar vacío.
- `metodo_pago` debe ser uno de los valores válidos (efectivo **no** es válido).
- Si `tiene_factura = FALSE` o `tiene_justificante_pago = FALSE`: generar advertencia. El gasto se incluye en el cálculo pero se marca como "documentación incompleta".

### 2. Filtro por límite de renta

Calcular `base_total = base_liquidable_general + base_liquidable_ahorro`.

Para cada deducción, determinar si aplica según `tipo_declaracion`:

| Deducción | Límite individual | Límite conjunta | Reducción gradual (individual / conjunta) |
|---|---|---|---|
| Salud, deporte, musical, abonos* | 60.000 € | 78.000 € | 54.000–60.000 € / 72.000–78.000 € |
| Guardería, material escolar | 30.000 € | 47.000 € | 27.000–30.000 € / 44.000–47.000 € |
| Abonos culturales | 50.000 € | — | — |

*Abonos culturales usa su propio límite de 50.000 €.

Fórmula de reducción para el tramo intermedio (usando límites del tipo de deducción):
```
factor = 1 - (base_total - limite_reduccion_inicio) / (limite_maximo - limite_reduccion_inicio)
deduccion_aplicable = deduccion_integra * factor
```

### 3. Porcentaje para deporte según edad/discapacidad

```
if grado_discapacidad >= 65 or edad >= 75:
    pct = Decimal("1.00")   # 100%
elif grado_discapacidad >= 33 or edad >= 65:
    pct = Decimal("0.50")   # 50%
else:
    pct = Decimal("0.30")   # 30%
```

### 4. Cálculo por categoría

Para cada categoría, sumar todos los importes del ejercicio del beneficiario correspondiente y aplicar:

```python
raw = sum(gastos de la categoría)

# aplicar porcentaje
deduccion_bruta = raw * pct_categoria

# aplicar límite de la categoría
deduccion_categoria = min(deduccion_bruta, limite_categoria)

# aplicar factor de reducción por renta
deduccion_final = deduccion_categoria * factor_renta
```

### 5. Casos especiales

- **`enfermedad_cronica`**: la deducción es un importe fijo de hasta 100 € (no porcentaje sobre gasto). Si se justifican gastos, el máximo aplicable es 100 €.
- **`guarderia`**: el límite de 297 € se aplica **por menor**, no por contribuyente. Si hay dos descendientes, el límite es 594 €.
- **`material_escolar`**: solo se calcula si `config.contribuyente_en_paro = TRUE`. Importe fijo de 110 € por hijo elegible.
- **Gastos de salud**: los cuatro subtypes (`salud_bucodental`, `salud_mental`, `optica`, `enfermedad_cronica`) son **acumulables** entre sí.

### 6. Output

Estructura del resultado por deducción:

```python
@dataclass
class DeduccionResult:
    categoria: str
    gasto_total: Decimal          # suma de importes brutos
    deduccion_bruta: Decimal      # antes de aplicar límites
    deduccion_aplicable: Decimal  # después de límites y factor de renta
    factor_renta: Decimal         # 1.0 si no hay reducción
    advertencias: list[str]       # documentación incompleta, etc.
```

---

## Estructura del módulo Python

```
src/renta/gastos/
├── __init__.py
├── categories.py       # enum DeductionCategory + reglas (%, límites)
├── reader.py           # lee el Excel, retorna Config + list[GastoEntry]
├── calculator.py       # aplica el algoritmo y retorna list[DeduccionResult]
├── report.py           # genera informe (Jinja2, igual que dividendos)
└── template.py         # crea el fichero Excel plantilla vacío
```

---

## Plantilla Excel

La plantilla se genera con `python -m renta.gastos.template` y crea:
- `gastos_deducibles_YYYY.xlsx` en el directorio de trabajo.
- Hoja `config` con las celdas de parámetros nombradas y con validación de tipo.
- Hoja `gastos` con cabeceras, formato de fecha, y validaciones en columnas `categoria`, `metodo_pago`, `beneficiario`, `tiene_factura`, `tiene_justificante_pago`.
- Hoja `instrucciones` (solo lectura) con resumen de las deducciones y sus límites.

---

## Tests

Fichero: `tests/gastos/test_calculator.py`

Casos a cubrir:
1. Contribuyente sin reducción por renta (base < 54.000 €): deducción íntegra.
2. Contribuyente en tramo de reducción (base entre 54k–60k): deducción proporcional.
3. Contribuyente sobre el límite (base > 60.000 €): deducción cero.
4. Deporte con ≥65 años: porcentaje 50%.
5. Acumulación de deducciones de salud (bucodental + mental + óptica).
6. Guardería con dos menores: límite 297 € × 2.
7. Gasto con `metodo_pago = efectivo`: advertencia + exclusión del cálculo.
8. Gasto con `tiene_factura = FALSE`: incluido pero con advertencia.
