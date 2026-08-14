() => {
    // Reads the styles a control takes on :hover and :focus, which
    // getComputedStyle can never report - it only ever describes the state
    // the element is actually in, and the crawl never hovers anything.
    //
    // Reads the *declared* rules rather than forcing the pseudo-state
    // through CDP. Two reasons: it needs no debugger protocol session at
    // all, and a declared value is what a design token is - `#1a4f9c` from
    // the stylesheet beats the same colour resolved through whatever the
    // element happened to inherit.
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

    // Only the properties a component library actually varies per state.
    // The full declaration block would be mostly layout noise.
    const TRACKED = ['color', 'background-color', 'border-color', 'box-shadow', 'outline', 'opacity'];

    const collectRules = () => {
        const rules = [];
        for (const sheet of Array.from(document.styleSheets)) {
            let sheetRules;
            try {
                // A cross-origin stylesheet throws here. Skipping it is the
                // only option - and worth stating, since it means a site
                // whose CSS is on a CDN reports fewer state styles.
                sheetRules = sheet.cssRules;
            } catch (e) {
                continue;
            }
            for (const rule of Array.from(sheetRules || [])) {
                if (!rule.selectorText || !rule.style) continue;
                for (const selector of rule.selectorText.split(',')) {
                    const trimmed = selector.trim();
                    const state = trimmed.includes(':hover') ? 'hover'
                        : (trimmed.includes(':focus') ? 'focus' : '');
                    if (!state) continue;
                    // Strip the pseudo-class so the remainder can be matched
                    // against a real element in its resting state.
                    const base = trimmed
                        .replace(/:hover/g, '')
                        .replace(/:focus-visible/g, '')
                        .replace(/:focus-within/g, '')
                        .replace(/:focus/g, '')
                        .trim();
                    if (!base) continue;
                    rules.push({ base, state, style: rule.style });
                }
            }
        }
        return rules;
    };

    const rules = collectRules();
    if (!rules.length) return [];

    const selector = 'button, a, input, select, textarea, ' +
        '[role="button"], [role="checkbox"], [role="radio"], [role="switch"], [role="combobox"], [role="tab"]';
    const results = [];
    for (const element of Array.from(document.querySelectorAll(selector))) {
        const states = {};
        for (const rule of rules) {
            let matches = false;
            try {
                matches = element.matches(rule.base);
            } catch (e) {
                continue;  // a selector we cannot evaluate is not a match
            }
            if (!matches) continue;
            const declared = states[rule.state] || (states[rule.state] = {});
            for (const property of TRACKED) {
                const value = rule.style.getPropertyValue(property);
                // Later rules win, mirroring the cascade closely enough for
                // a token inventory - full specificity resolution is not
                // worth reimplementing here.
                if (value) declared[property] = value.trim();
            }
        }
        if (Object.keys(states).length) {
            results.push({ path: gp(element), states });
        }
    }
    return results;
}
