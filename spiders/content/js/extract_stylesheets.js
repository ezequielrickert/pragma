() => {
    // Same-origin CSS text, one entry per stylesheet - the raw styling data
    // behind design-token generation, captured directly instead of only
    // ever inferred from getComputedStyle() on discovered components.
    //
    // A cross-origin stylesheet (a CDN-hosted font/framework CSS file)
    // throws reading .cssRules - the same restriction
    // extract_pseudo_styles.js already works around, and there is no way
    // around it here either: that stylesheet's rules stay unreadable from
    // page JS, so it reports as inaccessible rather than silently empty.
    const sheets = [];
    for (const sheet of Array.from(document.styleSheets)) {
        let cssText = '';
        let accessible = true;
        try {
            cssText = Array.from(sheet.cssRules || []).map(r => r.cssText).join('\n');
        } catch (e) {
            accessible = false;
        }
        sheets.push({
            href: sheet.href || '',
            accessible,
            text: cssText,
        });
    }
    return sheets;
}
