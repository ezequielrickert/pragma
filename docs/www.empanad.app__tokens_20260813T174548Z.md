> **Crawl coverage:** 1/8 pages (12%), 25/60 components interacted with (42%), 9 API endpoints discovered.
>
> Scope: the site's public surface. The crawl does not sign in, so any page or flow behind authentication is absent from this document and is not counted as missing below.

# Design Tokens: www.empanad.app

Token names are positional (`text-1` is the most-used text colour), not semantic. The crawl sees that a colour is used, never what it means - naming one `brand-primary` would be a guess presented as a fact. Rename them when you adopt them.

Spacing tokens are absent. They would come from element geometry, which the crawl measures at an 800x600 viewport chosen for speed - a spacing scale derived from that describes a layout nobody sees. Colours and font sizes are computed CSS values and do not have this problem.

## Colour

| Token | Role | Value | Uses | Merged near-identical |
|---|---|---|---|---|
| `text-1` | text | `#392b22` | 24 | - |
| `text-2` | text | `#fbf8f4` | 23 | - |
| `text-3` | text | `#bd3c28` | 8 | - |
| `text-4` | text | `#78685e` | 3 | - |
| `text-5` | text | `#32231b` | 2 | - |
| `surface-1` | surface | `#f9f6f1` | 17 | - |
| `surface-2` | surface | `#358d52` | 5 | - |
| `surface-3` | surface | `#bd3c28` | 2 | - |
| `surface-4` | surface | `#e29d36` | 2 | - |

## Type scale

| Token | Size | Weight | Uses |
|---|---|---|---|
| `type-1` | 16px | 400 | 31 |
| `type-2` | 16px | 600 | 1 |
| `type-3` | 14px | 400 | 8 |
| `type-4` | 14px | 500 | 20 |

## Interaction states

None were read. Either the measurement pass has not run, or the site serves its CSS cross-origin - the browser refuses to expose those rules, and there is no way around it. Absent is not the same as 'this site declares no hover styles'.
