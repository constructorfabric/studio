/* cfc map viewer — vis-network frontend
 *
 * Reads window.MAP_DATA (JSON payload from render_json).
 * Option B (minimal first iteration): full markdown preview and
 * tab-based UI deferred; core graph + inspector + sidebar implemented.
 *
 * Layout strategy: when data.layout.vis_nodes is non-empty (produced by
 * layout.py), node positions are pre-computed and pinned (x/y/fixed).
 * Physics is disabled and category bands are drawn via network.on("afterDrawing").
 * If vis_nodes is absent or empty, physics fallback is used with a console warning.
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

  /* ── Focus state ────────────────────────────────────────────── */
  // activeDepth: how many hops from the selected focus node(s) to show edges
  let activeDepth = 1;
  // currentFocusIds: Set of node IDs that are the current focus (null = no focus)
  let currentFocusIds = null;
  // allEdgesData: flat array of all edge objects from data.edges — set in buildGraph
  let allEdgesData = [];

  // Edge-type filters. When true → all edges of that type are visible everywhere
  // (independent of focus). When false → that type is hidden unless caught by
  // an active focus's depth-N BFS. Defaults: all off, matching the
  // "no edges visible until something is selected" behaviour.
  const enabledEdgeTypes = {
    "cpt-doc": false,
    "cpt-impl": false,
    "file-link": false,
  };

  // Node-kind filters. When true → that kind is shown; when false → hidden,
  // and edges with a hidden endpoint are also hidden. Defaults: all on.
  const enabledNodeKinds = {
    "markdown": true,
    "source": true,
    "phantom-cpt": true,
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
    wireToolbar();
  });

  /* ── Sidebar ─────────────────────────────────────────────────── */
  function buildSidebar(data) {
    const sidebar = document.getElementById("sidebar");

    /* Logo / title */
    const logo = el("div", { className: "logo" }, "cfc map");
    sidebar.appendChild(logo);

    /* Depth control */
    const depthWrap = el("div", { className: "depth-control" });
    const depthLabel = document.createElement("label");
    depthLabel.textContent = "Depth: ";
    const depthInput = el("input", {
      id: "depth-input",
      type: "number",
    });
    depthInput.setAttribute("min", "0");
    depthInput.setAttribute("max", "5");
    depthInput.setAttribute("value", "1");
    depthLabel.appendChild(depthInput);
    depthWrap.appendChild(depthLabel);
    depthWrap.appendChild(el("small", {}, "0 = focus only; ≥1 includes N hops"));
    sidebar.appendChild(depthWrap);

    function onDepthChange() {
      let v = parseInt(depthInput.value, 10);
      if (isNaN(v)) v = 1;
      if (v < 0) v = 0;
      if (v > 5) v = 5;
      depthInput.value = v;
      activeDepth = v;
      if (currentFocusIds !== null) {
        applyFocus(currentFocusIds);
      }
    }
    depthInput.addEventListener("change", onDepthChange);
    depthInput.addEventListener("input", onDepthChange);

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
    const nodeHint = el("div", { className: "stat-hint" }, "click to toggle visibility");
    nodeSect.appendChild(nodeHint);
    ["markdown", "source", "phantom-cpt"].forEach(function (kind) {
      const row = statRow(kind, nodeKinds[kind]);
      row.classList.add("clickable", "node-toggle", "node-toggle-" + kind);
      if (enabledNodeKinds[kind]) row.classList.add("active");
      row.title = "Show/hide all " + kind + " nodes";
      row.addEventListener("click", function () {
        enabledNodeKinds[kind] = !enabledNodeKinds[kind];
        row.classList.toggle("active", enabledNodeKinds[kind]);
        recomputeNodeVisibility();
        recomputeEdgeVisibility();
      });
      nodeSect.appendChild(row);
    });
    sidebar.appendChild(nodeSect);

    /* Edge counters */
    const edgeTypes = { "cpt-doc": 0, "cpt-impl": 0, "file-link": 0 };
    let danglingCount = 0;
    (data.edges || []).forEach(function (e) {
      if (e.type in edgeTypes) edgeTypes[e.type]++;
      if (e.dangling) danglingCount++;
    });
    const edgeSect = section("Edges  (" + (data.edges || []).length + ")");
    const edgeHint = el("div", { className: "stat-hint" }, "click to toggle visibility");
    edgeSect.appendChild(edgeHint);
    ["cpt-doc", "cpt-impl", "file-link"].forEach(function (type) {
      const row = statRow(type, edgeTypes[type]);
      row.classList.add("clickable", "edge-toggle", "edge-toggle-" + type);
      // initial visual state (off)
      if (enabledEdgeTypes[type]) row.classList.add("active");
      row.title = "Show/hide all " + type + " edges";
      row.addEventListener("click", function () {
        enabledEdgeTypes[type] = !enabledEdgeTypes[type];
        row.classList.toggle("active", enabledEdgeTypes[type]);
        recomputeEdgeVisibility();
      });
      edgeSect.appendChild(row);
    });
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

    /* Category breakdown — clickable rows that select & zoom to category nodes */
    if (data.categories && Object.keys(data.categories).length > 0) {
      const catSect = section("Categories");
      // Build a per-category node ID lookup (filled once network is built).
      // We attach a click handler that defers to window._cfcNetwork.
      let activeCatRow = null;
      Object.keys(data.categories).sort().forEach(function (cat) {
        const info = data.categories[cat];
        const row = statRow(cat, info.node_count);
        row.classList.add("clickable");
        row.title = "Click to focus " + cat + " nodes";
        row.addEventListener("click", function () {
          const network = window._cfcNetwork;
          if (!network) return;

          const idsInCat = (data.nodes || [])
            .filter(function (n) { return n.category === cat; })
            .map(function (n) { return n.id; });
          if (idsInCat.length === 0) return;

          // Toggle: clicking the active category row clears the focus
          if (activeCatRow === row && row.classList.contains("active")) {
            row.classList.remove("active");
            activeCatRow = null;
            clearFocus();
            return;
          }

          // Remove active from previous row
          if (activeCatRow && activeCatRow !== row) {
            activeCatRow.classList.remove("active");
          }
          row.classList.add("active");
          activeCatRow = row;

          setFocus(new Set(idsInCat));
          network.fit({ nodes: idsInCat, animation: { duration: 400, easingFunction: "easeInOutQuad" } });
        });
        catSect.appendChild(row);
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
    const layout = data.layout || {};
    const layoutVisNodes = layout.vis_nodes || [];
    const categoryBands = layout.category_bands || {};

    /* Build position lookup by id from layout data */
    const posById = {};
    layoutVisNodes.forEach(function (lv) {
      posById[lv.id] = lv;
    });
    const hasPositions = layoutVisNodes.length > 0;
    if (!hasPositions) {
      console.warn("cfc map: no pre-computed positions found — falling back to physics layout");
    }

    /* Nodes: merge layout positions into vis-network node objects */
    const visNodes = (data.nodes || []).map(function (n) {
      const vn = makeVisNode(n, primary, data.categories || {});
      if (hasPositions && posById[n.id]) {
        vn.x = posById[n.id].x;
        vn.y = posById[n.id].y;
        vn.fixed = { x: true, y: true };
      }
      return vn;
    });

    /* Expose node data before building edges so edgeLabel() can look up
     * file-link target rel_paths during makeVisEdge(). */
    window._cfcAllNodesData = data.nodes || [];

    /* Edges — hidden by default until a focus is set */
    allEdgesData = data.edges || [];
    const visEdges = allEdgesData.map(function (e) {
      return Object.assign(makeVisEdge(e), { hidden: true });
    });

    const nodesDS = new vis.DataSet(visNodes);
    const edgesDS = new vis.DataSet(visEdges);

    const container = document.getElementById("graph");

    /* Network options differ depending on whether we have pre-computed positions */
    const networkOptions = {
      layout: { improvedLayout: !hasPositions },
      physics: hasPositions
        ? { enabled: false }
        : {
            enabled: true,
            barnesHut: { gravitationalConstant: -4000, springLength: 120, springConstant: 0.04 },
            stabilization: { iterations: 200 },
          },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        dragNodes: !hasPositions,  // disable drag when positions are pinned
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
    };

    const network = new vis.Network(container, { nodes: nodesDS, edges: edgesDS }, networkOptions);

    /* Draw category bands as canvas overlays behind nodes.
     * We use afterDrawing because it fires after the canvas is cleared each frame,
     * letting us paint rectangles at absolute canvas coordinates. */
    if (hasPositions && Object.keys(categoryBands).length > 0) {
      /* beforeDrawing fires with the network transform already applied to ctx,
       * so we draw bands directly in graph coordinates — vis-network handles
       * pan/zoom for us. afterDrawing would paint on top of nodes; we want
       * bands behind. */
      network.on("beforeDrawing", function (ctx) {
        Object.keys(categoryBands).forEach(function (cat) {
          const band = categoryBands[cat];
          const stroke = band.title_color || "#4060c0";

          ctx.save();
          ctx.globalAlpha = 0.08;
          ctx.fillStyle = stroke;
          ctx.fillRect(band.x, band.y, band.w, band.h);
          ctx.restore();

          ctx.save();
          ctx.globalAlpha = 0.30;
          ctx.strokeStyle = stroke;
          ctx.lineWidth = 1.5;
          ctx.setLineDash([4, 4]);
          ctx.strokeRect(band.x, band.y, band.w, band.h);
          ctx.restore();

          ctx.save();
          ctx.globalAlpha = 0.85;
          ctx.fillStyle = stroke;
          ctx.font = "bold 14px sans-serif";
          ctx.fillText(band.label || cat, band.x + 8, band.y + 18);
          ctx.restore();
        });
      });
    }

    /* Click handlers */
    network.on("click", function (params) {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const node = findById(data.nodes, nodeId);
        if (node) showNodeInspector(node, data, primary);

        // Push canvas click into nav history too — but only if landing on a
        // different node than the current one.
        if (navCurrent && navCurrent !== nodeId) {
          navBack.push(navCurrent);
          navFwd.length = 0;
        }
        navCurrent = nodeId;
        refreshToolbarState();

        // Toggle focus: clicking the same focused single-node clears it
        if (currentFocusIds && currentFocusIds.size === 1 && currentFocusIds.has(nodeId)) {
          clearFocus();
        } else {
          setFocus(new Set([nodeId]));
        }
      } else if (params.edges.length > 0) {
        const edgeId = params.edges[0];
        const edge = findById(data.edges, edgeId);
        if (edge) showEdgeInspector(edge, data);
        // Keep the edge visible — no focus change
      } else {
        // Check if click landed inside a category band
        const canvasPos = params.pointer.canvas;
        const hitCat = hitTestCategoryBand(canvasPos, categoryBands);
        if (hitCat) {
          const idsInCat = (data.nodes || [])
            .filter(function (n) { return n.category === hitCat; })
            .map(function (n) { return n.id; });
          if (currentFocusIds && idsInCat.every(function (id) { return currentFocusIds.has(id); }) &&
              currentFocusIds.size === idsInCat.length) {
            // Same category band clicked again — clear focus
            clearFocus();
          } else {
            setFocus(new Set(idsInCat));
          }
        } else {
          // Empty canvas click — clear focus
          clearFocus();
          closeInspector();
        }
      }
    });

    /* Expose DS for applyFocus / clearFocus */
    window._cfcEdgesDS = edgesDS;
    window._cfcNodesDS = nodesDS;
    window._cfcAllNodeIds = visNodes.map(function (vn) { return vn.id; });
    window._cfcAllNodesData = data.nodes || [];

    /* Build cpt-ID indices once, exposed to inspector + search.
     *   _cfcCptDefiners[cpt_id] = Set<node_id>  (typically size 1)
     *   _cfcCptUsers[cpt_id]    = Set<node_id>  (consumers; excludes md-def entries) */
    const definers = {};
    const users = {};
    (data.nodes || []).forEach(function (n) {
      (n.cpt_defs || []).forEach(function (d) {
        if (!definers[d]) definers[d] = new Set();
        definers[d].add(n.id);
      });
      (n.cpt_uses || []).forEach(function (u) {
        if (u.marker_kind === "md-def") return;
        if (!users[u.cpt_id]) users[u.cpt_id] = new Set();
        users[u.cpt_id].add(n.id);
      });
    });
    window._cfcCptDefiners = definers;
    window._cfcCptUsers = users;

    /* Store reference for search and sidebar */
    window._cfcNetwork = network;
    return network;
  }

  function tooltipFor(n) {
    const lines = [
      "<b>" + (n.rel_path || n.id) + "</b>",
      "kind: " + n.kind,
      n.category ? "category: " + n.category : "",
      n.cpt_defs && n.cpt_defs.length ? "defs: " + n.cpt_defs.join(", ") : "",
    ];
    return lines.filter(Boolean).join("<br>");
  }

  function shortLabel(n) {
    /* filename only; cross-repo prefix is preserved as "[source] filename". */
    const rel = n.rel_path || "";
    const base = rel ? rel.split("/").pop() : n.id;
    if (n.kind !== "phantom-cpt" && n.source && n.source !== window.MAP_DATA.workspace.primary) {
      return "[" + n.source + "] " + base;
    }
    return base;
  }

  /* Hard cap on node visual width so labels do not blow up the grid layout. */
  const NODE_WIDTH = 60;
  const NODE_HEIGHT_MAX = 40;

  function makeVisNode(n, primary, categories) {
    const label = shortLabel(n);

    if (n.kind === "phantom-cpt") {
      const raw = n.id.replace(/^phantom:/, "");
      return Object.assign({}, NODE_PHANTOM_STYLE, {
        id: n.id,
        label: "⚠ " + raw.split(":")[0].replace(/^cpt-/, ""),
        title: tooltipFor(n),
        group: "phantom-cpt",
        widthConstraint: { maximum: NODE_WIDTH },
        heightConstraint: { maximum: NODE_HEIGHT_MAX },
        margin: 4,
        font: { color: "#c41212", size: 11 },
      });
    }

    if (n.kind === "source") {
      return Object.assign({}, NODE_SOURCE_STYLE, {
        id: n.id,
        label: label,
        title: tooltipFor(n),
        group: "source",
        widthConstraint: { maximum: NODE_WIDTH },
        heightConstraint: { maximum: NODE_HEIGHT_MAX },
        margin: 4,
        font: { face: "monospace", size: 11 },
      });
    }

    /* markdown */
    const style = (categories[n.category] || {}).style || {};
    return {
      id: n.id,
      label: label,
      title: tooltipFor(n),
      widthConstraint: { maximum: NODE_WIDTH },
      font: { size: 11 },
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
      label: edgeLabel(e),
      font: { size: 9, color: palette.color || "#666", align: "middle", background: "rgba(255,255,255,0.85)" },
    };
  }

  /* Edge label:
   *   file-link → basename of the target rel_path (target is markdown).
   *   cpt-doc / cpt-impl → the cpt-id (from refs[0]); on multiple refs append "+N more".
   */
  function edgeLabel(e) {
    if (e.type === "file-link") {
      const target = (window._cfcAllNodesData || []).find(function (n) { return n.id === e.to; });
      if (target && target.rel_path) {
        const base = target.rel_path.split("/").pop();
        return base.replace(/\.md$/, "");
      }
      return "";
    }
    // cpt-doc / cpt-impl
    const refs = e.refs || [];
    if (!refs.length) return "";
    const first = refs[0].cpt_id || "";
    const short = first.replace(/^cpt-/, "").replace(/:p\d+$/, "");
    if (refs.length > 1) return short + " +" + (refs.length - 1);
    return short;
  }

  /* ── BFS edge/node reachability ─────────────────────────────── */
  function nodesWithinDepth(rootIds, depth, edges) {
    if (depth === 0) return { nodes: new Set(rootIds), edges: new Set() };
    const adj = {};          // node id → [edge ids]
    const edgeNodes = {};    // edge id → [node id, node id]
    for (var i = 0; i < edges.length; i++) {
      var e = edges[i];
      edgeNodes[e.id] = [e.from, e.to];
      if (!adj[e.from]) adj[e.from] = [];
      adj[e.from].push(e.id);
      if (!adj[e.to]) adj[e.to] = [];
      adj[e.to].push(e.id);
    }
    var visited = new Set(rootIds);
    var reachableEdges = new Set();
    var frontier = new Set(rootIds);
    for (var h = 0; h < depth; h++) {
      var next = new Set();
      frontier.forEach(function (nid) {
        (adj[nid] || []).forEach(function (eid) {
          reachableEdges.add(eid);
          var pair = edgeNodes[eid];
          var other = pair[0] === nid ? pair[1] : pair[0];
          if (!visited.has(other)) {
            visited.add(other);
            next.add(other);
          }
        });
      });
      if (!next.size) break;
      frontier = next;
    }
    return { nodes: visited, edges: reachableEdges };
  }

  /* ── Category band hit-testing ───────────────────────────────── */
  function hitTestCategoryBand(canvasPos, categoryBands) {
    var cats = Object.keys(categoryBands);
    for (var i = 0; i < cats.length; i++) {
      var cat = cats[i];
      var band = categoryBands[cat];
      if (canvasPos.x >= band.x && canvasPos.x <= band.x + band.w &&
          canvasPos.y >= band.y && canvasPos.y <= band.y + band.h) {
        return cat;
      }
    }
    return null;
  }

  /* ── Focus management ────────────────────────────────────────── */
  function setFocus(nodeIdSet) {
    currentFocusIds = nodeIdSet;
    applyFocus(nodeIdSet);
  }

  function clearFocus() {
    currentFocusIds = null;
    recomputeEdgeVisibility();
    const network = window._cfcNetwork;
    if (network) network.selectNodes([]);
  }

  function applyFocus(nodeIdSet) {
    recomputeEdgeVisibility();
    const network = window._cfcNetwork;
    if (network) network.selectNodes(Array.from(nodeIdSet));
  }

  /* Node visibility — driven by enabledNodeKinds. Hidden nodes are removed
   * from the canvas (vis-network auto-hides edges whose endpoint is hidden,
   * but we also enforce it in recomputeEdgeVisibility for consistency). */
  function recomputeNodeVisibility() {
    const nodesDS = window._cfcNodesDS;
    const allNodesData = window._cfcAllNodesData || [];
    if (!nodesDS) return;
    nodesDS.update(allNodesData.map(function (n) {
      return { id: n.id, hidden: !enabledNodeKinds[n.kind] };
    }));
  }

  /* Single source of truth for edge visibility:
   *   edge visible ⇔ (enabledEdgeTypes[type]  OR  edge in focus BFS reach)
   *                  AND both endpoints belong to an enabled node kind.
   */
  function recomputeEdgeVisibility() {
    const edgesDS = window._cfcEdgesDS;
    const nodesDS = window._cfcNodesDS;
    const allNodeIds = window._cfcAllNodeIds || [];
    const allNodesData = window._cfcAllNodesData || [];
    if (!edgesDS || !nodesDS) return;

    const kindById = {};
    allNodesData.forEach(function (n) { kindById[n.id] = n.kind; });

    let reachableNodes = null;
    let reachableEdges = null;
    if (currentFocusIds && currentFocusIds.size > 0) {
      const result = nodesWithinDepth(Array.from(currentFocusIds), activeDepth, allEdgesData);
      reachableNodes = result.nodes;
      reachableEdges = result.edges;
    }

    edgesDS.update(allEdgesData.map(function (e) {
      const byType = !!enabledEdgeTypes[e.type];
      const byFocus = reachableEdges ? reachableEdges.has(e.id) : false;
      const endpointsVisible =
        enabledNodeKinds[kindById[e.from]] !== false &&
        enabledNodeKinds[kindById[e.to]]   !== false;
      return { id: e.id, hidden: !((byType || byFocus) && endpointsVisible) };
    }));

    if (reachableNodes) {
      nodesDS.update(allNodeIds.map(function (id) {
        return { id: id, opacity: reachableNodes.has(id) ? 1.0 : 0.18 };
      }));
    } else {
      nodesDS.update(allNodeIds.map(function (id) {
        return { id: id, opacity: 1.0 };
      }));
    }
  }

  /* ── Inspector ───────────────────────────────────────────────── */
  function showNodeInspector(node, data, primary) {
    const insp = document.getElementById("inspector");
    // Ensure inspector is visible before populating
    insp.classList.add("open");
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

    /* Index def-sites from cpt_uses (md-def entries carry the definition
     * line + paragraph snippet — surface them under cpt_defs). */
    const defSiteById = {};
    (node.cpt_uses || []).forEach(function (u) {
      if (u.marker_kind === "md-def") defSiteById[u.cpt_id] = u;
    });

    /* For source nodes we keep snippets as plain code, not Markdown. */
    const renderSnippet = node.kind === "source"
      ? function (text) {
          return collapsible(el("pre", { className: "snippet code" }, text || ""), text || "");
        }
      : function (text) {
          return collapsible(mdElement(text || "", { className: "snippet" }), text || "");
        };

    /* cpt definitions — clickable chip opens picker of consumer nodes */
    if (node.cpt_defs && node.cpt_defs.length > 0) {
      body.appendChild(fieldHeading("cpt-IDs defined (" + node.cpt_defs.length + ")"));
      node.cpt_defs.forEach(function (d) {
        const card = el("div", { className: "ref-card" });
        card.appendChild(cptChip(d, "users"));
        const site = defSiteById[d];
        if (site) {
          card.appendChild(el("div", {}, el("span", {}, "line " + site.line)));
          card.appendChild(renderSnippet(site.snippet));
        } else {
          card.appendChild(el("div", { className: "snippet muted" }, "(definition site not located)"));
        }
        body.appendChild(card);
      });
    }

    /* cpt uses — clickable chip jumps to definer node */
    const useEntries = (node.cpt_uses || []).filter(function (u) {
      return u.marker_kind !== "md-def";
    });
    if (useEntries.length > 0) {
      body.appendChild(fieldHeading("cpt-IDs used (" + useEntries.length + ")"));
      const listEl = el("div", { className: "ref-list" });
      const INITIAL = 20;
      function renderUse(u) {
        const card = el("div", { className: "ref-card" });
        card.appendChild(cptChip(u.cpt_id, "definer"));
        const meta = "line " + u.line + (u.marker_kind ? " · " + u.marker_kind : "");
        card.appendChild(el("div", {}, el("span", {}, meta)));
        card.appendChild(renderSnippet(u.snippet));
        return card;
      }
      useEntries.slice(0, INITIAL).forEach(function (u) {
        listEl.appendChild(renderUse(u));
      });
      body.appendChild(listEl);
      if (useEntries.length > INITIAL) {
        const remaining = useEntries.length - INITIAL;
        const btn = el("button", { className: "snippet-toggle load-more" },
                       "show all (" + remaining + " more)");
        btn.addEventListener("click", function () {
          useEntries.slice(INITIAL).forEach(function (u) {
            listEl.appendChild(renderUse(u));
          });
          if (btn.parentNode) btn.parentNode.removeChild(btn);
        });
        body.appendChild(btn);
      }
    }

    /* Content */
    body.appendChild(fieldHeading("Content"));
    if (node.content) {
      const truncated = node.content.length > 8000;
      const text = node.content.slice(0, 8000);
      const inner = node.kind === "source"
        ? el("pre", { className: "content-block code" }, text)
        : mdElement(text, { className: "content-block" });
      body.appendChild(collapsible(inner, text));
      if (truncated) {
        body.appendChild(el("p", { className: "muted" }, "(truncated to 8000 chars)"));
      }
    } else {
      body.appendChild(el("p", { className: "muted" }, "(content not embedded)"));
    }

    insp.appendChild(body);
  }

  function showEdgeInspector(edge, data) {
    const insp = document.getElementById("inspector");
    // Ensure inspector is visible before populating
    insp.classList.add("open");
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
      // Use side may be source code → keep as plain. Def side is always markdown.
      const useNode = (window._cfcAllNodesData || []).filter(function (n) { return n.id === edge.from; })[0];
      const useIsSource = useNode && useNode.kind === "source";
      const useRender = useIsSource
        ? function (t) { return collapsible(el("pre", { className: "snippet code" }, t || ""), t || ""); }
        : function (t) { return collapsible(mdElement(t || "", { className: "snippet" }), t || ""); };
      const defRender = function (t) {
        return collapsible(mdElement(t || "", { className: "snippet" }), t || "");
      };
      edge.refs.forEach(function (r) {
        const card = el("div", { className: "ref-card" });
        if (r.cpt_id) card.appendChild(cptChip(r.cpt_id, "definer"));
        card.appendChild(el("div", {}, "use site — line " + r.line));
        if (r.snippet) card.appendChild(useRender(r.snippet));
        if (r.def_line != null) {
          card.appendChild(el("div", {}, "definition — line " + r.def_line));
        }
        if (r.def_snippet) card.appendChild(defRender(r.def_snippet));
        body.appendChild(card);
      });
    }

    insp.appendChild(body);
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

  /* Navigation history (back / forward).
   *   navBack  = stack of node IDs visited before the current one
   *   navFwd   = stack of node IDs that were "back-ed out of"
   *   navCurrent = the node currently shown in the inspector (top of history)
   * Any normal jumpToNode() pushes current → navBack and clears navFwd.
   * Back/forward navigation must NOT mutate those stacks beyond their own
   * intent, so jumpToNode() accepts a `fromHistory` opt to skip the push. */
  const navBack = [];
  const navFwd = [];
  let navCurrent = null;

  function jumpToNode(nodeId, opts) {
    opts = opts || {};
    const network = window._cfcNetwork;
    const data = window.MAP_DATA || {};
    const primary = (data.workspace || {}).primary || "local";
    if (!network) return;

    if (!opts.fromHistory) {
      if (navCurrent && navCurrent !== nodeId) {
        navBack.push(navCurrent);
        navFwd.length = 0;  // new navigation invalidates redo stack
      }
    }
    navCurrent = nodeId;
    refreshToolbarState();

    setFocus(new Set([nodeId]));
    network.fit({ nodes: [nodeId], animation: { duration: 350 } });
    const node = (data.nodes || []).filter(function (n) { return n.id === nodeId; })[0];
    if (node) showNodeInspector(node, data, primary);
  }

  function navGoBack() {
    if (!navBack.length) return;
    const prev = navBack.pop();
    if (navCurrent) navFwd.push(navCurrent);
    jumpToNode(prev, { fromHistory: true });
  }

  function navGoForward() {
    if (!navFwd.length) return;
    const next = navFwd.pop();
    if (navCurrent) navBack.push(navCurrent);
    jumpToNode(next, { fromHistory: true });
  }

  function refreshToolbarState() {
    const back = document.getElementById("tb-back");
    const fwd  = document.getElementById("tb-fwd");
    if (back) back.disabled = navBack.length === 0;
    if (fwd)  fwd.disabled  = navFwd.length === 0;
  }

  function zoomBy(factor) {
    const network = window._cfcNetwork;
    if (!network) return;
    const cur = network.getScale();
    network.moveTo({ scale: cur * factor, animation: { duration: 150 } });
  }

  function fitAll() {
    const network = window._cfcNetwork;
    if (network) network.fit({ animation: { duration: 350 } });
  }

  function wireToolbar() {
    const back = document.getElementById("tb-back");
    const fwd  = document.getElementById("tb-fwd");
    const zi   = document.getElementById("tb-zoom-in");
    const zo   = document.getElementById("tb-zoom-out");
    const fit  = document.getElementById("tb-fit");
    if (back) back.addEventListener("click", navGoBack);
    if (fwd)  fwd.addEventListener("click",  navGoForward);
    if (zi)   zi.addEventListener("click",   function () { zoomBy(1.25); });
    if (zo)   zo.addEventListener("click",   function () { zoomBy(1 / 1.25); });
    if (fit)  fit.addEventListener("click",  fitAll);
    refreshToolbarState();
  }

  /* Build a clickable chip for a cpt-id that jumps to its definer (or shows
   * a picker if there are multiple, or if direction === "users"). */
  function cptChip(cptId, direction) {
    const span = el("span", { className: "cpt-id link cpt-link" }, cptId);
    span.title = direction === "users"
      ? "Click to see nodes that use this cpt-id"
      : "Click to jump to the node defining this cpt-id";
    span.addEventListener("click", function (ev) {
      ev.stopPropagation();
      if (direction === "users") {
        showCptPicker(span, cptId, "users");
      } else {
        const definers = window._cfcCptDefiners || {};
        const set = definers[cptId];
        if (!set || set.size === 0) {
          // Try basename fallback (definers store base; uses may be phase-qualified or vice versa).
          const base = cptId.split(":")[0];
          const baseSet = definers[base];
          if (baseSet && baseSet.size > 0) return navigateOne(span, baseSet);
          flashNotFound(span);
          return;
        }
        navigateOne(span, set);
      }
    });
    return span;
  }

  function navigateOne(anchor, idSet) {
    const ids = Array.from(idSet);
    if (ids.length === 1) {
      jumpToNode(ids[0]);
    } else {
      showCptPickerForList(anchor, ids);
    }
  }

  function flashNotFound(anchor) {
    const note = el("span", { className: "muted" }, "  (not defined)");
    anchor.parentNode.insertBefore(note, anchor.nextSibling);
    setTimeout(function () { if (note.parentNode) note.parentNode.removeChild(note); }, 1500);
  }

  function showCptPicker(anchor, cptId, direction) {
    const idx = direction === "users" ? window._cfcCptUsers : window._cfcCptDefiners;
    const set = (idx || {})[cptId] || new Set();
    showCptPickerForList(anchor, Array.from(set));
  }

  function showCptPickerForList(anchor, nodeIds) {
    // Remove any existing picker right after this anchor.
    if (anchor._cptPicker && anchor._cptPicker.parentNode) {
      anchor._cptPicker.parentNode.removeChild(anchor._cptPicker);
      anchor._cptPicker = null;
      return;
    }
    const picker = el("div", { className: "cpt-picker" });
    if (!nodeIds.length) {
      picker.appendChild(el("div", { className: "empty" }, "no other nodes reference this id"));
    } else {
      const byId = {};
      (window._cfcAllNodesData || []).forEach(function (n) { byId[n.id] = n; });
      nodeIds.forEach(function (nid) {
        const n = byId[nid];
        const item = el("div", { className: "picker-item" });
        const kindLabel = n ? n.kind : "?";
        item.appendChild(el("span", { className: "kind " + kindLabel }, kindLabel));
        item.appendChild(document.createTextNode(n ? (n.rel_path || nid) : nid));
        item.addEventListener("click", function (ev) {
          ev.stopPropagation();
          jumpToNode(nid);
        });
        picker.appendChild(item);
      });
    }
    anchor.parentNode.insertBefore(picker, anchor.nextSibling);
    anchor._cptPicker = picker;
  }

  /* Wrap a snippet element with a collapse / expand control. By default the
   * snippet is clamped to ~4 lines via CSS; clicking "show more" removes the
   * clamp. If the raw text is already short (≤ 4 lines and ≤ 200 chars) the
   * toggle button is hidden — nothing to collapse. */
  function collapsible(innerEl, rawText) {
    const lineCount = (rawText || "").split("\n").length;
    const isShort = lineCount <= 4 && (rawText || "").length <= 200;
    const wrap = el("div", { className: "snippet-wrap" });
    if (isShort) {
      // No clip; just emit the content directly inside the wrap.
      wrap.classList.add("short");
      wrap.appendChild(innerEl);
      return wrap;
    }
    // The clip element is the only thing that gets max-height + overflow:hidden.
    // Button lives outside the clip so it stays clickable when collapsed.
    const clip = el("div", { className: "snippet-clip collapsed" });
    clip.appendChild(innerEl);
    const fade = el("div", { className: "snippet-fade" });
    clip.appendChild(fade);
    wrap.appendChild(clip);

    const btn = el("button", { className: "snippet-toggle" }, "show more");
    btn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      ev.preventDefault();
      const expanded = clip.classList.toggle("expanded");
      clip.classList.toggle("collapsed", !expanded);
      btn.textContent = expanded ? "show less" : "show more";
    });
    wrap.appendChild(btn);
    return wrap;
  }

  /* Render Markdown safely. Uses vendored marked.js → DOMPurify chain.
   * If either library is missing, falls back to a textContent paragraph. */
  function mdElement(text, opts) {
    opts = opts || {};
    const wrap = el("div", { className: "md " + (opts.className || "") });
    if (!text) return wrap;
    if (typeof window.marked === "undefined" || typeof window.DOMPurify === "undefined") {
      wrap.appendChild(el("pre", {}, text));
      return wrap;
    }
    try {
      const html = window.marked.parse(text, { gfm: true, breaks: false, mangle: false, headerIds: false });
      wrap.innerHTML = window.DOMPurify.sanitize(html, {
        ALLOWED_TAGS: ["p","a","strong","em","code","pre","kbd","ul","ol","li","blockquote",
                        "h1","h2","h3","h4","h5","h6","br","hr","table","thead","tbody","tr","th","td",
                        "img","input","del","ins","sup","sub"],
        ALLOWED_ATTR: ["href","title","alt","src","class","type","checked","disabled","colspan","rowspan"],
        ALLOW_DATA_ATTR: false,
      });
    } catch (err) {
      wrap.appendChild(el("pre", {}, text));
    }
    return wrap;
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
