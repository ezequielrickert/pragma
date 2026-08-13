> **Crawl coverage:** 1/8 pages (12%), 25/60 components interacted with (42%), 9 API endpoints discovered.
>
> Scope: the site's public surface. The crawl does not sign in, so any page or flow behind authentication is absent from this document and is not counted as missing below.

# Component Catalogue: www.empanad.app

Grouped by inferred pattern, largest first. `hover`, `focus` and `active` states are absent: the crawl only ever observes components at rest.

## Button

The visible texts suggest multiple distinct functions such as adding items, submitting orders, sharing links, or canceling.

`<button>` · button · 16 instances · atom

| Prop | Type | Varies | Example |
|---|---|---|---|
| `form` | string | yes | body > div#radix-\:r1\: > form |
| `option_labels` | list | yes | Carne picante (selected), Lomo, Carne cortada a cuchillo, Salteña, Tucumana, Jamón, queso y huevo, Matambre a la pizza, Vacío y provoleta, Jamón crudo y rúcula, Cebolla y queso, Napolitana, Humita, Choclo, Espinaca, Acelga y muzzarella, Roquefort, Champignon y queso, Cuatro quesos, Panceta y ciruela, Pollo al verdeo, Pollo al champignon, Queso y albahaca, Caprese, Calabaza, Atún, Bondiola, Cordero, Carne dulce, Hamburguesa con cheddar, Salchicha con cheddar, Cerdo a la barbacoa, Dulce de leche, Manzana, Carne con aceituna, Carne catamarqueña, Lomito y cheddar, Lomo picante, Osobuco, Mondongo, Mollejas al verdeo, Matambrito al verdeo, Cantimpalo y queso, Jamón y roquefort, Jamón, queso y cebolla, Cebolla caramelizada y queso, Provolone, Fugazzeta, Albahaca, Panceta y queso, Choclo y queso, Espinaca y queso, Acelga y salsa blanca, Pollo picante, Pollo y salsa blanca, Pollo a la leña, Pollo y cheddar, Queso y verdeo, Queso y hongos, Hongos, Berenjena ahumada y provoleta, Tomate, albahaca y muzzarella, Pascualina, Brócoli y champignon, Calabaza y choclo, Calabaza y queso, Criolla dulce, Peras y roquefort, Roquefort y cebolla, Roquefort y queso, Roquefort, apio y nuez, Vacío cheddar |

**Variants**

| Modifier classes | Background | Instances | Example |
|---|---|---|---|
| bg-background, border, border-dashed, border-input, h-11, hover:bg-accent, hover:text-accent-foreground, px-4, py-2, w-full | rgb(249, 246, 241) | 4 | Agregar variedad |
| bg-background, border, border-input, h-10, hover:bg-accent, hover:text-accent-foreground, mb-3, px-4, py-2, w-full | rgb(249, 246, 241) | 3 | Agregar pedido de alguien más |
| bg-background, border, border-input, h-11, hover:bg-accent, hover:text-accent-foreground, shrink-0, w-11 | rgb(249, 246, 241) | 3 | Copiar link |
| bg-success, flex-1, h-11, hover:bg-success/90, px-4, py-2, shadow-lg, text-success-foreground | rgb(53, 141, 82) | 3 | Invitar por WhatsApp |
| bg-success, h-10, hover:bg-success/90, mt-3, px-4, py-2, text-success-foreground, w-full | rgb(53, 141, 82) | 2 | Finalizar mi pedido |
| bg-background, border, border-input, flex-1, h-11, hover:bg-accent, hover:text-accent-foreground, px-4, py-2 | rgb(249, 246, 241) | 1 | Cancelar |

Used on: empanad.app/o/{token}, empanad.app/o/{token}#state:4e921c8fd3, empanad.app/o/{token}#state:7c270e58a2

## Button2

Adjusts a numeric quantity by performing addition or subtraction.

`<button>` · button · 16 instances · atom

| Prop | Type | Varies | Example |
|---|---|---|---|
| `option_labels` | list | yes | stepper |

Used on: empanad.app/o/{token}, empanad.app/o/{token}#state:4e921c8fd3

## Button3

Initiates an action to add a new item or record.

`<button>` · button · 8 instances · atom

Used on: empanad.app/o/{token}, empanad.app/o/{token}#state:7c270e58a2

## Button4

Displays detailed information about a specific person.

`<button>` · button · 3 instances · atom

Used on: empanad.app/o/{token}, empanad.app/o/{token}#state:4e921c8fd3, empanad.app/o/{token}#state:7c270e58a2

## Link

Navigates the user to another page or location within the application.

`<a>` · link · 3 instances · atom

| Prop | Type | Varies | Example |
|---|---|---|---|
| `href` | string | no (same on every instance) | / |

Used on: empanad.app/o/{token}, empanad.app/o/{token}#state:4e921c8fd3, empanad.app/o/{token}#state:7c270e58a2

## TextFieldNumber

`<input>` · text field (number) · 3 instances · atom

| Prop | Type | Varies | Example |
|---|---|---|---|
| `label` | string | no (same on every instance) | Total del pedido |
| `placeholder` | string | no (same on every instance) | ej: 12000 |

Used on: empanad.app/o/{token}, empanad.app/o/{token}#state:4e921c8fd3, empanad.app/o/{token}#state:7c270e58a2

## Combobox

`<input>` · combobox (searchable dropdown) · 2 instances · atom

| Prop | Type | Varies | Example |
|---|---|---|---|
| `placeholder` | string | yes | Buscar empanadería… |

**Variants**

| Modifier classes | Background | Instances | Example |
|---|---|---|---|
| text-base | rgba(0, 0, 0, 0) | 1 |  |
| text-sm | rgba(0, 0, 0, 0) | 1 |  |

Used on: empanad.app/o/{token}

## ListMenuOption

Selecting or choosing an option from a predefined list.

`<div>` · list/menu option · 2 instances

| Prop | Type | Varies | Example |
|---|---|---|---|
| `option_labels` | list | yes | Mi Gusto (selected), Solo Empanadas, 1810 Cocina Regional, La Continental, El Noble, El Hornero, Morita, La Leñita, El Sanjuanino, La Morada, La Cocina, El Gauchito, Cumaná, La Paceña, Las Cabras, El Santa Evita, Roma del Abasto, Empanadas Tremendas, El Cuartito, Maná Empanadas, Tercera Docena, Otra / No sé |

**Variants**

| Modifier classes | Background | Instances | Example |
|---|---|---|---|
| py-1.5 | rgb(226, 157, 54) | 1 | Mi Gusto |
| py-3 | rgb(226, 157, 54) | 1 | Carne picante |

Used on: empanad.app/o/{token}

## SubmitButton

Confirms or submits an action.

`<button>` · submit button · 2 instances · atom (in a form)

| Prop | Type | Varies | Example |
|---|---|---|---|
| `form` | string | yes | body > div#root > main > div > div:nth-of-type(3) > form |

**Variants**

| Modifier classes | Background | Instances | Example |
|---|---|---|---|
| flex-1, font-medium, h-11, px-4, py-2, text-sm | rgb(189, 60, 40) | 1 | Crear |
| font-semibold, h-12, mt-5, px-8, text-base, w-full | rgb(189, 60, 40) | 1 | Unirte al pedido |

Used on: empanad.app/o/{token}, empanad.app/o/{token}#state:4e921c8fd3

## TextFieldText

`<input>` · text field (text) · 2 instances · atom (in a form)

| Prop | Type | Varies | Example |
|---|---|---|---|
| `label` | string | yes | ¿Cómo te llamás? |
| `placeholder` | string | yes | Tu nombre |
| `form` | string | yes | body > div#root > main > div > div:nth-of-type(3) > form |

Used on: empanad.app/o/{token}, empanad.app/o/{token}#state:4e921c8fd3
