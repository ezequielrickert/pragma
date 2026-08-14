() => {
    // Duplicates a small slice of discover_components.js's own gp()/
    // isVisible()/getRect() helpers and interactive-selector string, rather
    // than importing a shared module - crawl4ai's page.evaluate() takes a
    // single self-contained script with no module system, and this file
    // must not touch discover_components.js's own battle-tested logic.
    // Accepted near-term duplication (~20 lines); a shared _dom_helpers.js
    // extraction is a reasonable future cleanup once a third script needs
    // the same helpers, not a blocker for this one.
    const gp = (e, p = []) => {
        while (e) {
            if (!e.parentElement) {
                const root = e.getRootNode();
                if (root instanceof ShadowRoot) {
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
                break;
            }
            let seg = e.tagName.toLowerCase();
            if (e.id) {
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
    const isVisible = (e) => {
        const style = getComputedStyle(e);
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

    // Same interactive selector discover_components.js uses - anything it
    // matches (or contains, or is contained by) is that component's own
    // label text, not a separate text-content leaf. Kept identical (not
    // imported) for the same self-contained-script reason noted above.
    const interactiveSelector = 'button, a, input, select, textarea, ' +
        '[role="button"], [role="option"], [role="menuitem"], ' +
        '[role="menuitemcheckbox"], [role="menuitemradio"], [role="tab"], ' +
        '[role="checkbox"], [role="radio"], [role="switch"], [role="combobox"]';

    // Block-level prose elements - headings, paragraphs, list items, and a
    // few other common text-bearing tags.
    const textSelector = 'p, h1, h2, h3, h4, h5, h6, li, blockquote, figcaption, dt, dd';

    const results = [];
    for (const el of document.querySelectorAll(textSelector)) {
        // A <p> inside a <button> is that button's own label (already
        // captured by discover_components.js's text-extraction chain) - not
        // a separate leaf. Exclude anything matched by, contained in, or
        // containing an interactive element.
        if (el.matches(interactiveSelector)) continue;
        if (el.closest(interactiveSelector)) continue;
        if (el.querySelector(interactiveSelector)) continue;

        // Own direct text only - not el.innerText, which would double-count
        // a <div><h2>Title</h2><p>Body</p></div>'s combined text under both
        // the div (if it matched, which it doesn't here, but the principle
        // applies to nested prose tags like <li><p>...</p></li>) and each
        // child individually.
        const ownText = Array.from(el.childNodes)
            .filter(n => n.nodeType === 3)
            .map(n => n.textContent)
            .join(' ')
            .trim();
        if (!ownText) continue;

        results.push({
            tag: el.tagName.toLowerCase(),
            text: ownText,
            path: gp(el),
            visible: isVisible(el),
            rect: getRect(el),
        });
    }
    return results;
}
