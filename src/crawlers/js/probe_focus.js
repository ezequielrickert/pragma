() => {
    // Describes whatever currently has focus: which element it is, and
    // whether a sighted keyboard user could tell. Called after each Tab
    // press by the measurement pass.
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

    // Focus can land inside a shadow root; activeElement then reports the
    // host, and the real target is one level in.
    let element = document.activeElement;
    while (element && element.shadowRoot && element.shadowRoot.activeElement) {
        element = element.shadowRoot.activeElement;
    }
    if (!element || element === document.body || element === document.documentElement) {
        return null;
    }

    const style = getComputedStyle(element);
    // WCAG 2.4.7 asks whether focus is *visible*, not whether an outline
    // property exists. A UA default outline counts; `outline: none` with
    // nothing put back does not, and that is the common failure - a reset
    // stylesheet removing it and never replacing it.
    const hasOutline = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth || '0') > 0;
    const hasShadow = (style.boxShadow || 'none') !== 'none';
    const rect = element.getBoundingClientRect();

    return {
        path: gp(element),
        tag: element.tagName.toLowerCase(),
        text: (element.innerText || element.getAttribute('aria-label') || '').trim().slice(0, 60),
        focus_visible: hasOutline || hasShadow,
        // DOM order of this element among all focusable ones, so a tab
        // sequence that jumps around can be told from one that doesn't.
        dom_index: Array.from(
            document.querySelectorAll(
                'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
            )
        ).indexOf(element),
        tabindex: element.getAttribute('tabindex') || '',
        offscreen: rect.width === 0 && rect.height === 0,
    };
}
