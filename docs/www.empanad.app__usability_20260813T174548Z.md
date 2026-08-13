> **Crawl coverage:** 1/8 pages (12%), 25/60 components interacted with (42%), 9 API endpoints discovered.
>
> Scope: the site's public surface. The crawl does not sign in, so any page or flow behind authentication is absent from this document and is not counted as missing below.

# Usability Audit: www.empanad.app

6 findings. Each cites the page and element it came from - disagree and go look. Recommendations describe what the rebuild should do, not what the current system does.

Not covered here and waiting on richer capture: loading indicators during a request, and whether a failed submit actually told the user. Both need the DOM observed *during* an interaction, which the crawl does not do.

| Severity | Rule | Heuristic | Where | Finding | Do instead |
|---|---|---|---|---|---|
| medium | `inconsistent-action-naming` | Consistency and standards | GET obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors | One endpoint triggered by controls labelled: 'EmpanadApp', 'Unirte al pedido'. | Name the same action the same way everywhere, or split the endpoint if the actions really differ. |
| medium | `inconsistent-action-naming` | Consistency and standards | GET obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors | One endpoint triggered by controls labelled: 'EmpanadApp', 'Unirte al pedido'. | Name the same action the same way everywhere, or split the endpoint if the actions really differ. |
| medium | `inconsistent-action-naming` | Consistency and standards | GET obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders | One endpoint triggered by controls labelled: 'EmpanadApp', 'Unirte al pedido'. | Name the same action the same way everywhere, or split the endpoint if the actions really differ. |
| medium | `inconsistent-action-naming` | Consistency and standards | GET obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections | One endpoint triggered by controls labelled: 'EmpanadApp', 'Unirte al pedido'. | Name the same action the same way everywhere, or split the endpoint if the actions really differ. |
| medium | `inconsistent-action-naming` | Consistency and standards | GET obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants | One endpoint triggered by controls labelled: 'EmpanadApp', 'Unirte al pedido'. | Name the same action the same way everywhere, or split the endpoint if the actions really differ. |
| medium | `inconsistent-family-styling` | Consistency and standards | button (16 instances) | Same component pattern rendered in 2 background colours: rgb(249, 246, 241), rgb(53, 141, 82). | Pick one token per semantic variant and bind every instance to it; the design-token document lists the colours actually in use. |
