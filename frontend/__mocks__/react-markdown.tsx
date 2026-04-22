/**
 * Jest manual mock for react-markdown.
 *
 * react-markdown is a pure-ESM package — Jest's CommonJS transformer cannot
 * handle it without a complex Babel/swc ESM pipeline. Since the component
 * tests exercise our custom renderers (not react-markdown's internals), we
 * mock the library to a simple passthrough renderer that still calls our
 * `components` prop overrides so they can be tested in isolation.
 *
 * Next.js compiles the real react-markdown at build/dev time — this mock only
 * applies during `npm test`.
 */
import React from 'react'

// Minimal stub: renders children through our custom component overrides
// by parsing the Markdown string ourselves (just enough for test assertions).
const ReactMarkdown = ({
  children,
  components: overrides = {},
}: {
  children: string
  components?: Record<string, React.ElementType>
  remarkPlugins?: unknown[]
}) => {
  // Render a thin approximation of the AST so test assertions can find the
  // right elements (headings, paragraphs, tables, etc.).
  const lines = children.split('\n')
  const elements: React.ReactNode[] = []

  let inTable = false
  const tableRows: string[][] = []
  let rowIndex = 0

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // H1
    if (/^# /.test(line)) {
      const H1 = (overrides.h1 as React.ElementType) || 'h1'
      elements.push(<H1 key={i}>{line.slice(2)}</H1>)
      continue
    }
    // H2
    if (/^## /.test(line)) {
      const H2 = (overrides.h2 as React.ElementType) || 'h2'
      elements.push(<H2 key={i}>{line.slice(3)}</H2>)
      continue
    }
    // H3
    if (/^### /.test(line)) {
      const H3 = (overrides.h3 as React.ElementType) || 'h3'
      elements.push(<H3 key={i}>{line.slice(4)}</H3>)
      continue
    }
    // GFM table row (starts and ends with |)
    if (/^\|.+\|$/.test(line)) {
      if (!inTable) { inTable = true; tableRows.length = 0; rowIndex = 0 }
      const cells = line.split('|').slice(1, -1).map(c => c.trim())
      if (!cells.every(c => /^-+$/.test(c))) {
        tableRows.push(cells)
        rowIndex++
      }
      continue
    }
    // End of table
    if (inTable) {
      inTable = false
      const Table = (overrides.table as React.ElementType) || 'table'
      const Thead = (overrides.thead as React.ElementType) || 'thead'
      const Tbody = (overrides.tbody as React.ElementType) || 'tbody'
      const Tr   = (overrides.tr   as React.ElementType) || 'tr'
      const Th   = (overrides.th   as React.ElementType) || 'th'
      const Td   = (overrides.td   as React.ElementType) || 'td'
      const [header, ...rows] = tableRows
      elements.push(
        <Table key={`table-${i}`}>
          <Thead>
            <Tr>{header.map((h, j) => <Th key={j}>{h}</Th>)}</Tr>
          </Thead>
          <Tbody>
            {rows.map((row, ri) => (
              <Tr key={ri}>{row.map((cell, ci) => <Td key={ci}>{cell}</Td>)}</Tr>
            ))}
          </Tbody>
        </Table>
      )
    }
    // Blockquote
    if (/^> /.test(line)) {
      const Bq = (overrides.blockquote as React.ElementType) || 'blockquote'
      const P  = (overrides.p as React.ElementType) || 'p'
      // Strip bold markers for assertion simplicity
      const text = line.slice(2).replace(/\*\*(.+?)\*\*/g, '$1')
      elements.push(<Bq key={i}><P>{text}</P></Bq>)
      continue
    }
    // HR
    if (/^---$/.test(line)) {
      const Hr = (overrides.hr as React.ElementType) || 'hr'
      elements.push(<Hr key={i} />)
      continue
    }
    // List item
    if (/^[-*] /.test(line)) {
      const Li = (overrides.li as React.ElementType) || 'li'
      elements.push(<Li key={i}>{line.slice(2)}</Li>)
      continue
    }
    // Inline elements in paragraph: bold, code, link
    if (line.trim()) {
      const P = (overrides.p as React.ElementType) || 'p'
      // Detect inline code, links, bold and convert to appropriate elements
      const parts: React.ReactNode[] = []
      let rest = line
      // bold  **text**
      rest = rest.replace(/\*\*(.+?)\*\*/g, (_, t) => `__STRONG__${t}__STRONG__`)
      // inline code `text`
      rest = rest.replace(/`(.+?)`/g, (_, t) => `__CODE__${t}__CODE__`)
      // link [text](href)
      rest = rest.replace(/\[(.+?)\]\((.+?)\)/g, (_, t, h) => `__LINK__${t}|${h}__LINK__`)

      const tokens = rest.split(/(__STRONG__.+?__STRONG__|__CODE__.+?__CODE__|__LINK__.+?__LINK__)/)
      for (let j = 0; j < tokens.length; j++) {
        const tok = tokens[j]
        if (tok.startsWith('__STRONG__')) {
          const Str = (overrides.strong as React.ElementType) || 'strong'
          parts.push(<Str key={j}>{tok.slice(10, -10)}</Str>)
        } else if (tok.startsWith('__CODE__')) {
          const Cd = (overrides.code as React.ElementType) || 'code'
          parts.push(<Cd key={j}>{tok.slice(8, -8)}</Cd>)
        } else if (tok.startsWith('__LINK__')) {
          const [text, href] = tok.slice(8, -8).split('|')
          const A = (overrides.a as React.ElementType) || 'a'
          parts.push(<A key={j} href={href} target="_blank" rel="noopener noreferrer">{text}</A>)
        } else if (tok) {
          parts.push(tok)
        }
      }
      elements.push(<P key={i}>{parts}</P>)
    }
  }

  return <>{elements}</>
}

export default ReactMarkdown
