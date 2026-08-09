() => {
    const meta = {};
    document.querySelectorAll('meta').forEach(m => {
        const name = m.getAttribute('name') || m.getAttribute('property');
        if (name) meta[name] = m.getAttribute('content');
    });
    return meta;
}
