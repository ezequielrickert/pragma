() => {
    const collectRoots = (root, out) => {
        out.push(root);
        const all = root === document ? document.querySelectorAll('*') : root.querySelectorAll('*');
        for (const el of all) {
            if (el.shadowRoot) collectRoots(el.shadowRoot, out);
        }
    };
    const roots = [];
    collectRoots(document, roots);

    // gp() builds a valid, unique CSS selector path for an element - ported
    // verbatim from PlaywrightScraper._discover_components, with one fix (see
    // below) found via the crawl4ai migration spike (2026-08-07).
    const gp = (e, p = []) => {
        while (e) {
            if (!e.parentElement) {
                const root = e.getRootNode();
                if (root instanceof ShadowRoot) {
                    // FIX (found via crawl4ai spike, not present in the original
                    // PlaywrightScraper code): `e` is a shadow root's *direct*
                    // child - per the DOM spec its `parentElement` is null (a
                    // ShadowRoot is not an Element), so the original code jumped
                    // straight to `root.host` here without ever computing this
                    // element's own segment. That silently dropped the element
                    // from its own path, resolving to the shadow host's path
                    // instead - confirmed live: a shadow-root-direct-child
                    // <button id="shadowBtn"> resolved to its host div's path,
                    // not its own. Disambiguate against the ShadowRoot's own
                    // children (a ShadowRoot has `.children` just like an
                    // Element) before climbing to the host, mirroring the normal
                    // sibling-disambiguation branch below exactly.
                    let seg = e.tagName.toLowerCase();
                    if (e.id) {
                        seg += '#' + CSS.escape(e.id);
                    } else {
                        const siblings = Array.from(root.children).filter(c => c.tagName === e.tagName);
                        if (siblings.length > 1) {
                            seg += ':nth-of-type(' + (siblings.indexOf(e) + 1) + ')';
                        }
                    }
                    p.unshift(seg);
                    e = root.host;
                    continue;
                }
                // Top of the real document (e.g. <html>, whose parent is
                // `document`, not an Element) - intentionally not added to the
                // path; every path already implicitly starts at <body> the same
                // way it always has.
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
    // getComputedStyle() forces a style recalculation - cache it per element
    // so the pointer-cursor scan, isVisible, and getStyleFacts each read one
    // computed style per element instead of recomputing it 2-3x over.
    const styleCache = new WeakMap();
    const styleOf = (e) => {
        let s = styleCache.get(e);
        if (!s) {
            s = getComputedStyle(e);
            styleCache.set(e, s);
        }
        return s;
    };
    const isVisible = (e) => {
        const style = styleOf(e);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
            return false;
        }
        const rect = e.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };
    const getRect = (e) => {
        const r = e.getBoundingClientRect();
        return { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) };
    };
    // Small, curated subset of getComputedStyle() - just enough for a future
    // visual-reconstruction pass (Modulo 3) to tell "this looks like a heading"
    // from "this looks like a disabled button" without re-crawling the site.
    // Not the full CSSStyleDeclaration: most properties are noise for that use.
    const getStyleFacts = (e) => {
        const s = styleOf(e);
        return {
            color: s.color,
            background_color: s.backgroundColor,
            font_size: s.fontSize,
            font_weight: s.fontWeight,
            display: s.display,
            position: s.position,
        };
    };
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
    const selector = 'button, a, input, select, textarea, ' +
        '[role="button"], [role="option"], [role="menuitem"], ' +
        '[role="menuitemcheckbox"], [role="menuitemradio"], [role="tab"], ' +
        '[role="checkbox"], [role="radio"], [role="switch"], [role="combobox"]';
    const semanticEls = roots.flatMap(r => Array.from(r.querySelectorAll(selector)));
    const semanticSet = new Set(semanticEls);

    // Elements that contain (or are) a semantic element - precomputed by
    // walking up from each semantic element once, instead of a nested
    // querySelectorAll('*') per pointer-cursor candidate (was O(n*m) on a
    // large DOM; this is O(n) in the number of semantic elements).
    const semanticAncestors = new Set();
    for (const el of semanticEls) {
        let cur = el.parentElement;
        while (cur && !semanticAncestors.has(cur)) {
            semanticAncestors.add(cur);
            cur = cur.parentElement;
        }
    }

    const pointerEls = [];
    outer:
    for (const r of roots) {
        const scope = r === document ? document.body : r;
        if (!scope) continue;
        for (const el of scope.querySelectorAll('*')) {
            if (pointerEls.length >= 100) break outer;
            if (semanticSet.has(el)) continue;
            if (semanticAncestors.has(el)) continue;
            if (el.closest(selector)) continue;
            if (styleOf(el).cursor !== 'pointer') continue;
            const label = el.innerText?.trim() || getAccessibleLabel(el);
            if (!label) continue;
            pointerEls.push(el);
        }
    }

    const layerOf = (el) => semanticSet.has(el) ? 'semantic' : 'pointer';
    return [...semanticEls, ...pointerEls]
        .map(el => ({
            tag: el.tagName.toLowerCase(),
            text: el.innerText.trim() || getAccessibleLabel(el) || (el.textContent || '').trim(),
            path: gp(el),
            discovery_layer: layerOf(el),
            form: el.closest('form') ? gp(el.closest('form')) : '',
            input_type: el.getAttribute('type') || '',
            placeholder: el.getAttribute('placeholder') || '',
            label: getLabel(el),
            name: el.getAttribute('name') || '',
            role: el.getAttribute('role') || '',
            disabled: !!el.disabled,
            value: ['input', 'textarea', 'select'].includes(el.tagName.toLowerCase()) ? (el.value || '') : '',
            required: ['input', 'textarea', 'select'].includes(el.tagName.toLowerCase()) ? !!el.required : false,
            visible: isVisible(el),
            rect: getRect(el),
            style: getStyleFacts(el),
            selected: el.getAttribute('aria-selected') === 'true' ||
                el.getAttribute('aria-checked') === 'true' ||
                el.getAttribute('data-state') === 'checked' ||
                el.getAttribute('data-state') === 'on' ||
                !!el.checked,
            attributes: { id: el.id, class: el.className, href: el.getAttribute('href') || '' }
        }));
}
