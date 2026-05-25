# Vendored JavaScript libraries

All files in this directory are verbatim copies of upstream releases, kept
under their original permissive licenses. Update them via the same `curl`
command shown below.

## marked.min.js

- **Source**: <https://github.com/markedjs/marked>
- **Version**: 12.0.2
- **License**: MIT (Copyright © 2011–2024 Christopher Jeffrey)
- **Vendored**: 2026-05-20
- **Refresh**:
  ```sh
  curl -sSL https://cdn.jsdelivr.net/npm/marked@12/marked.min.js \
       -o marked.min.js
  ```

## purify.min.js (DOMPurify)

- **Source**: <https://github.com/cure53/DOMPurify>
- **Version**: 3.4.5
- **License**: Apache License 2.0 OR Mozilla Public License 2.0 (dual license; we use under Apache 2.0)
- **Vendored**: 2026-05-20
- **Refresh**:
  ```sh
  curl -sSL https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js \
       -o purify.min.js
  ```

## Why these two

`marked` parses Markdown to HTML. `DOMPurify` strips any unsafe HTML before
insertion into the DOM (defensive — Markdown can contain raw HTML which could
otherwise leak XSS from foreign repositories scanned via workspace federation).
