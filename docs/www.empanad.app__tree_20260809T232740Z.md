# Component Tree: www.empanad.app

Generated: 2026-08-09T23:29:09.618224+00:00

4 pages, 150 components, 35 text blocks

```
www.empanad.app/
├── empanad.app (empanad.app)
├── EmpanadApp · Pedidos de empanadas en grupo (empanad.app/o/{token})
│   ├── [link] "EmpanadApp" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=* -> 201; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=*&share_token=eq.0sCNzYLPme-wTYaXiWOQLoe5vto2KMrt -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors?select=*&is_active=eq.true&order=sort_order.asc -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors?select=*&order_id=eq.99be9c81-cd9f-44c4-9ab3-226732bd3d18 -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=*&order_id=eq.99be9c81-cd9f-44c4-9ab3-226732bd3d18 -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants?select=*&order_id=eq.99be9c81-cd9f-44c4-9ab3-226732bd3d18 -> 200] -> "empanad.app/o/0sCNzYLPme-wTYaXiWOQLoe5vto2KMrt" (empanad.app/o/0sCNzYLPme-wTYaXiWOQLoe5vto2KMrt)
│   ├── [button] "Copiar link" -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Invitar por WhatsApp" -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [submit button] "Crear pedido" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants?select=* -> 201; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=*&share_token=eq.0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors?select=*&is_active=eq.true&order=sort_order.asc -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors?select=*&order_id=eq.884c8197-29c1-41ca-a48a-2343b09f5d98 -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=*&order_id=eq.884c8197-29c1-41ca-a48a-2343b09f5d98 -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants?select=*&order_id=eq.884c8197-29c1-41ca-a48a-2343b09f5d98 -> 200] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [combobox (searchable dropdown)] "Otra / No sé" variants=[Mi Gusto (selected), Solo Empanadas, 1810 Cocina Regional, La Continental, El Noble, El Hornero, Morita, La Leñita, El Sanjuanino, La Morada, La Cocina, El Gauchito, Cumaná, La Paceña, Las Cabras, El Santa Evita, Roma del Abasto, Empanadas Tremendas, El Cuartito, Maná Empanadas, Tercera Docena, Otra / No sé] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [text field (text)] placeholder='Juanito' -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Agregar variedad" variants=[Carne picante (selected), Lomo, Carne cortada a cuchillo, Salteña, Tucumana, Jamón, queso y huevo, Matambre a la pizza, Vacío y provoleta, Jamón crudo y rúcula, Cebolla y queso, Napolitana, Humita, Choclo, Espinaca, Acelga y muzzarella, Roquefort, Champignon y queso, Cuatro quesos, Panceta y ciruela, Pollo al verdeo, Pollo al champignon, Queso y albahaca, Caprese, Calabaza, Atún, Bondiola, Cordero, Carne dulce, Hamburguesa con cheddar, Salchicha con cheddar, Cerdo a la barbacoa, Dulce de leche, Manzana, Carne con aceituna, Carne catamarqueña, Lomito y cheddar, Lomo picante, Osobuco, Mondongo, Mollejas al verdeo, Matambrito al verdeo, Cantimpalo y queso, Jamón y roquefort, Jamón, queso y cebolla, Cebolla caramelizada y queso, Provolone, Fugazzeta, Albahaca, Panceta y queso, Choclo y queso, Espinaca y queso, Acelga y salsa blanca, Pollo picante, Pollo y salsa blanca, Pollo a la leña, Pollo y cheddar, Queso y verdeo, Queso y hongos, Hongos, Berenjena ahumada y provoleta, Tomate, albahaca y muzzarella, Pascualina, Brócoli y champignon, Calabaza y choclo, Calabaza y queso, Criolla dulce, Peras y roquefort, Roquefort y cebolla, Roquefort y queso, Roquefort, apio y nuez, Vacío cheddar] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Agregar variedad"
│   ├── [button] "Finalizar mi pedido"
│   ├── [button] "Agregar" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=* -> 201] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Restar" requests=[DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?id=eq.0c703a78-6587-4d62-97f6-6dca86176159 -> 204] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Agregar" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=* -> 201] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Restar" requests=[DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?id=eq.bd670303-5796-402b-a46a-3a000e49441c -> 204] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Agregar" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=* -> 201] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Restar" requests=[DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?id=eq.a21156af-e14b-4c2a-a380-fbaf178b03bc -> 204] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Agregar" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=* -> 201] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Restar" requests=[DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?id=eq.b45e0fcb-f883-4a28-bd94-e961cbd7b875 -> 204] -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Sumar" variants=[stepper]
│   ├── [button] "Detalle por persona" -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [button] "Agregar pedido de alguien más" -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
│   ├── [text field (number)] placeholder='12000' -> "empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug" (empanad.app/o/0t_ix9kmLZS925UwsCWP5mbSK5bSa3Ug)
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
│   ├── [text: h2] Pedido de  Juanito
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
│   ├── [link] "EmpanadApp" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=* -> 201; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=*&share_token=eq.iVeQN-Vvz7EkuH9OIZyQc7QDtjc2QxzF -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors?select=*&is_active=eq.true&order=sort_order.asc -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors?select=*&order_id=eq.ae73280d-5145-404d-a78e-7c74930c14db -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=*&order_id=eq.ae73280d-5145-404d-a78e-7c74930c14db -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants?select=*&order_id=eq.ae73280d-5145-404d-a78e-7c74930c14db -> 200] -> "empanad.app/o/iVeQN-Vvz7EkuH9OIZyQc7QDtjc2QxzF" (empanad.app/o/iVeQN-Vvz7EkuH9OIZyQc7QDtjc2QxzF)
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
│   ├── [text: h2] Pedido de  Juanito
│   ├── [text: p] 4 empanadas elegidas
│   ├── [text: h2] Pedido del grupo
│   ├── [text: p] de   confirmados · vas a ver el pedido completo cuando finalicen todos
│   ├── [text: p] Esperando que alguien finalice su pedido.
│   ├── [text: h2] Cuenta
│   ├── [text: p] Cargá el total y partimos la cuenta entre los que pidieron
│   └── [text: p] Lo que pagaste en total. Se divide proporcional a cuántas pidió cada uno.
└── EmpanadApp · Pedidos de empanadas en grupo (empanad.app/o/{token}#state:7c270e58a2)
    ├── [link] "EmpanadApp" requests=[POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=* -> 201; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders?select=*&share_token=eq.KyZ6b1edM_Vs50MOWdKVTzabts8mI91h -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors?select=*&is_active=eq.true&order=sort_order.asc -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors?select=*&order_id=eq.e6991d8c-3b36-45d2-b5b4-384eec3a901d -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections?select=*&order_id=eq.e6991d8c-3b36-45d2-b5b4-384eec3a901d -> 200; GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants?select=*&order_id=eq.e6991d8c-3b36-45d2-b5b4-384eec3a901d -> 200] -> "empanad.app/o/KyZ6b1edM_Vs50MOWdKVTzabts8mI91h" (empanad.app/o/KyZ6b1edM_Vs50MOWdKVTzabts8mI91h)
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
    ├── [text: h2] Pedido de  Juanito
    ├── [text: p] Tocá + para sumar al pedido
    ├── [text: h2] Pedido del grupo
    ├── [text: p] de   confirmados · vas a ver el pedido completo cuando finalicen todos
    ├── [text: p] Esperando que alguien finalice su pedido.
    ├── [text: p] esperando que confirme su pedido
    ├── [text: h2] Cuenta
    ├── [text: p] Cargá el total y partimos la cuenta entre los que pidieron
    └── [text: p] Lo que pagaste en total. Se divide proporcional a cuántas pidió cada uno.
```
