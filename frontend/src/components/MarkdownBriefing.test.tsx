import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import MarkdownBriefing from "./MarkdownBriefing";

// ---------------------------------------------------------------------------
// Headings
// ---------------------------------------------------------------------------

describe("MarkdownBriefing — headings", () => {
  it("renders h1", () => {
    render(<MarkdownBriefing content="# Morning Briefing" />);
    expect(screen.getByRole("heading", { level: 1, name: "Morning Briefing" })).toBeInTheDocument();
  });

  it("renders h2", () => {
    render(<MarkdownBriefing content="## Critical Exceptions" />);
    expect(screen.getByRole("heading", { level: 2, name: /Critical Exceptions/ })).toBeInTheDocument();
  });

  it("renders h3", () => {
    render(<MarkdownBriefing content="### Vendor Patterns" />);
    expect(screen.getByRole("heading", { level: 3, name: /Vendor Patterns/ })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Inline formatting
// ---------------------------------------------------------------------------

describe("MarkdownBriefing — inline formatting", () => {
  it("renders bold text as <strong>", () => {
    const { container } = render(<MarkdownBriefing content="**CRITICAL** item" />);
    expect(container.querySelector("strong")).toHaveTextContent("CRITICAL");
  });

  it("renders inline code as <code>", () => {
    const { container } = render(<MarkdownBriefing content="Use `VND-400` for lookup" />);
    expect(container.querySelector("code")).toHaveTextContent("VND-400");
  });

  it("renders plain paragraph text", () => {
    render(<MarkdownBriefing content="Hello world" />);
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Lists
// ---------------------------------------------------------------------------

describe("MarkdownBriefing — lists", () => {
  it("renders unordered list items", () => {
    render(<MarkdownBriefing content={"- Alpha\n- Beta\n- Gamma"} />);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Gamma")).toBeInTheDocument();
  });

  it("renders all three items for a 3-item list", () => {
    const { container } = render(
      <MarkdownBriefing content={"- Item one\n- Item two\n- Item three"} />
    );
    // Each li has a bullet span + content span; count li elements
    expect(container.querySelectorAll("li").length).toBeGreaterThanOrEqual(3);
  });
});

// ---------------------------------------------------------------------------
// Block elements
// ---------------------------------------------------------------------------

describe("MarkdownBriefing — block elements", () => {
  it("renders blockquote", () => {
    const { container } = render(<MarkdownBriefing content="> Executive summary" />);
    expect(container.querySelector("blockquote")).toBeInTheDocument();
    expect(screen.getByText("Executive summary")).toBeInTheDocument();
  });

  it("renders horizontal rule", () => {
    const { container } = render(<MarkdownBriefing content={"A\n\n---\n\nB"} />);
    expect(container.querySelector("hr")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// GFM tables
// ---------------------------------------------------------------------------

describe("MarkdownBriefing — GFM tables", () => {
  const tableContent = `
| Priority | Count |
|---|---|
| CRITICAL | 3 |
| HIGH | 7 |
`;

  it("renders a <table> element", () => {
    render(<MarkdownBriefing content={tableContent} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("renders column headers", () => {
    render(<MarkdownBriefing content={tableContent} />);
    expect(screen.getByText("Priority")).toBeInTheDocument();
    expect(screen.getByText("Count")).toBeInTheDocument();
  });

  it("renders data cells", () => {
    render(<MarkdownBriefing content={tableContent} />);
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("renders the correct number of rows (header + 2 data rows)", () => {
    const { container } = render(<MarkdownBriefing content={tableContent} />);
    expect(container.querySelectorAll("tr").length).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// Links
// ---------------------------------------------------------------------------

describe("MarkdownBriefing — links", () => {
  it("renders link with correct href", () => {
    render(<MarkdownBriefing content="[Dashboard](http://localhost:3000)" />);
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "href",
      "http://localhost:3000"
    );
  });

  it("renders link with target=_blank for external safety", () => {
    render(<MarkdownBriefing content="[Dashboard](http://localhost:3000)" />);
    expect(screen.getByRole("link")).toHaveAttribute("target", "_blank");
  });

  it("renders link with rel=noopener noreferrer", () => {
    render(<MarkdownBriefing content="[Dashboard](http://localhost:3000)" />);
    expect(screen.getByRole("link")).toHaveAttribute("rel", "noopener noreferrer");
  });
});

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

describe("MarkdownBriefing — edge cases", () => {
  it("renders without crashing on empty string", () => {
    expect(() => render(<MarkdownBriefing content="" />)).not.toThrow();
  });

  it("renders without crashing on whitespace-only content", () => {
    expect(() => render(<MarkdownBriefing content="   " />)).not.toThrow();
  });

  it("handles multiple sections without crashing", () => {
    const multiSection = [
      "# Title",
      "",
      "> Callout",
      "",
      "## Section",
      "",
      "- A",
      "- B",
      "",
      "---",
      "",
      "Footer text",
    ].join("\n");
    expect(() => render(<MarkdownBriefing content={multiSection} />)).not.toThrow();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Realistic full-briefing integration test
// ---------------------------------------------------------------------------

describe("MarkdownBriefing — realistic briefing", () => {
  const briefing = `
# 📋 Morning Briefing — 2026-04-21

> **3 CRITICAL exceptions** require immediate attention. Estimated $42,000 at risk.

## 🚨 Critical Exceptions

| Exception | Store | Est. Lost Sales |
|---|---|---|
| OOS – Organic Oat Milk | STR-001 (Tier 1, LA) | $28,000 |
| OOS – Premium Coffee | STR-003 (Tier 1, NYC) | $14,000 |

## ⚠️ Vendor Pattern Alert

**VND-400 (CleanHome Distributors)** showing systemic deterioration:
- 14 exceptions across 8 stores
- Fill rate: 72% (below 85% threshold)
- Recommend escalation to supply chain manager

---

*Generated by Exception Copilot AI*
`;

  it("renders the h1 title", () => {
    render(<MarkdownBriefing content={briefing} />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("renders the GFM table", () => {
    render(<MarkdownBriefing content={briefing} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("renders vendor pattern text", () => {
    render(<MarkdownBriefing content={briefing} />);
    expect(screen.getByText(/VND-400/)).toBeInTheDocument();
  });

  it("renders the blockquote callout", () => {
    const { container } = render(<MarkdownBriefing content={briefing} />);
    expect(container.querySelector("blockquote")).toBeInTheDocument();
  });

  it("renders the hr divider", () => {
    const { container } = render(<MarkdownBriefing content={briefing} />);
    expect(container.querySelector("hr")).toBeInTheDocument();
  });
});
