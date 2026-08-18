> **Crawl coverage:** 0/85 pages (0%), 0/4677 components interacted with (0%), 1 API endpoints discovered.
>
> **This run stopped early:** page budget reached (21/20 pages). The pages it did not reach are still recorded as pending - run the same URL again to continue from there.
>
> Scope: the site's public surface. The crawl does not sign in, so any page or flow behind authentication is absent from this document and is not counted as missing below.

# Usability Audit: www.stjohns.edu.ar

3 findings. Each cites the page and element it came from - disagree and go look. Recommendations describe what the rebuild should do, not what the current system does.

Not covered here and waiting on richer capture: loading indicators during a request, and whether a failed submit actually told the user. Both need the DOM observed *during* an interaction, which the crawl does not do.

| Severity | Rule | Heuristic | Where | Finding | Do instead |
|---|---|---|---|---|---|
| medium | `missing-semantic-input-type` | Error prevention | stjohns.edu.ar/Web/Admision/Entrevista — body > form#WPForm > main > section > div > div > div:nth-of-type(2) > div#v-pills-tabContent > div#postulante > div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(3) > div > input#ctl05_ucDatosPostulante1_txtFechaNacimiento | Field named/labelled for date but declared as plain text. | Declare `type="date"` in the rebuild so the browser validates it and mobile shows the right keyboard. |
| medium | `missing-semantic-input-type` | Error prevention | stjohns.edu.ar/Web/Admissions/Interview — body > form#WPForm > main > section > div > div > div:nth-of-type(2) > div#v-pills-tabContent > div#postulante > div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(3) > div > input#ctl05_ucDatosPostulante1_txtFechaNacimiento | Field named/labelled for date but declared as plain text. | Declare `type="date"` in the rebuild so the browser validates it and mobile shows the right keyboard. |
| medium | `missing-semantic-input-type` | Error prevention | stjohns.edu.ar/Web/admision/entrevista — body > form#WPForm > main > section > div > div > div:nth-of-type(2) > div#v-pills-tabContent > div#postulante > div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(3) > div > input#ctl05_ucDatosPostulante1_txtFechaNacimiento | Field named/labelled for date but declared as plain text. | Declare `type="date"` in the rebuild so the browser validates it and mobile shows the right keyboard. |
