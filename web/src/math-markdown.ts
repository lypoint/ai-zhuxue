// Models also emit TeX delimiters; convert prose while leaving Markdown code intact.
export function normalizeMathMarkdown(source: string): string {
  const prose = (text: string) => text
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, math: string) => `\n$$\n${math.trim()}\n$$\n`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, math: string) => `$${math}$`);
  const tokens = /(^ {0,3}(`{3,}|~{3,})[^\n]*(?:\n|$))|(`+)/gm;
  let result = "", cursor = 0, token: RegExpExecArray | null;
  while ((token = tokens.exec(source))) {
    let end: number;
    if (token[2]) {
      const fence = token[2];
      const close = new RegExp(`^ {0,3}${fence[0]}{${fence.length},}[ \\t]*(?:\\n|$)`, "gm");
      close.lastIndex = tokens.lastIndex;
      const match = close.exec(source);
      end = match ? close.lastIndex : source.length;
    } else {
      const close = /`+/g;
      close.lastIndex = tokens.lastIndex;
      let match: RegExpExecArray | null;
      do { match = close.exec(source); } while (match && match[0].length !== token[3].length);
      if (!match) continue;
      end = close.lastIndex;
    }
    result += prose(source.slice(cursor, token.index)) + source.slice(token.index, end);
    cursor = end;
    tokens.lastIndex = end;
  }
  return result + prose(source.slice(cursor));
}
