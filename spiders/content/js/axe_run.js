async () => {
    // Third copy of gp() in this directory, after discover_components.js and
    // extract_text_content.js. Deliberate: discover_components.js's selector
    // logic is explicitly not to be touched (wiki/browser-automation-pitfalls.md),
    // and unifying the helper means editing it. The duplication is ~25 lines
    // of pure function with no state; the alternative is risking the one piece
    // of DOM code this project most depends on.
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

    // axe reports a node as an array of selectors: one per frame, innermost
    // last. Only the last one addresses an element in this document.
    const ourPath = (target) => {
        const selector = Array.isArray(target) ? target[target.length - 1] : target;
        if (typeof selector !== 'string') return '';
        try {
            const element = document.querySelector(selector);
            if (!element) return '';
            // gp() deliberately stops below <html> - every path it builds
            // implicitly starts at <body>. So a document-level rule
            // (html-has-lang, page-has-heading-one) resolves to the empty
            // string, which would read as "we could not find it" rather
            // than "this is about the page, not an element".
            if (element === document.documentElement || element === document.body) {
                return '(document)';
            }
            return gp(element);
        } catch (e) {
            return '';
        }
    };

    // Scoped to WCAG A/AA. Without this, axe's best-practice rules come along
    // too and the document fills with findings that aren't WCAG at all.
    const results = await axe.run(document, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
        resultTypes: ['violations'],
    });

    return results.violations.map(v => ({
        rule_id: v.id,
        impact: v.impact || '',
        help: v.help || '',
        help_url: v.helpUrl || '',
        // Only the wcag* tags: axe also tags rules by category and version.
        criteria: (v.tags || []).filter(t => t.startsWith('wcag')),
        // Cap per rule - a global defect can hit hundreds of nodes, and the
        // document needs enough to act on, not the whole list.
        nodes: (v.nodes || []).slice(0, 25).map(n => ({
            path: ourPath(n.target),
            axe_target: Array.isArray(n.target) ? n.target.join(' ') : String(n.target || ''),
            summary: (n.failureSummary || '').split('\n').filter(Boolean).slice(0, 2).join(' '),
        })),
        total_nodes: (v.nodes || []).length,
    }));
}
