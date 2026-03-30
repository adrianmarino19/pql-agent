#!/usr/bin/env python3
"""Build a browsable HTML view and CSV index from scraped PQL docs JSONL."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/scrape/pql_docs.jsonl"),
        help="Source JSONL (one JSON object per line)",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=Path("data/scrape/pql_docs_index.csv"),
        help="Metadata-only CSV (no full body text)",
    )
    parser.add_argument(
        "--html-out",
        type=Path,
        default=Path("data/scrape/pql_docs_browser.html"),
        help="Single-file searchable browser",
    )
    args = parser.parse_args()

    rows: list[dict] = []
    with args.input.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    fieldnames = [
        "position",
        "title",
        "url",
        "source",
        "status_code",
        "word_count",
        "fetched_at_utc",
        "content_hash_sha256",
        "error",
    ]
    args.csv_out.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    html = _HTML_TEMPLATE.replace(
        "__DOCS_JSON__",
        json.dumps(rows, ensure_ascii=False),
    )
    args.html_out.write_text(html, encoding="utf-8")
    print(f"Wrote {len(rows)} rows -> {args.csv_out}")
    print(f"Wrote {args.html_out}")


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PQL docs (scraped)</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a2332;
      --text: #e7ecf3;
      --muted: #8b9cb3;
      --accent: #5eb3f6;
      --border: #2a3544;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      min-height: 100vh;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(15, 20, 25, 0.92);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
      padding: 1rem 1.25rem;
    }
    h1 {
      margin: 0 0 0.5rem;
      font-size: 1.15rem;
      font-weight: 600;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      align-items: center;
    }
    #q {
      flex: 1;
      min-width: 200px;
      padding: 0.5rem 0.75rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--panel);
      color: var(--text);
      font-size: 1rem;
    }
    #q::placeholder { color: var(--muted); }
    .meta { font-size: 0.85rem; color: var(--muted); }
    main {
      display: grid;
      grid-template-columns: minmax(260px, 340px) 1fr;
      gap: 0;
      min-height: calc(100vh - 120px);
    }
    @media (max-width: 800px) {
      main { grid-template-columns: 1fr; }
      #list { max-height: 40vh; border-right: none; border-bottom: 1px solid var(--border); }
    }
    #list {
      overflow: auto;
      border-right: 1px solid var(--border);
      padding: 0.5rem 0;
    }
    .item {
      padding: 0.65rem 1rem;
      cursor: pointer;
      border-left: 3px solid transparent;
    }
    .item:hover { background: rgba(94, 179, 246, 0.08); }
    .item.active {
      background: rgba(94, 179, 246, 0.12);
      border-left-color: var(--accent);
    }
    .item-title { font-weight: 500; font-size: 0.95rem; }
    .item-sub { font-size: 0.75rem; color: var(--muted); margin-top: 0.2rem; }
    #detail {
      overflow: auto;
      padding: 1rem 1.25rem 2rem;
    }
    #detail h2 { margin-top: 0; font-size: 1.1rem; }
    #detail a { color: var(--accent); }
    #detail .content {
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 0.9rem;
      line-height: 1.55;
      color: #d0dae8;
    }
    .empty { color: var(--muted); padding: 2rem; }
  </style>
</head>
<body>
  <header>
    <h1>PQL docs (local scrape)</h1>
    <div class="toolbar">
      <input type="search" id="q" placeholder="Filter by title, URL, or body text…" autocomplete="off" />
      <span class="meta" id="count"></span>
    </div>
  </header>
  <main>
    <nav id="list" aria-label="Documents"></nav>
    <article id="detail">
      <p class="empty">Select a document from the list.</p>
    </article>
  </main>
  <script type="application/json" id="docs-data">__DOCS_JSON__</script>
  <script>
    const docs = JSON.parse(document.getElementById('docs-data').textContent);
    const listEl = document.getElementById('list');
    const detailEl = document.getElementById('detail');
    const qEl = document.getElementById('q');
    const countEl = document.getElementById('count');

    let filtered = [...docs];
    let activeIndex = -1;

    function norm(s) {
      return (s || '').toLowerCase();
    }

    function applyFilter() {
      const q = norm(qEl.value.trim());
      if (!q) {
        filtered = [...docs];
      } else {
        filtered = docs.filter((d) => {
          const hay = norm(d.title) + ' ' + norm(d.url) + ' ' + norm(d.full_content);
          return hay.includes(q);
        });
      }
      activeIndex = filtered.length ? 0 : -1;
      renderList();
      countEl.textContent = filtered.length + ' / ' + docs.length + ' pages';
      if (activeIndex >= 0) selectDoc(0);
      else showEmpty('No matches.');
    }

    function renderList() {
      listEl.innerHTML = '';
      filtered.forEach((d, i) => {
        const div = document.createElement('div');
        div.className = 'item' + (i === activeIndex ? ' active' : '');
        div.dataset.idx = String(i);
        div.innerHTML =
          '<div class="item-title"></div><div class="item-sub"></div>';
        div.querySelector('.item-title').textContent = d.title || '(no title)';
        div.querySelector('.item-sub').textContent = d.url || '';
        div.addEventListener('click', () => selectDoc(i));
        listEl.appendChild(div);
      });
    }

    function showEmpty(msg) {
      detailEl.innerHTML = '<p class="empty">' + msg + '</p>';
    }

    function selectDoc(i) {
      activeIndex = i;
      const d = filtered[i];
      if (!d) {
        showEmpty('Select a document from the list.');
        return;
      }
      [...listEl.querySelectorAll('.item')].forEach((el, j) => {
        el.classList.toggle('active', j === i);
      });
      detailEl.innerHTML =
        '<h2></h2>' +
        '<p><a href="" target="_blank" rel="noopener">Open original</a> · ' +
        (d.word_count != null ? d.word_count + ' words' : '') +
        (d.fetched_at_utc ? ' · ' + d.fetched_at_utc : '') +
        '</p>' +
        '<div class="content"></div>';
      detailEl.querySelector('h2').textContent = d.title || '(no title)';
      const a = detailEl.querySelector('a');
      a.href = d.url || '#';
      detailEl.querySelector('.content').textContent = d.full_content || '';
    }

    qEl.addEventListener('input', applyFilter);
    countEl.textContent = docs.length + ' / ' + docs.length + ' pages';
    applyFilter();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
