> **Crawl coverage:** 1/8 pages (12%), 25/60 components interacted with (42%), 9 API endpoints discovered.
>
> Scope: the site's public surface. The crawl does not sign in, so any page or flow behind authentication is absent from this document and is not counted as missing below.

# Accessibility Audit: www.empanad.app

No page was audited. The audit runs in the measurement pass, which re-visits the crawled pages with a realistic browser - if that pass has not run, this document has nothing to report and that is not the same as a clean result.

Automated testing finds on the order of a third of real WCAG problems. Everything here is a genuine violation - axe reports only what it can determine without judgement - but a clean report is not a compliant application. Judgement-dependent criteria (is this label clear, is this order logical to a person) are not automatable and are absent.

1 rule violations across 1 pages.

| Impact | Rule | Criteria | Page | Elements | What fails |
|---|---|---|---|---|---|
| moderate | `target-size` | wcag22aa, wcag258 | empanad.app/o/{token}#state:4e921c8fd3 | 1 | [Pointer target smaller than 24x24 CSS pixels.](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) |

## Failing elements

Resolved to the same CSS paths the graph uses, so each one is a node you can look up rather than a selector to go hunting for. `(document)` means the rule is about the page itself, not an element on it.

**`target-size` on empanad.app/o/{token}#state:4e921c8fd3**
- `body > div#radix-\:r1\: > button`
