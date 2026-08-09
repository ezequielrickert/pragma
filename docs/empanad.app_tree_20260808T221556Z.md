# Component Tree: empanad.app

Generated: 2026-08-08T22:15:56.383519+00:00

4 pages, 151 components, 35 text blocks

```
empanad.app/
├── empanad.app (empanad.app)
├── EmpanadApp · Pedidos de empanadas en grupo (empanad.app/o/{token})
│   ├── [button]
│   ├── [link] "EmpanadApp" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=* -> 201; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=*&share_token=eq.WoQfDAc53jinXuGkfrf0ppB6RCSAzlXT -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors?select=*&is_active=eq.true&order=sort_order.asc -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors?select=*&order_id=eq.2e743038-0769-4194-b7d8-690ab2118a6e -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=*&order_id=eq.2e743038-0769-4194-b7d8-690ab2118a6e -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants?select=*&order_id=eq.2e743038-0769-4194-b7d8-690ab2118a6e -> 200] -> "empanad.app/o/WoQfDAc53jinXuGkfrf0ppB6RCSAzlXT" (empanad.app/o/WoQfDAc53jinXuGkfrf0ppB6RCSAzlXT)
│   ├── [button] "Copiar link" -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Invitar por WhatsApp" -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [submit button] "Crear pedido" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants?select=* -> 201; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=*&share_token=eq.aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors?select=*&is_active=eq.true&order=sort_order.asc -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors?select=*&order_id=eq.bd62e947-e39e-491b-a507-b0b7c4a7cd86 -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=*&order_id=eq.bd62e947-e39e-491b-a507-b0b7c4a7cd86 -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants?select=*&order_id=eq.bd62e947-e39e-491b-a507-b0b7c4a7cd86 -> 200] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [combobox (searchable dropdown)] "Otra / No sé" variants=[Mi Gusto (selected), Solo Empanadas, 1810 Cocina Regional, La Continental, El Noble, El Hornero, Morita, La Leñita, El Sanjuanino, La Morada, La Cocina, El Gauchito, Cumaná, La Paceña, Las Cabras, El Santa Evita, Roma del Abasto, Empanadas Tremendas, El Cuartito, Maná Empanadas, Tercera Docena, Otra / No sé] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [text field (text)] placeholder='Juan' -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Agregar variedad" variants=[Carne picante (selected), Lomo, Carne cortada a cuchillo, Salteña, Tucumana, Jamón, queso y huevo, Matambre a la pizza, Vacío y provoleta, Jamón crudo y rúcula, Cebolla y queso, Napolitana, Humita, Choclo, Espinaca, Acelga y muzzarella, Roquefort, Champignon y queso, Cuatro quesos, Panceta y ciruela, Pollo al verdeo, Pollo al champignon, Queso y albahaca, Caprese, Calabaza, Atún, Bondiola, Cordero, Carne dulce, Hamburguesa con cheddar, Salchicha con cheddar, Cerdo a la barbacoa, Dulce de leche, Manzana, Carne con aceituna, Carne catamarqueña, Lomito y cheddar, Lomo picante, Osobuco, Mondongo, Mollejas al verdeo, Matambrito al verdeo, Cantimpalo y queso, Jamón y roquefort, Jamón, queso y cebolla, Cebolla caramelizada y queso, Provolone, Fugazzeta, Albahaca, Panceta y queso, Choclo y queso, Espinaca y queso, Acelga y salsa blanca, Pollo picante, Pollo y salsa blanca, Pollo a la leña, Pollo y cheddar, Queso y verdeo, Queso y hongos, Hongos, Berenjena ahumada y provoleta, Tomate, albahaca y muzzarella, Pascualina, Brócoli y champignon, Calabaza y choclo, Calabaza y queso, Criolla dulce, Peras y roquefort, Roquefort y cebolla, Roquefort y queso, Roquefort, apio y nuez, Vacío cheddar] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Agregar variedad"
│   ├── [button] "Finalizar mi pedido"
│   ├── [button] "Agregar" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=* -> 201] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Restar" requests=[DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?id=eq.558439c0-e902-4e45-916c-da8dee6ff2ec -> 204] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Agregar" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=* -> 201] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Restar" requests=[DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?id=eq.3080be83-258d-40af-a2d6-7c3a42a171ab -> 204] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Agregar" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=* -> 201] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Restar" requests=[DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?id=eq.3fab9b3e-a912-47d8-8e91-932f0bf1b4e2 -> 204] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Agregar" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=* -> 201] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Restar" requests=[DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?id=eq.36731d11-f740-4512-a808-a24381137e26 -> 204] -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Detalle por persona" -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [button] "Agregar pedido de alguien más" -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [text field (number)] placeholder='5000' -> "empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe" (empanad.app/o/aOdqtdQkUUYOtYRSM3TUS55SULOuGKOe)
│   ├── [list/menu option] "Mi Gusto"
│   ├── [list/menu option] "Solo Empanadas"
│   ├── [list/menu option] "1810 Cocina Regional"
│   ├── [list/menu option] "La Continental"
│   ├── [list/menu option] "El Noble"
│   ├── [list/menu option] "El Hornero"
│   ├── [list/menu option] "Morita"
│   ├── [list/menu option] "La Leñita"
│   ├── [list/menu option] "El Sanjuanino"
│   ├── [list/menu option] "La Morada"
│   ├── [list/menu option] "La Cocina"
│   ├── [list/menu option] "El Gauchito"
│   ├── [list/menu option] "Cumaná"
│   ├── [list/menu option] "La Paceña"
│   ├── [list/menu option] "Las Cabras"
│   ├── [list/menu option] "El Santa Evita"
│   ├── [list/menu option] "Roma del Abasto"
│   ├── [list/menu option] "Empanadas Tremendas"
│   ├── [list/menu option] "El Cuartito"
│   ├── [list/menu option] "Maná Empanadas"
│   ├── [list/menu option] "Tercera Docena"
│   ├── [list/menu option] "Otra / No sé"
│   ├── [list/menu option] "Calabaza"
│   ├── [list/menu option] "Atún"
│   ├── [list/menu option] "Bondiola"
│   ├── [list/menu option] "Cordero"
│   ├── [list/menu option] "Carne dulce"
│   ├── [list/menu option] "Hamburguesa con cheddar"
│   ├── [list/menu option] "Salchicha con cheddar"
│   ├── [list/menu option] "Cerdo a la barbacoa"
│   ├── [list/menu option] "Dulce de leche"
│   ├── [list/menu option] "Manzana"
│   ├── [list/menu option] "Carne con aceituna"
│   ├── [list/menu option] "Carne catamarqueña"
│   ├── [list/menu option] "Lomito y cheddar"
│   ├── [list/menu option] "Lomo picante"
│   ├── [list/menu option] "Osobuco"
│   ├── [list/menu option] "Mondongo"
│   ├── [list/menu option] "Mollejas al verdeo"
│   ├── [list/menu option] "Matambrito al verdeo"
│   ├── [list/menu option] "Cantimpalo y queso"
│   ├── [list/menu option] "Jamón y roquefort"
│   ├── [list/menu option] "Jamón, queso y cebolla"
│   ├── [list/menu option] "Cebolla caramelizada y queso"
│   ├── [list/menu option] "Provolone"
│   ├── [list/menu option] "Fugazzeta"
│   ├── [list/menu option] "Albahaca"
│   ├── [list/menu option] "Panceta y queso"
│   ├── [list/menu option] "Choclo y queso"
│   ├── [list/menu option] "Espinaca y queso"
│   ├── [list/menu option] "Acelga y salsa blanca"
│   ├── [list/menu option] "Pollo picante"
│   ├── [list/menu option] "Pollo y salsa blanca"
│   ├── [list/menu option] "Pollo a la leña"
│   ├── [list/menu option] "Pollo y cheddar"
│   ├── [list/menu option] "Queso y verdeo"
│   ├── [list/menu option] "Queso y hongos"
│   ├── [list/menu option] "Hongos"
│   ├── [list/menu option] "Berenjena ahumada y provoleta"
│   ├── [list/menu option] "Tomate, albahaca y muzzarella"
│   ├── [list/menu option] "Pascualina"
│   ├── [list/menu option] "Brócoli y champignon"
│   ├── [list/menu option] "Calabaza y choclo"
│   ├── [list/menu option] "Calabaza y queso"
│   ├── [list/menu option] "Criolla dulce"
│   ├── [list/menu option] "Peras y roquefort"
│   ├── [list/menu option] "Roquefort y cebolla"
│   ├── [list/menu option] "Roquefort y queso"
│   ├── [list/menu option] "Roquefort, apio y nuez"
│   ├── [list/menu option] "Vacío cheddar"
│   ├── [list/menu option] "Carne picante"
│   ├── [list/menu option] "Lomo"
│   ├── [list/menu option] "Carne cortada a cuchillo"
│   ├── [list/menu option] "Salteña"
│   ├── [list/menu option] "Tucumana"
│   ├── [list/menu option] "Jamón, queso y huevo"
│   ├── [list/menu option] "Matambre a la pizza"
│   ├── [list/menu option] "Vacío y provoleta"
│   ├── [list/menu option] "Jamón crudo y rúcula"
│   ├── [list/menu option] "Cebolla y queso"
│   ├── [list/menu option] "Napolitana"
│   ├── [list/menu option] "Humita"
│   ├── [list/menu option] "Choclo"
│   ├── [list/menu option] "Espinaca"
│   ├── [list/menu option] "Acelga y muzzarella"
│   ├── [list/menu option] "Roquefort"
│   ├── [list/menu option] "Champignon y queso"
│   ├── [list/menu option] "Cuatro quesos"
│   ├── [list/menu option] "Panceta y ciruela"
│   ├── [list/menu option] "Pollo al verdeo"
│   ├── [list/menu option] "Pollo al champignon"
│   ├── [list/menu option] "Queso y albahaca"
│   ├── [list/menu option] "Caprese"
│   ├── [combobox (searchable dropdown)]
│   ├── [combobox (searchable dropdown)]
│   ├── [text: p] Pedí empanadas con amigos sin vueltas
│   ├── [text: h2] ¿Cómo funciona?
│   ├── [text: p] Acá vas a encontrar todos los sabores que hay en la app. Revisá que el sabor que elegís esté en la carta real para no pedir algo que no haya.
│   ├── [text: h2] Pedido de  Juan
│   ├── [text: p] 4 empanadas elegidas
│   ├── [text: h2] Pedido del grupo
│   ├── [text: p] de   confirmados · vas a ver el pedido completo cuando finalicen todos
│   ├── [text: p] Esperando que alguien finalice su pedido.
│   ├── [text: p] esperando que confirme su pedido
│   ├── [text: h2] Cuenta
│   ├── [text: p] Cargá el total y partimos la cuenta entre los que pidieron
│   └── [text: p] Lo que pagaste en total. Se divide proporcional a cuántas pidió cada uno.
├── EmpanadApp · Pedidos de empanadas en grupo (empanad.app/o/{token}#state:4e921c8fd3)
│   ├── [button] "Close"
│   ├── [button] "Cancelar"
│   ├── [submit button] "Crear"
│   ├── [text field (text)]
│   ├── [link] "EmpanadApp" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=* -> 201; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=*&share_token=eq.HqpO1kQEECXJ3ZGUL2s9EanguO2LySYh -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors?select=*&is_active=eq.true&order=sort_order.asc -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors?select=*&order_id=eq.b821856c-535f-4c2b-b498-836ffa1130ad -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=*&order_id=eq.b821856c-535f-4c2b-b498-836ffa1130ad -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants?select=*&order_id=eq.b821856c-535f-4c2b-b498-836ffa1130ad -> 200] -> "empanad.app/o/HqpO1kQEECXJ3ZGUL2s9EanguO2LySYh" (empanad.app/o/HqpO1kQEECXJ3ZGUL2s9EanguO2LySYh)
│   ├── [button] "Copiar link"
│   ├── [button] "Invitar por WhatsApp"
│   ├── [button] "Agregar variedad"
│   ├── [button] "Finalizar mi pedido"
│   ├── [button] "Restar"
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Restar"
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Restar"
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Restar"
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Detalle por persona"
│   ├── [button] "Agregar pedido de alguien más"
│   ├── [text field (number)]
│   ├── [text: h2] Agregar pedido de alguien más
│   ├── [text: p] ¿A nombre de quién vas a cargar las empanadas?
│   ├── [text: p] Pedí empanadas con amigos sin vueltas
│   ├── [text: p] Acá vas a encontrar todos los sabores que hay en la app. Revisá que el sabor que elegís esté en la carta real para no pedir algo que no haya.
│   ├── [text: h2] Pedido de  Juan
│   ├── [text: p] 4 empanadas elegidas
│   ├── [text: h2] Pedido del grupo
│   ├── [text: p] de   confirmados · vas a ver el pedido completo cuando finalicen todos
│   ├── [text: p] Esperando que alguien finalice su pedido.
│   ├── [text: h2] Cuenta
│   ├── [text: p] Cargá el total y partimos la cuenta entre los que pidieron
│   └── [text: p] Lo que pagaste en total. Se divide proporcional a cuántas pidió cada uno.
└── EmpanadApp · Pedidos de empanadas en grupo (empanad.app/o/{token}#state:7c270e58a2)
    ├── [link] "EmpanadApp" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=* -> 201; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=*&share_token=eq.d-tJDGgTIa_50o356FcIIDZD93XiDTlq -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors?select=*&is_active=eq.true&order=sort_order.asc -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors?select=*&order_id=eq.df9b4332-0129-4d66-948d-a6d8b8064ea7 -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=*&order_id=eq.df9b4332-0129-4d66-948d-a6d8b8064ea7 -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants?select=*&order_id=eq.df9b4332-0129-4d66-948d-a6d8b8064ea7 -> 200] -> "empanad.app/o/d-tJDGgTIa_50o356FcIIDZD93XiDTlq" (empanad.app/o/d-tJDGgTIa_50o356FcIIDZD93XiDTlq)
    ├── [button] "Copiar link"
    ├── [button] "Invitar por WhatsApp"
    ├── [button] "Agregar variedad"
    ├── [button] "Agregar"
    ├── [button] "Agregar"
    ├── [button] "Agregar"
    ├── [button] "Agregar"
    ├── [button] "Detalle por persona"
    ├── [button] "Agregar pedido de alguien más"
    ├── [text field (number)]
    ├── [text: p] Pedí empanadas con amigos sin vueltas
    ├── [text: p] Acá vas a encontrar todos los sabores que hay en la app. Revisá que el sabor que elegís esté en la carta real para no pedir algo que no haya.
    ├── [text: h2] Pedido de  Juan
    ├── [text: p] Tocá + para sumar al pedido
    ├── [text: h2] Pedido del grupo
    ├── [text: p] de   confirmados · vas a ver el pedido completo cuando finalicen todos
    ├── [text: p] Esperando que alguien finalice su pedido.
    ├── [text: p] esperando que confirme su pedido
    ├── [text: h2] Cuenta
    ├── [text: p] Cargá el total y partimos la cuenta entre los que pidieron
    └── [text: p] Lo que pagaste en total. Se divide proporcional a cuántas pidió cada uno.
```
