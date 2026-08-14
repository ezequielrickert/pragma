() => {
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
}
