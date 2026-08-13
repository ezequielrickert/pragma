> **Crawl coverage:** 1/8 pages (12%), 25/60 components interacted with (42%), 9 API endpoints discovered.
>
> Scope: the site's public surface. The crawl does not sign in, so any page or flow behind authentication is absent from this document and is not counted as missing below.

# Sequence Diagrams: www.empanad.app

The same traces the behaviour specification renders as scenarios, drawn. Not a second source of truth - a trace already *is* a sequence, so these cannot disagree with it.

## click Copiar link on empanad.app/o/msUc9nBw6jBAfSUQPW-8y-dNEMtdMsD5

```mermaid
sequenceDiagram
    actor User
    participant UI
    participant API
    User->>UI: click Copiar link
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Invitar por WhatsApp
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Agregar
    UI->>API: POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 201
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Agregar
    UI->>API: POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 201
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Agregar
    UI->>API: POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 201
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Agregar
    UI->>API: POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 201
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Agregar variedad
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Detalle por persona
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Agregar pedido de alguien más
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click EmpanadApp
    UI->>API: POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders
    API-->>UI: 201
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: no response captured
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants
    API-->>UI: no response captured
    UI-->>User: empanad.app/o/msUc9nBw6jBAfSUQPW-8y-dNEM
```

## click Restar on empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWSw5xxNx

```mermaid
sequenceDiagram
    actor User
    participant UI
    participant API
    User->>UI: click Restar
    UI->>API: DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 204
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Sumar
    User->>UI: click Restar
    UI->>API: DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 204
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Sumar
    User->>UI: click Restar
    UI->>API: DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 204
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Sumar
    User->>UI: click Restar
    UI->>API: DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 204
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Sumar
    User->>UI: fill text field (number)
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
```

## fill text field (text) on empanad.app/o/twT7V1HfIhAria0JIz1kzC9kezoVNzU-

```mermaid
sequenceDiagram
    actor User
    participant UI
    participant API
    User->>UI: fill text field (text)
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Otra / No sé
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click Unirte al pedido
    UI->>API: POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants
    API-->>UI: 201
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants
    API-->>UI: 200
    UI-->>User: empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWS
    User->>UI: click EmpanadApp
    UI->>API: POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders
    API-->>UI: 201
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants
    API-->>UI: 200
    UI-->>User: empanad.app/o/twT7V1HfIhAria0JIz1kzC9kez
```

## click EmpanadApp on empanad.app/o/naLAQ0Uysf0SjgW0JSeZj5ne0meo96rV

```mermaid
sequenceDiagram
    actor User
    participant UI
    participant API
    User->>UI: click EmpanadApp
    UI->>API: POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders
    API-->>UI: 201
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    API-->>UI: 200
    UI->>API: GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants
    API-->>UI: 200
    UI-->>User: empanad.app/o/naLAQ0Uysf0SjgW0JSeZj5ne0m
```
