function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Minimal, dependency-free markdown -> safe HTML. Escapes first, so nothing
// in the input (model output or vault content) can inject real markup —
// only the tags this function itself adds are real.
export function renderMarkdown(raw) {
  const lines = escapeHtml(raw).split('\n');
  const blocks = [];
  let listBuffer = [];
  let listType = null;

  function flushList() {
    if (listBuffer.length) {
      const tag = listType === 'ol' ? 'ol' : 'ul';
      blocks.push(`<${tag}>${listBuffer.map((li) => `<li>${li}</li>`).join('')}</${tag}>`);
      listBuffer = [];
      listType = null;
    }
  }

  function inline(text) {
    return text
      .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');
  }

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === '') continue;

    const bulletMatch = trimmed.match(/^[-*]\s+(.*)/);
    const numberedMatch = trimmed.match(/^\d+\.\s+(.*)/);
    const headerMatch = trimmed.match(/^(#{1,3})\s+(.*)/);

    if (bulletMatch) {
      if (listType !== 'ul') flushList();
      listType = 'ul';
      listBuffer.push(inline(bulletMatch[1]));
    } else if (numberedMatch) {
      if (listType !== 'ol') flushList();
      listType = 'ol';
      listBuffer.push(inline(numberedMatch[1]));
    } else {
      flushList();
      if (headerMatch) {
        const level = headerMatch[1].length + 3;
        blocks.push(`<h${level}>${inline(headerMatch[2])}</h${level}>`);
      } else {
        blocks.push(`<p>${inline(line)}</p>`);
      }
    }
  }
  flushList();

  return blocks.join('');
}
