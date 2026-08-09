() => {
    return Array.from(document.querySelectorAll('a[href]'))
        .map(a => {
            let scheme = '';
            try { scheme = new URL(a.href).protocol.replace(':', ''); } catch (e) {}
            return { href: a.href, text: a.innerText.trim() || a.innerHTML.trim(), scheme };
        })
        .filter(l => l.href);
}
