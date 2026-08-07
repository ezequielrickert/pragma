"""
Playwright-based stateful scraper for Pragma with high-fidelity discovery.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright, ElementHandle

from ..core.interfaces import PageState, Scraper
from ..core.registry import SCRAPER_REGISTRY


@SCRAPER_REGISTRY.register("playwright")
class PlaywrightScraper(Scraper):
    """A high-fidelity scraper that maintains a browser session."""

    def __init__(self, headless: bool = True, wait_seconds: float = 15.0) -> None:
        """Initialize scraper settings.

        Args:
            headless: Run the browser without a visible UI.
            wait_seconds: Extra time to let the page settle after navigation
                before reading links/components - JS-heavy nav (mega menus,
                client-rendered content) can otherwise still be missing from
                the DOM at extraction time. Raise this for slow/JS-heavy sites.
        """
        self.headless = headless
        self.wait_seconds = wait_seconds
        self._playwright = None
        self._browser = None
        self._page = None

    def _ensure_browser(self) -> None:
        """Lazily start playwright and browser."""
        if not self._playwright:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._page = self._browser.new_page()

    def navigate(self, url: str) -> PageState:
        """Navigate to a URL and capture deep state."""
        self._ensure_browser()
        self._page.goto(url, wait_until="networkidle")
        time.sleep(self.wait_seconds)
        return self.get_state()

    def _resolve_frame(self, frame_url: Optional[str]):
        """Resolve `frame_url` (a `PageState.components[i]["frame_url"]` value from a
        previous discovery pass) to a live Playwright Frame, or the main page if
        `frame_url` is empty/None - the default, unchanged behavior for every
        caller that never deals with iframes.

        Raises a clear error if the frame is no longer present (e.g. the
        iframe was removed or re-rendered with a different src since it was
        last discovered) rather than silently falling back to the main frame,
        which would make the click land on the wrong document with no
        indication why.
        """
        if not frame_url:
            return self._page
        frame = self._page.frame(url=frame_url)
        if frame is None:
            raise ValueError(f"Frame not found: {frame_url!r} (page may have navigated or the iframe changed)")
        return frame

    def click(self, selector: str, frame_url: Optional[str] = None) -> PageState:
        """Click an element and capture new deep state.

        A click failure (bad/ambiguous selector, element not clickable, etc.)
        propagates so the caller can tell the click didn't happen - swallowing
        it here used to make every failed click look like a successful no-op,
        which was indistinguishable from a click that legitimately changed
        nothing. Only the post-click networkidle wait is treated as best-effort,
        since pages with persistent polling/analytics often never go idle.

        A normal click that times out specifically because the element isn't
        visible (common for dropdown/submenu items that only render on hover
        of a parent, but are present in the DOM the whole time) is retried
        with force=True, which dispatches the click directly and skips
        Playwright's visibility/actionability checks.

        `frame_url`: if the target component was discovered inside an iframe
        (see `_discover_components`'s per-frame pass), this targets that
        frame's own document instead of the top-level page - see
        `_resolve_frame`. Defaults to the main page, unchanged for every
        caller/backend that doesn't deal with iframes.
        """
        self._ensure_browser()
        target = self._resolve_frame(frame_url)
        try:
            target.click(selector, timeout=5000)
        except Exception as exc:
            if "not visible" not in str(exc):
                raise
            print(f"Element not visible, retrying with a forced click: {selector}")
            target.click(selector, timeout=5000, force=True)

        try:
            self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as exc:
            print(f"Warning: page did not reach idle after clicking {selector}: {exc}")

        time.sleep(self.wait_seconds)
        return self.get_state()

    def fill(self, selector: str, value: str, frame_url: Optional[str] = None) -> PageState:
        """Type `value` into an input/textarea and capture new deep state.

        Same visibility-retry discipline as click(): the primary action must
        raise on real failure, only the post-fill networkidle wait is
        best-effort (see click()'s docstring for why). `frame_url`: see click()'s
        docstring.
        """
        self._ensure_browser()
        target = self._resolve_frame(frame_url)
        try:
            target.fill(selector, value, timeout=5000)
        except Exception as exc:
            if "not visible" not in str(exc):
                raise
            print(f"Element not visible, retrying fill with a forced click first: {selector}")
            target.click(selector, timeout=5000, force=True)
            target.fill(selector, value, timeout=5000)

        try:
            self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as exc:
            print(f"Warning: page did not reach idle after filling {selector}: {exc}")

        time.sleep(self.wait_seconds)
        return self.get_state()

    def submit(self, selector: str, frame_url: Optional[str] = None) -> PageState:
        """Press Enter on `selector` (typically right after fill) and capture new deep state.

        Covers the common single-field search/login submit pattern without
        needing a second element ref for a distinct submit button. `frame_url`:
        see click()'s docstring.
        """
        self._ensure_browser()
        target = self._resolve_frame(frame_url)
        target.press(selector, "Enter", timeout=5000)

        try:
            self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as exc:
            print(f"Warning: page did not reach idle after submitting {selector}: {exc}")

        time.sleep(self.wait_seconds)
        return self.get_state()

    def extract_context(self, max_chars: int = 1500) -> str:
        """Deeper one-time read of the current page for `SimplePRDGenerator._establish_site_context` -
        see `Scraper.extract_context`'s docstring for why this is separate from
        `_extract_description`.

        Unlike `_extract_description` (meta description, else first heading + first
        substantial paragraph - deliberately terse since it's repeated every turn),
        this collects *every* h1/h2/h3 (deduped, in document order - a real site's
        headings are usually its own table of contents of what it does/sells) plus the
        first several substantial paragraphs (not just one), so a business whose
        purpose isn't stated in a single meta tag or opening line still comes through -
        e.g. a product listing whose "what we sell" only becomes clear across a few
        section headings and blurbs, not one paragraph.
        """
        script = """(maxChars) => {
            const seen = new Set();
            const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
                .map(h => h.innerText.trim())
                .filter(t => t.length > 1 && !seen.has(t) && seen.add(t));
            const paragraphs = Array.from(document.querySelectorAll('p'))
                .map(p => p.innerText.trim())
                .filter(t => t.length > 20)
                .slice(0, 5);
            const metaDesc = document.querySelector('meta[name="description"]');
            const parts = [];
            if (metaDesc && metaDesc.getAttribute('content')) {
                parts.push(metaDesc.getAttribute('content').trim());
            }
            if (headings.length) parts.push('Headings: ' + headings.join(' | '));
            if (paragraphs.length) parts.push(paragraphs.join(' '));
            return parts.join('\\n').slice(0, maxChars);
        }"""
        self._ensure_browser()
        return self._page.evaluate(script, max_chars) or ""

    def get_state(self) -> PageState:
        """Extract current page structure and interactive DNA."""
        self._ensure_browser()
        return PageState(
            url=self._page.url,
            title=self._page.title(),
            metadata=self._extract_metadata(),
            components=self._discover_components(),
            links=self._extract_links(),
            description=self._extract_description(),
        )

    def _extract_description(self) -> str:
        """A short (~300 char) description of what this page is about, for the
        model to read as page-level context (see `_build_iteration_prompt` in
        prd_generator.py) and for the final PRD to explain the app from, not
        just list its routes/components.

        Prefers the page's own `<meta name="description">` (a site author's
        own summary, when present) over guessing from body content; falls
        back to the first heading + first substantial paragraph (>20 chars,
        to skip short nav labels/badges that happen to be in a <p>) - a
        reasonable proxy for "what is this page about" without needing any
        NLP, matching the codebase's existing no-ML-retrieval philosophy
        (see src/api_server/static_docs.py's docstring).
        """
        script = """() => {
            const metaDesc = document.querySelector('meta[name="description"]');
            if (metaDesc && metaDesc.getAttribute('content')) {
                return metaDesc.getAttribute('content').trim();
            }
            const h1 = document.querySelector('h1');
            const heading = h1 ? h1.innerText.trim() : '';
            const paragraphs = Array.from(document.querySelectorAll('p'))
                .map(p => p.innerText.trim())
                .filter(t => t.length > 20);
            const paragraph = paragraphs.length ? paragraphs[0] : '';
            return [heading, paragraph].filter(Boolean).join(' - ');
        }"""
        text = self._page.evaluate(script) or ""
        return text[:300]

    def _extract_metadata(self) -> Dict[str, str]:
        """Extract meta tags and semantic markers."""
        script = """() => {
            const meta = {};
            document.querySelectorAll('meta').forEach(m => {
                const name = m.getAttribute('name') || m.getAttribute('property');
                if (name) meta[name] = m.getAttribute('content');
            });
            return meta;
        }"""
        return self._page.evaluate(script)

    def _discover_components(self) -> List[Dict[str, Any]]:
        """Perform deep discovery of all interactive components.

        Every returned component also carries `rect` ({x, y, width, height},
        viewport-relative CSS pixels at discovery time - see `getRect`) -
        SimplePRDGenerator persists this into the graph store's component
        checklist alongside `interacted`, so the checklist is a precise map
        of *where* on the page each component is, not just that it exists.

        Paths are built as valid, unique CSS selectors: an element with an id
        uses `tag#id`; otherwise it gets a `:nth-of-type(n)` index among its
        same-tag siblings. Without this, sibling elements with no id (e.g. every
        link in a nav menu) produce identical path strings, which then fail as
        CSS selectors with a Playwright "strict mode: resolved to N elements"
        error on click - silently, since click() only logs such failures.

        Each component's `text` uses a broadened fallback chain (see
        `getAccessibleLabel` below) rather than just `innerText`/`aria-label` -
        `innerText` is empty for anything CSS-hidden (e.g. a visually-hidden
        accessible-label span), which otherwise makes a real, labelled
        component indistinguishable from a genuinely empty one downstream in
        the component catalog (see component_classifier.py/prd_generator.py).

        Discovery has two layers, in order of preference: native/ARIA-role
        elements (see the `selector` below - covers native tags plus the
        common custom-widget ARIA roles Radix/shadcn/MUI/etc. build listbox
        options, menu items, tabs, etc. out of), then a `cursor: pointer`
        catch-all for the remaining case of a fully custom clickable element
        with no semantic tag or ARIA role at all. Each returned component
        carries `discovery_layer` ("semantic" or "pointer") recording which
        layer found it - consumed by SimplePRDGenerator/GraphStore to exclude
        the noisier catch-all layer from completion-guard "unexplored
        component" counts (`semantic_only=True`).

        Elements inside an *open* shadow root are found too: `collectRoots`
        recurses into every element's `.shadowRoot` and the discovery selector
        is run against each collected root in addition to `document` - closed
        roots (`mode: 'closed'`) are skipped for free, since `.shadowRoot` is
        `null` there (no separate open/closed detection needed). `gp()`'s
        parent-walk continues across a shadow boundary via
        `e.getRootNode().host` when `e.parentElement` is null but
        `e.getRootNode()` is a ShadowRoot, so a shadow-DOM element still gets a
        real, resolvable-by-Playwright CSS path (Playwright's own selector
        engine pierces shadow roots with plain CSS, so no special click-side
        handling is needed once the path itself is correct).
        """
        script = """() => {
            const collectRoots = (root, out) => {
                out.push(root);
                const all = root === document ? document.querySelectorAll('*') : root.querySelectorAll('*');
                for (const el of all) {
                    if (el.shadowRoot) collectRoots(el.shadowRoot, out);
                }
            };
            const roots = [];
            collectRoots(document, roots);

            const gp = (e, p=[]) => {
                while (e) {
                    if (!e.parentElement) {
                        const root = e.getRootNode();
                        if (root instanceof ShadowRoot) {
                            e = root.host;
                            continue;
                        }
                        break;
                    }
                    let seg = e.tagName.toLowerCase();
                    if (e.id) {
                        // CSS.escape() is required, not cosmetic: component libraries
                        // like Radix UI generate ids such as "radix-:r0:" - a colon is
                        // legal in an HTML id but starts a pseudo-class in a CSS
                        // selector, so concatenating the raw id (`'#' + e.id`) produced
                        // an invalid selector ("Unexpected token" from Playwright) that
                        // could never be clicked, no matter how many times the model
                        // picked its ref.
                        seg += '#' + CSS.escape(e.id);
                    } else {
                        const siblings = Array.from(e.parentElement.children)
                            .filter(c => c.tagName === e.tagName);
                        if (siblings.length > 1) {
                            seg += ':nth-of-type(' + (siblings.indexOf(e) + 1) + ')';
                        }
                    }
                    p.unshift(seg);
                    e = e.parentElement;
                }
                return p.join(' > ');
            };
            // A mega-menu/dropdown's items are commonly present in the DOM the
            // whole time, just CSS-hidden until a trigger is clicked/hovered -
            // this flags that so _build_iteration_prompt can prioritize what's
            // actually visible right now over raw DOM order (see its docstring:
            // on a real nav-heavy page, hundreds of components can exist before
            // batch_size is reached, permanently burying anything a click just
            // revealed if only DOM order is used).
            const isVisible = (e) => {
                const style = getComputedStyle(e);
                if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
                    return false;
                }
                const rect = e.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            // Viewport-relative bounding box, in CSS pixels, at discovery time -
            // rounded to whole pixels since sub-pixel precision isn't meaningful
            // here (nothing consumes it at that resolution) and keeps the
            // payload smaller on a component-dense page. This is what makes the
            // persisted component checklist a genuinely *precise* map of the
            // page - not just "this exists" but "this exists right here" -
            // rather than recomputing `isVisible`'s rect and throwing it away.
            const getRect = (e) => {
                const r = e.getBoundingClientRect();
                return { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) };
            };
            // A text input's `placeholder` is often absent even when a real,
            // human-readable label exists right next to it (<label for="...">
            // is the standard accessible-forms pattern) - without this, a
            // labelled-but-placeholder-less field looked identical to the
            // model to an unlabelled one, leaving it no way to know what the
            // field is actually for before generating a value to fill() with.
            const getLabel = (e) => {
                if (e.id) {
                    const lbl = document.querySelector(`label[for="${CSS.escape(e.id)}"]`);
                    if (lbl && lbl.innerText.trim()) return lbl.innerText.trim();
                }
                const parentLabel = e.closest('label');
                if (parentLabel && parentLabel.innerText.trim()) return parentLabel.innerText.trim();
                const labelledBy = e.getAttribute('aria-labelledby');
                if (labelledBy) {
                    const ref = document.getElementById(labelledBy);
                    if (ref && ref.innerText.trim()) return ref.innerText.trim();
                }
                return '';
            };
            // A component's accessible text can live somewhere `innerText`/
            // `aria-label` never look: `innerText` returns '' for anything
            // CSS-hidden (a common sr-only/visually-hidden accessibility
            // utility class wrapping the *real* label next to a decorative
            // icon), and a bare `aria-label` check misses `aria-labelledby`,
            // `title`, an `<img alt>` child, or an SVG `<title>` child - all
            // legitimate accessible-name sources. A real crawl (empanad.app)
            // hit exactly this: a header `<a href="/">` wrapping only
            // `<img alt="EmpanadApp">` with no aria-label of its own -
            // `innerText` and `aria-label` were both '', so the component
            // catalog narrated it as "Unnamed Element"/"Empty Element" even
            // though the real label was one attribute away. Order matters:
            // check the cheap/specific sources before the broad
            // `textContent` fallback, so a real label is preferred over
            // incidental hidden text.
            const getAccessibleLabel = (e) => {
                const ariaLabel = e.getAttribute('aria-label');
                if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();
                const labelledBy = e.getAttribute('aria-labelledby');
                if (labelledBy) {
                    const ref = document.getElementById(labelledBy);
                    if (ref && ref.innerText.trim()) return ref.innerText.trim();
                }
                const title = e.getAttribute('title');
                if (title && title.trim()) return title.trim();
                const img = e.querySelector('img[alt]');
                if (img) {
                    const alt = img.getAttribute('alt');
                    if (alt && alt.trim()) return alt.trim();
                }
                const svgTitle = e.querySelector('svg > title');
                if (svgTitle && svgTitle.textContent.trim()) return svgTitle.textContent.trim();
                return '';
            };
            // Modern component libraries (Radix, shadcn/ui's Command/cmdk, MUI,
            // Headless UI, ...) build most non-native widgets - listbox/combobox
            // options, menu items, tabs, custom checkboxes/radios/switches - out
            // of <div>/<li> with an ARIA role, not a real <button>/<input>. A
            // real crawl (empanad.app) opened a searchable shop-picker popover
            // with 22 real, clickable role="option" divs that were completely
            // invisible here - the model had nothing to act on but the trigger
            // it had already clicked, forever. `[role="button"]` alone only
            // covers one such pattern; this covers the rest of the common ones
            // without depending on any specific component library's markup.
            const selector = 'button, a, input, select, textarea, ' +
                '[role="button"], [role="option"], [role="menuitem"], ' +
                '[role="menuitemcheckbox"], [role="menuitemradio"], [role="tab"], ' +
                '[role="checkbox"], [role="radio"], [role="switch"], [role="combobox"]';
            const semanticEls = roots.flatMap(r => Array.from(r.querySelectorAll(selector)));
            const semanticSet = new Set(semanticEls);

            // Fallback for the remaining case: a fully custom clickable element
            // with no semantic tag AND no ARIA role at all (e.g. a styled <div
            // onClick=...> with no accessibility markup - poor practice, but
            // real). `cursor: pointer` is the one signal that survives even
            // then. Excluded: anything inside a semantic element's subtree in
            // *either* direction - a pointer-cursor <div> wrapping a real
            // <button> is redundant with that button, and so (this bit on
            // first attempt) is a real <button>'s own inner <span> that
            // happens to inherit cursor:pointer from it; clicking either
            // achieves the same thing as clicking the semantic element itself,
            // so only the semantic element should get a ref. Also requires
            // real text/aria-label so empty decorative wrappers don't flood
            // the list. Capped at 100 - this is meant to catch the occasional
            // custom widget, not become the primary discovery path (that's
            // still the semantic selector above, which stays first/preferred
            // in the returned list).
            const pointerEls = [];
            outer:
            for (const r of roots) {
                const scope = r === document ? document.body : r;
                if (!scope) continue;
                for (const el of scope.querySelectorAll('*')) {
                    if (pointerEls.length >= 100) break outer;
                    if (semanticSet.has(el)) continue;
                    if (el.closest(selector)) continue;
                    if (getComputedStyle(el).cursor !== 'pointer') continue;
                    const label = el.innerText?.trim() || getAccessibleLabel(el);
                    if (!label) continue;
                    let wrapsSemantic = false;
                    for (const child of el.querySelectorAll('*')) {
                        if (semanticSet.has(child)) { wrapsSemantic = true; break; }
                    }
                    if (wrapsSemantic) continue;
                    pointerEls.push(el);
                }
            }

            const layerOf = (el) => semanticSet.has(el) ? 'semantic' : 'pointer';
            return [...semanticEls, ...pointerEls]
                .map(el => ({
                    tag: el.tagName.toLowerCase(),
                    // Last-resort fallback is `textContent` (not just
                    // `innerText`/`aria-label`/`getAccessibleLabel`) - it
                    // ignores CSS visibility entirely, so it can recover text
                    // from a visually-hidden sr-only span or a disconnected
                    // inline SVG label that none of the above sources catch.
                    // Accepted here (unlike the pointer-catch-all layer above,
                    // which deliberately stops at getAccessibleLabel) because
                    // by this point something recoverable is strictly better
                    // than the catalog narrating a real, meaningful component
                    // as "Unnamed Element"/"Empty Element".
                    text: el.innerText.trim() || getAccessibleLabel(el) || (el.textContent || '').trim(),
                    path: gp(el),
                    discovery_layer: layerOf(el),
                    // The nearest enclosing <form>'s own path, or '' if none - lets
                    // SimplePRDGenerator._page_structure_line group its submit-readiness
                    // nudge per form instead of whole-page, so a page with two
                    // independent forms (e.g. newsletter signup + contact form) doesn't
                    // treat "any submit button anywhere" as gating "any unfilled field
                    // anywhere."
                    form: el.closest('form') ? gp(el.closest('form')) : '',
                    // input_type/placeholder/label/role/disabled/visible let the model
                    // tell a text field it should `fill` apart from a button it should
                    // `click`, infer what a field is *for* even with no placeholder,
                    // and see what's currently on-screen - all without needing the
                    // full CSS path/class list - see _build_iteration_prompt in
                    // prd_generator.py, which renders only these fields (never `path`
                    // or `attributes.class`).
                    input_type: el.getAttribute('type') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    label: getLabel(el),
                    name: el.getAttribute('name') || '',
                    role: el.getAttribute('role') || '',
                    disabled: !!el.disabled,
                    // `value`/`required` are the difference between the model seeing
                    // "an empty field" and "a field I already filled, and still needs
                    // vs. doesn't need more" - without `value`, there's no way to tell
                    // a fill actually landed from the DNA list alone (only from the
                    // separate "Value typed" line SimplePRDGenerator logs after the
                    // fact); without `required`, no way to tell which of several
                    // fields actually block submission. Only meaningful on
                    // input/textarea/select - buttons/links/options get '' / false.
                    value: ['input', 'textarea', 'select'].includes(el.tagName.toLowerCase()) ? (el.value || '') : '',
                    required: ['input', 'textarea', 'select'].includes(el.tagName.toLowerCase()) ? !!el.required : false,
                    visible: isVisible(el),
                    rect: getRect(el),
                    // Whether this element is the currently-active/chosen one within its
                    // own group (a listbox option, a radio/checkbox, a tab) - component
                    // libraries (Radix/shadcn/MUI/...) mark this via one of several
                    // conventions depending on the widget, so all the common ones are
                    // checked rather than picking just one. Distinct from `value`, which
                    // is a text field's own typed content, not a member's membership
                    // state within a set of options. Consumed by SimplePRDGenerator's
                    // component classifier to report which option/choice is the default
                    // or currently-active one in the generated component catalog.
                    selected: el.getAttribute('aria-selected') === 'true' ||
                        el.getAttribute('aria-checked') === 'true' ||
                        el.getAttribute('data-state') === 'checked' ||
                        el.getAttribute('data-state') === 'on' ||
                        !!el.checked,
                    attributes: { id: el.id, class: el.className, href: el.getAttribute('href') || '' }
                }));
        }"""
        # Run in every frame on the page, not just the top-level document -
        # content inside an <iframe> (a common pattern for embedded widgets:
        # payment forms, chat, third-party signup) was previously invisible to
        # discovery entirely, since a single evaluate() against the main page
        # can't see across a frame boundary. Each frame's own components are
        # tagged `frame_url` (empty string for the main page - the overwhelming
        # common case stays exactly as before) so click()/fill()/submit() can
        # target the right document later (see `_resolve_frame`). A frame that
        # errors on evaluate (cross-origin, still loading, detached) is skipped
        # rather than failing the whole discovery pass.
        results: List[Dict[str, Any]] = []
        main_url = self._page.main_frame.url
        for frame in self._page.frames:
            try:
                frame_components = frame.evaluate(script)
            except Exception as exc:
                print(f"Warning: component discovery failed in frame {frame.url!r}: {exc}")
                continue
            frame_url = "" if frame.url == main_url else frame.url
            for comp in frame_components:
                comp["frame_url"] = frame_url
            results.extend(frame_components)
        return results

    def _extract_links(self) -> List[Dict[str, str]]:
        """Gather all unique, relevant hrefs and their labels, from every frame on
        the page (see `_discover_components`'s docstring for why).

        Every href-bearing anchor is kept, not just http(s) ones - a `scheme`
        field lets the caller (SimplePRDGenerator._update_discovered_routes)
        decide what to do with a mailto:/tel:/javascript: link explicitly
        (capture it, but don't queue it as a pending route - there's nothing
        to navigate to) instead of this layer silently dropping it before the
        caller ever sees it existed.
        """
        script = """() => {
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => {
                    let scheme = '';
                    try { scheme = new URL(a.href).protocol.replace(':', ''); } catch (e) {}
                    return { href: a.href, text: a.innerText.trim() || a.innerHTML.trim(), scheme };
                })
                .filter(l => l.href);
        }"""
        results: List[Dict[str, str]] = []
        for frame in self._page.frames:
            try:
                results.extend(frame.evaluate(script))
            except Exception as exc:
                print(f"Warning: link extraction failed in frame {frame.url!r}: {exc}")
        return results

    def close(self) -> None:
        """Shutdown browser and playwright."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._page = None
