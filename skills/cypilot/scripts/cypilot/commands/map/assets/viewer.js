/* cfc map viewer — vis-network frontend
 *
 * Reads window.MAP_DATA (JSON payload from render_json).
 * Option B (minimal first iteration): full markdown preview and
 * tab-based UI deferred; core graph + inspector + sidebar implemented.
 */
(function () {
  "use strict";

  /* ── Constants ─────────────────────────────────────────────── */
  const EDGE_COLORS = {
    "cpt-doc":   { color: "#4060c0", highlight: "#6080e0", hover: "#6080e0" },
    "cpt-impl":  { color: "#20a060", highlight: "#40c080", hover: "#40c080" },
    "file-link": { color: "#888888", highlight: "#aaaaaa", hover: "#aaaaaa" },
    _dangling:   { color: "#c41212", highlight: "#e04040", hover: "#e04040" },
  };

  const NODE_SOURCE_STYLE = {
    color: { background: "#fff5e6", border: "#c07000", highlight: { background: "#ffe0b0", border: "#c07000" } },
    font: { face: "monospace", size: 12 },
    shape: "box",
  };

  const NODE_PHANTOM_STYLE = {
    color: { background: "#ffeaea", border: "#c41212", highlight: { background: "#ffd0d0", border: "#c41212" } },
    font: { color: "#c41212", size: 12 },
    shape: "diamond",
  };

  /* ── Bootstrap ──────────────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", function () {
    const data = window.MAP_DATA;
    if (!data) {
      document.getElementById("graph").textContent = "ERROR: window.MAP_DATA not found.";
      return;
    }
    buildSidebar(data);
    const network = buildGraph(data);
    buildSearch(data, network);
  });

  /* ── Sidebar ─────────────────────────────────────────────────── */
  function buildSidebar(data) {
    const sidebar = document.getElementById("sidebar");

    /* Logo / title */
    const logo = el("div", { className: "logo" }, "cfc map");
    sidebar.appendChild(logo);

    /* Workspace info */
    const ws = data.workspace || {};
    const wsSect = section("Workspace");
    if (ws.primary) wsSect.appendChild(statRow(ws.primary, null));
    sidebar.appendChild(wsSect);

    /* Node counters */
    const nodeKinds = { markdown: 0, source: 0, "phantom-cpt": 0 };
    (data.nodes || []).forEach(function (n) {
      if (n.kind in nodeKinds) nodeKinds[n.kind]++;
    });
    const nodeSect = section("Nodes  (" + (data.nodes || []).length + ")");
    nodeSect.appendChild(statRow("markdown",    nodeKinds.markdown));
    nodeSect.appendChild(statRow("source",      nodeKinds.source));
    nodeSect.appendChild(statRow("phantom-cpt", nodeKinds["phantom-cpt"]));
    sidebar.appendChild(nodeSect);

    /* Edge counters */
    const edgeTypes = { "cpt-doc": 0, "cpt-impl": 0, "file-link": 0 };
    let danglingCount = 0;
    (data.edges || []).forEach(function (e) {
      if (e.type in edgeTypes) edgeTypes[e.type]++;
      if (e.dangling) danglingCount++;
    });
    const edgeSect = section("Edges  (" + (data.edges || []).length + ")");
    edgeSect.appendChild(statRow("cpt-doc",   edgeTypes["cpt-doc"]));
    edgeSect.appendChild(statRow("cpt-impl",  edgeTypes["cpt-impl"]));
    edgeSect.appendChild(statRow("file-link", edgeTypes["file-link"]));
    sidebar.appendChild(edgeSect);

    /* Dangling row — clickable */
    if (danglingCount > 0) {
      const dangSect = section("Issues");
      const row = statRow(danglingCount + " dangling cpt-ID(s)", danglingCount);
      row.classList.add("danger", "clickable");
      row.title = "Click to focus first phantom node";
      row.addEventListener("click", function () {
        focusFirstPhantom(data);
      });
      dangSect.appendChild(row);
      sidebar.appendChild(dangSect);
    }

    /* Category breakdown */
    if (data.categories && Object.keys(data.categories).length > 0) {
      const catSect = section("Categories");
      Object.keys(data.categories).sort().forEach(function (cat) {
        const info = data.categories[cat];
        catSect.appendChild(statRow(cat, info.node_count));
      });
      sidebar.appendChild(catSect);
    }

    /* Legend */
    sidebar.appendChild(buildLegend());
  }

  function section(title) {
    const wrap = el("div", { className: "stat-group" });
    wrap.appendChild(el("h2", {}, title));
    return wrap;
  }

  function statRow(label, count) {
    const row = el("div", { className: "stat-row" });
    row.appendChild(el("span", { className: "label", title: label }, label));
    if (count !== null) {
      row.appendChild(el("span", { className: "count" }, String(count)));
    }
    return row;
  }

  function buildLegend() {
    const wrap = section("Legend");
    [
      ["cpt-doc edge",   "edge-cpt-doc"],
      ["cpt-impl edge",  "edge-cpt-impl"],
      ["file-link edge", "edge-file-link"],
      ["dangling edge",  "edge-dangling"],
    ].forEach(function (pair) {
      const row = el("div", { className: "stat-row" });
      const token = el("span", { className: "edge-token " + pair[1] });
      const lbl = el("span", { className: "label" }, pair[0]);
      row.appendChild(token);
      row.appendChild(lbl);
      wrap.appendChild(row);
    });
    return wrap;
  }

  /* ── Graph ───────────────────────────────────────────────────── */
  function buildGraph(data) {
    const primary = (data.workspace || {}).primary || "";

    /* Nodes */
    const visNodes = (data.nodes || []).map(function (n) {
      return makeVisNode(n, primary, data.categories || {});
    });

    /* Edges */
    const visEdges = (data.edges || []).map(function (e) {
      return makeVisEdge(e);
    });

    const nodesDS = new vis.DataSet(visNodes);
    const edgesDS = new vis.DataSet(visEdges);

    const container = document.getElementById("graph");
    const network = new vis.Network(container, { nodes: nodesDS, edges: edgesDS }, {
      layout: { improvedLayout: true },
      physics: {
        enabled: true,
        barnesHut: { gravitationalConstant: -4000, springLength: 120, springConstant: 0.04 },
        stabilization: { iterations: 200 },
      },
      interaction: {
        tooltipDelay: 300,
        hideEdgesOnDrag: true,
      },
      edges: {
        smooth: { type: "dynamic" },
        arrows: { to: { enabled: true, scaleFactor: 0.7 } },
        font: { size: 10, color: "#666", align: "middle" },
      },
      nodes: {
        borderWidth: 1.5,
        font: { size: 12 },
      },
    });

    /* Click handlers */
    network.on("click", function (params) {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const node = findById(data.nodes, nodeId);
        if (node) showNodeInspector(node, data, primary);
      } else if (params.edges.length > 0) {
        const edgeId = params.edges[0];
        const edge = findById(data.edges, edgeId);
        if (edge) showEdgeInspector(edge, data);
      } else {
        closeInspector();
      }
    });

    /* Store reference for search */
    window._cfcNetwork = network;
    window._cfcNodesDS = nodesDS;
    return network;
  }

  function makeVisNode(n, primary, categories) {
    let label = n.rel_path || n.id;
    if (n.kind !== "phantom-cpt" && n.source && n.source !== primary) {
      label = "[" + n.source + "] " + (n.rel_path || n.id);
    }

    if (n.kind === "phantom-cpt") {
      const raw = n.id.replace(/^phantom:/, "");
      return Object.assign({}, NODE_PHANTOM_STYLE, {
        id: n.id,
        label: "⚠ " + raw,
        title: "Undefined cpt-ID: " + raw,
        group: "phantom-cpt",
      });
    }

    if (n.kind === "source") {
      return Object.assign({}, NODE_SOURCE_STYLE, {
        id: n.id,
        label: label,
        title: n.id,
        group: "source",
      });
    }

    /* markdown */
    const style = (categories[n.category] || {}).style || {};
    return {
      id: n.id,
      label: label,
      title: n.id,
      shape: "box",
      color: {
        background: style.background || "#e8eaff",
        border: style.color || "#4060c0",
        highlight: { background: style.background || "#d0d4ff", border: style.color || "#2040a0" },
      },
      font: { size: 12 },
      group: "markdown",
    };
  }

  function makeVisEdge(e) {
    const isD = e.dangling === true;
    const palette = isD ? EDGE_COLORS._dangling : (EDGE_COLORS[e.type] || EDGE_COLORS["file-link"]);
    return {
      id: e.id,
      from: e.from,
      to: e.to,
      color: palette,
      width: isD ? 2 : (e.type === "file-link" ? 1 : 1.5),
      dashes: isD,
      title: e.type + (isD ? " (dangling)" : "") + (e.cross_repo ? " [cross-repo]" : ""),
      label: e.type === "file-link" ? "" : e.type,
    };
  }

  /* ── Inspector ───────────────────────────────────────────────── */
  function showNodeInspector(node, data, primary) {
    const insp = document.getElementById("inspector");
    insp.innerHTML = "";

    /* Header */
    const header = el("div", { id: "inspector-header" });
    const badge = el("span", { className: "kind-badge " + node.kind }, node.kind);
    const closeBtn = el("button", { id: "inspector-close", title: "Close" }, "×");
    closeBtn.addEventListener("click", closeInspector);
    header.appendChild(badge);
    header.appendChild(closeBtn);
    insp.appendChild(header);

    const body = el("div", { id: "inspector-body" });

    /* ID */
    body.appendChild(fieldHeading("Identity"));
    body.appendChild(field("ID", code(node.id)));
    if (node.rel_path) body.appendChild(field("Path", node.rel_path));
    if (node.source)   body.appendChild(field("Source", node.source));
    if (node.language) body.appendChild(field("Language", node.language));
    body.appendChild(field("Category", node.category + " (" + node.category_origin + ")"));
    body.appendChild(field("LOC", String(node.loc || 0)));

    /* cpt definitions */
    if (node.cpt_defs && node.cpt_defs.length > 0) {
      body.appendChild(fieldHeading("cpt-IDs defined (" + node.cpt_defs.length + ")"));
      node.cpt_defs.forEach(function (d) {
        body.appendChild(el("p", {}, code(d)));
      });
    }

    /* cpt uses */
    if (node.cpt_uses && node.cpt_uses.length > 0) {
      body.appendChild(fieldHeading("cpt-IDs used (" + node.cpt_uses.length + ")"));
      node.cpt_uses.slice(0, 20).forEach(function (u) {
        const card = el("div", { className: "ref-card" });
        card.appendChild(el("div", { className: "cpt-id" }, u.cpt_id));
        card.appendChild(el("div", {}, el("span", {}, "line " + u.line + " — ")));
        card.appendChild(el("div", { className: "snippet" }, u.snippet || ""));
        body.appendChild(card);
      });
      if (node.cpt_uses.length > 20) {
        body.appendChild(el("p", {}, "… and " + (node.cpt_uses.length - 20) + " more."));
      }
    }

    /* Content */
    body.appendChild(fieldHeading("Content"));
    if (node.content) {
      const cb = el("div", { className: "content-block" }, node.content.slice(0, 4000));
      body.appendChild(cb);
      if (node.content.length > 4000) {
        body.appendChild(el("p", {}, "(truncated to 4000 chars)"));
      }
    } else {
      body.appendChild(el("p", {}, "(content not embedded)"));
    }

    insp.appendChild(body);
    insp.classList.add("open");
  }

  function showEdgeInspector(edge, data) {
    const insp = document.getElementById("inspector");
    insp.innerHTML = "";

    const header = el("div", { id: "inspector-header" });
    const badge = el("span", { className: "kind-badge edge" }, edge.type);
    const closeBtn = el("button", { id: "inspector-close", title: "Close" }, "×");
    closeBtn.addEventListener("click", closeInspector);
    header.appendChild(badge);
    header.appendChild(closeBtn);
    insp.appendChild(header);

    const body = el("div", { id: "inspector-body" });

    body.appendChild(fieldHeading("Edge"));
    body.appendChild(field("Type", edge.type + (edge.dangling ? " (dangling)" : "") + (edge.cross_repo ? " [cross-repo]" : "")));
    body.appendChild(field("From", code(edge.from)));
    body.appendChild(field("To",   code(edge.to)));

    if (edge.refs && edge.refs.length > 0) {
      body.appendChild(fieldHeading("References (" + edge.refs.length + ")"));
      edge.refs.forEach(function (r, i) {
        const card = el("div", { className: "ref-card" });
        if (r.cpt_id) card.appendChild(el("div", { className: "cpt-id" }, r.cpt_id));
        card.appendChild(el("div", {}, "line " + r.line));
        if (r.snippet) card.appendChild(el("div", { className: "snippet" }, r.snippet));
        if (r.def_line != null) {
          card.appendChild(el("div", {}, "defined at line " + r.def_line));
        }
        if (r.def_snippet) card.appendChild(el("div", { className: "snippet" }, r.def_snippet));
        body.appendChild(card);
      });
    }

    insp.appendChild(body);
    insp.classList.add("open");
  }

  function closeInspector() {
    const insp = document.getElementById("inspector");
    insp.classList.remove("open");
  }

  /* ── Search ──────────────────────────────────────────────────── */
  function buildSearch(data, network) {
    const sidebar = document.getElementById("sidebar");
    const wrap = el("div", { id: "search-wrap" });
    wrap.appendChild(el("h2", {}, "Search cpt-ID / path"));

    const input = el("input", {
      id: "search-input",
      type: "text",
      placeholder: "e.g. cpt-myfeature-foo",
    });
    const results = el("div", { id: "search-results" });

    /* Build index: cpt_id -> [node_id] and path fragment -> [node_id] */
    const cptIndex = {};  /* cpt_id -> Set<node_id> */
    const pathIndex = []; /* {text, id} for fuzzy scan */

    (data.nodes || []).forEach(function (n) {
      if (n.rel_path) pathIndex.push({ text: n.rel_path.toLowerCase(), id: n.id });
      (n.cpt_defs || []).forEach(function (d) {
        if (!cptIndex[d]) cptIndex[d] = new Set();
        cptIndex[d].add(n.id);
      });
      (n.cpt_uses || []).forEach(function (u) {
        if (!cptIndex[u.cpt_id]) cptIndex[u.cpt_id] = new Set();
        cptIndex[u.cpt_id].add(n.id);
      });
    });

    input.addEventListener("input", function () {
      const q = input.value.trim().toLowerCase();
      if (!q) {
        results.textContent = "";
        resetHighlight(network, data);
        return;
      }

      /* Find matching node IDs */
      const matched = new Set();

      /* exact / prefix match in cpt index */
      Object.keys(cptIndex).forEach(function (cptId) {
        if (cptId.toLowerCase().indexOf(q) !== -1) {
          cptIndex[cptId].forEach(function (nid) { matched.add(nid); });
        }
      });

      /* path substring match */
      pathIndex.forEach(function (entry) {
        if (entry.text.indexOf(q) !== -1) matched.add(entry.id);
      });

      /* direct node id match */
      (data.nodes || []).forEach(function (n) {
        if (n.id.toLowerCase().indexOf(q) !== -1) matched.add(n.id);
      });

      if (matched.size === 0) {
        results.textContent = "No matches.";
        resetHighlight(network, data);
      } else {
        results.textContent = matched.size + " match(es)";
        highlightNodes(network, matched);
        if (matched.size === 1) {
          network.focus(Array.from(matched)[0], { scale: 1.2, animation: true });
        }
      }
    });

    wrap.appendChild(input);
    wrap.appendChild(results);
    sidebar.insertBefore(wrap, sidebar.children[1] || null);
  }

  function highlightNodes(network, matchedIds) {
    network.selectNodes(Array.from(matchedIds));
  }

  function resetHighlight(network) {
    network.selectNodes([]);
  }

  /* ── Focus first phantom ─────────────────────────────────────── */
  function focusFirstPhantom(data) {
    const network = window._cfcNetwork;
    if (!network) return;
    const phantom = (data.nodes || []).find(function (n) { return n.kind === "phantom-cpt"; });
    if (phantom) {
      network.focus(phantom.id, { scale: 1.5, animation: { duration: 600, easingFunction: "easeInOutQuad" } });
      network.selectNodes([phantom.id]);
    }
  }

  /* ── Helpers ─────────────────────────────────────────────────── */
  function el(tag, attrs, content) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "className") {
          node.className = attrs[k];
        } else {
          node[k] = attrs[k];
        }
      });
    }
    if (content !== undefined && content !== null) {
      if (typeof content === "string") {
        node.textContent = content;
      } else {
        node.appendChild(content);
      }
    }
    return node;
  }

  function code(text) {
    return el("code", {}, text);
  }

  function fieldHeading(text) {
    return el("h3", {}, text);
  }

  function field(label, valueNode) {
    const p = document.createElement("p");
    const lbl = el("span", { className: "field-label" }, label + ": ");
    p.appendChild(lbl);
    if (typeof valueNode === "string") {
      p.appendChild(document.createTextNode(valueNode));
    } else {
      p.appendChild(valueNode);
    }
    return p;
  }

  function findById(arr, id) {
    return (arr || []).find(function (x) { return x.id === id; }) || null;
  }

})();
