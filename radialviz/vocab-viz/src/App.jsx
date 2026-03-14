import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import * as d3 from "d3";

const API = import.meta.env.PROD ? "https://api.glossalearn.com/api" : "http://127.0.0.1:5000/api";

const T = {
  bg:"#0e0d0b", surface:"#1a1815", raised:"#211f1a",
  hover:"#2a2722", border:"#302c25", borderL:"#3d372e",
  text:"#c8bfa8", dim:"#8a7f6e", bright:"#efe6d0",
  gold:"#d4a843", goldDim:"#a68432", goldGlow:"rgba(212,168,67,0.10)",
  red:"#c4574a", blue:"#5a8fb4", green:"#6b9c6b",
  purple:"#8b6fa8", teal:"#5a9e94", orange:"#c4864a",
  rose:"#b4697a", cyan:"#5aafb4",
  font:"'EB Garamond',Georgia,serif",
  mono:"'JetBrains Mono',monospace",
  // Font size scale — bump everything up for readability
  xs: 13, sm: 14, md: 16, lg: 18, xl: 26,
};
const POS_CLR = {
  noun:T.gold, verb:T.blue, adjective:T.green, adverb:T.purple,
  pronoun:T.teal, preposition:T.orange, conjunction:T.rose,
  particle:T.cyan, article:T.dim, "":T.dim,
};

function useApi(url) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!url) { setData(null); return; }
    let c = false;
    setLoading(true);
    fetch(url).then(r => r.json()).then(d => { if (!c) setData(d); })
      .catch(() => {}).finally(() => { if (!c) setLoading(false); });
    return () => { c = true; };
  }, [url]);
  return { data, loading };
}

/* ═══════════════════════════════════════════════════
   COLLAPSIBLE PANEL WRAPPER
   Collapsed: 40px strip with vertical label.
   Expanded: full width on hover.
   ═══════════════════════════════════════════════════ */
function CollapsiblePanel({ side, label, expandedWidth, children, pinned, onTogglePin }) {
  const [hovered, setHovered] = useState(false);
  const open = pinned || hovered;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: open ? expandedWidth : 40,
        minWidth: open ? expandedWidth : 40,
        transition: "width 0.25s ease, min-width 0.25s ease",
        borderLeft: side === "right" ? `1px solid ${T.border}` : "none",
        borderRight: side === "left" ? `1px solid ${T.border}` : "none",
        display: "flex", flexDirection: "column", overflow: "hidden",
        position: "relative", flexShrink: 0, zIndex: open ? 10 : 1,
        background: T.bg,
      }}>
      {/* Collapsed label */}
      {!open && (
        <div style={{
          position: "absolute", inset: 0, display: "flex",
          alignItems: "center", justifyContent: "center", cursor: "pointer",
        }}>
          <span style={{
            writingMode: "vertical-rl", textOrientation: "mixed",
            fontSize: 13, color: T.goldDim, letterSpacing: 2, fontFamily: T.font,
            transform: side === "left" ? "rotate(180deg)" : "none",
          }}>{label}</span>
        </div>
      )}
      {/* Expanded content */}
      <div style={{
        display: open ? "flex" : "none", flexDirection: "column",
        height: "100%", overflow: "hidden", width: expandedWidth,
      }}>
        {/* Panel header with pin button */}
        <div style={{
          padding: "6px 10px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 13, color: T.goldDim, letterSpacing: 1, textTransform: "uppercase" }}>
            {label}</span>
          <button onClick={onTogglePin} title={pinned ? "Unpin" : "Pin open"} style={{
            background: "none", border: "none", cursor: "pointer",
            color: pinned ? T.gold : T.dim, fontSize: 14, padding: "0 4px",
          }}>{pinned ? "📌" : "📎"}</button>
        </div>
        {children}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   WORKS SELECTOR
   ═══════════════════════════════════════════════════ */
function WorkSelector({ authors, works, selectedAuthors, selectedWorks, onToggleAuthor, onToggleWork }) {
  const [expanded, setExpanded] = useState(new Set());
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search) return authors;
    const q = search.toLowerCase();
    return authors.filter(a =>
      a.author.toLowerCase().includes(q) ||
      (works[a.author] || []).some(w => (w.title || "").toLowerCase().includes(q))
    );
  }, [authors, works, search]);

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
      <div style={{ padding: "6px 8px", borderBottom: `1px solid ${T.border}` }}>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Filter..."
          style={{ width: "100%", background: T.surface, border: `1px solid ${T.borderL}`,
            borderRadius: 4, padding: "4px 7px", color: T.text, fontSize: 14,
            fontFamily: T.font, outline: "none" }} />
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {filtered.map(a => {
          const sel = selectedAuthors.has(a.author);
          const authorWorks = works[a.author] || [];
          const exp = expanded.has(a.author);
          return (
            <div key={a.author}>
              <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "3px 8px", fontSize: 14 }}>
                <span onClick={() => {
                  const n = new Set(expanded);
                  n.has(a.author) ? n.delete(a.author) : n.add(a.author);
                  setExpanded(n);
                }} style={{ color: T.dim, fontSize: 11, width: 14, textAlign: "center", cursor: "pointer", flexShrink: 0 }}>
                  {exp ? "▾" : "▸"}</span>
                <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer", flex: 1, minWidth: 0 }}>
                  <input type="checkbox" checked={sel} onChange={() => onToggleAuthor(a.author)}
                    style={{ accentColor: T.gold, flexShrink: 0 }} />
                  <span style={{ color: sel ? T.gold : T.text, fontWeight: sel ? 600 : 400,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.author}</span>
                </label>
                <span style={{ color: T.dim, fontSize: 12, fontFamily: T.mono, flexShrink: 0 }}>{a.work_count}</span>
              </div>
              {exp && authorWorks.map(w => {
                const ws = selectedWorks.has(w.id);
                return (
                  <label key={w.id} style={{ display: "flex", alignItems: "center", gap: 5,
                    padding: "2px 8px 2px 32px", cursor: "pointer", fontSize: 13 }}>
                    <input type="checkbox" checked={ws || sel} disabled={sel}
                      onChange={() => onToggleWork(w.id)} style={{ accentColor: T.gold, flexShrink: 0 }} />
                    <span style={{ color: (ws || sel) ? T.bright : T.dim,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {w.title || w.work_code}</span>
                  </label>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   WORD LIST
   ═══════════════════════════════════════════════════ */
const POS_LIST = ["noun", "verb", "adjective", "adverb", "pronoun", "preposition", "conjunction", "particle", "article"];

function WordList({ vocab, selectedId, onSelect, sort, onSortChange, searchQ, onSearchChange, loading, posFilter, onPosFilterChange }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
      <div style={{ padding: "6px 8px", borderBottom: `1px solid ${T.border}`, display: "flex", gap: 4 }}>
        <input value={searchQ} onChange={e => onSearchChange(e.target.value)}
          placeholder="Search..."
          style={{ flex: 1, background: T.surface, border: `1px solid ${T.borderL}`,
            borderRadius: 4, padding: "4px 7px", color: T.text, fontSize: 14,
            fontFamily: T.font, outline: "none" }} />
        <select value={sort} onChange={e => onSortChange(e.target.value)}
          style={{ background: T.surface, border: `1px solid ${T.borderL}`,
            borderRadius: 4, padding: "4px", color: T.text, fontSize: 12,
            fontFamily: T.font, cursor: "pointer" }}>
          <option value="frequency">Freq</option>
          <option value="alpha">A-Z</option>
        </select>
      </div>
      {/* POS filter chips */}
      <div style={{ padding: "4px 8px", borderBottom: `1px solid ${T.border}`,
        display: "flex", flexWrap: "wrap", gap: 3 }}>
        {POS_LIST.map(pos => {
          const active = posFilter.has(pos);
          const clr = POS_CLR[pos] || T.dim;
          return (
            <button key={pos} onClick={() => onPosFilterChange(pos)}
              style={{
                padding: "2px 7px", borderRadius: 3, fontSize: 11, fontWeight: 600,
                letterSpacing: .3, cursor: "pointer", fontFamily: T.font,
                background: active ? clr : "transparent",
                color: active ? T.bg : clr,
                border: `1px solid ${active ? clr : T.borderL}`,
                opacity: active ? 1 : 0.6,
              }}>{pos.slice(0, 4)}</button>
          );
        })}
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {loading && <div style={{ padding: 12, color: T.dim, fontSize: 14, textAlign: "center" }}>Loading...</div>}
        {vocab.map(w => (
          <div key={w.id} onClick={() => onSelect(w)}
            onMouseEnter={e => { if (selectedId !== w.id) e.currentTarget.style.background = T.hover; }}
            onMouseLeave={e => { if (selectedId !== w.id) e.currentTarget.style.background = "transparent"; }}
            style={{
              display: "flex", alignItems: "baseline", gap: 5,
              padding: "5px 10px", cursor: "pointer", fontSize: 15,
              background: selectedId === w.id ? T.goldGlow : "transparent",
              borderLeft: selectedId === w.id ? `3px solid ${T.gold}` : "3px solid transparent",
            }}>
            <span style={{ fontFamily: T.font,
              color: selectedId === w.id ? T.gold : T.bright,
              fontWeight: selectedId === w.id ? 700 : 400,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1,
            }}>{w.lemma}</span>
            <span style={{ fontSize: 11, color: POS_CLR[w.pos] || T.dim, flexShrink: 0 }}>{w.pos}</span>
            <span style={{ fontSize: 12, color: T.dim, fontFamily: T.mono, flexShrink: 0 }}>
              {w.work_freq || w.total_occurrences}</span>
          </div>
        ))}
        {!loading && vocab.length === 0 && (
          <div style={{ padding: 16, textAlign: "center", color: T.dim, fontSize: 14, fontStyle: "italic" }}>
            Select works to see vocabulary</div>
        )}
      </div>
      <div style={{ padding: "4px 10px", borderTop: `1px solid ${T.border}`, fontSize: 12, color: T.dim, flexShrink: 0 }}>
        {vocab.length} words</div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   FAMILY TREE — D3 radial layout
   Root at center (gold ring), members radiating out.
   Each node: pill shape with lemma, POS color dot, short def.
   Selected word highlighted with glow.
   Non-overlapping layout with collision detection.
   ═══════════════════════════════════════════════════ */
function FamilyTree({ family, selectedWord, detailWord, onSelectMember, onNodeAction, width, height }) {
  const svgRef = useRef(null);
  const zoomRef = useRef(null);

  // Set up D3 zoom — re-run whenever the SVG mounts (always rendered now)
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);

    let g = svg.select("g.family-content");
    if (g.empty()) {
      g = svg.append("g").attr("class", "family-content");
    }

    const zoom = d3.zoom()
      .scaleExtent([0.15, 3])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });
    svg.call(zoom);
    svg.style("cursor", "grab");
    svg.on("mousedown.cursor", () => svg.style("cursor", "grabbing"));
    svg.on("mouseup.cursor", () => svg.style("cursor", "grab"));
    zoomRef.current = zoom;

    return () => { svg.on(".zoom", null); };
  }, []);

  // Draw family tree content
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    let g = svg.select("g.family-content");
    if (g.empty()) {
      g = svg.append("g").attr("class", "family-content");
    }
    g.selectAll("*").remove();

    if (!family?.members?.length) {
      // Reset zoom to center when no family
      if (zoomRef.current) {
        const t = d3.zoomIdentity.translate(width / 2, height / 2);
        svg.call(zoomRef.current.transform, t);
      }
      return;
    }

    const members = [...family.members];
    let rootIdx = members.findIndex(m => m.relation === "root" && m.total_occurrences === Math.max(...members.filter(x => x.relation === "root").map(x => x.total_occurrences)));
    if (rootIdx < 0) rootIdx = 0;
    const root = members[rootIdx];
    const others = members.filter((_, i) => i !== rootIdx);

    const nW = 145, nH = 58; // node dimensions
    const gap = 150;

    // ── Build parent/child maps ──
    const memberById = new Map(members.map(m => [m.id, m]));
    const childrenOf = new Map(); // parent_id → [member, ...]
    others.forEach(m => {
      const pid = (m.parent_lemma_id && memberById.has(m.parent_lemma_id)) ? m.parent_lemma_id : root.id;
      if (!childrenOf.has(pid)) childrenOf.set(pid, []);
      childrenOf.get(pid).push(m);
    });

    // Collect all descendants of a node
    const getDescendants = (id) => {
      const desc = new Set();
      const stack = childrenOf.get(id) || [];
      for (const c of stack) {
        desc.add(c.id);
        for (const d of getDescendants(c.id)) desc.add(d);
      }
      return desc;
    };

    // ── Determine focus ──
    // "focusNode" = the ring-1 node (direct child of root) whose branch is expanded.
    // If detailWord is a ring-1 node with children, it is the focus.
    // If detailWord is deeper, walk up to find which ring-1 ancestor owns it.
    const ring1 = childrenOf.get(root.id) || [];
    const ring1Ids = new Set(ring1.map(m => m.id));

    let focusId = null;
    if (detailWord && detailWord.id !== root.id) {
      // Walk up parent chain to find ring-1 ancestor
      let cur = detailWord.id;
      const visited = new Set();
      while (cur && !ring1Ids.has(cur) && !visited.has(cur)) {
        visited.add(cur);
        const mem = memberById.get(cur);
        if (!mem) break;
        cur = (mem.parent_lemma_id && memberById.has(mem.parent_lemma_id)) ? mem.parent_lemma_id : null;
      }
      if (cur && ring1Ids.has(cur)) {
        // Only focus if this ring-1 node actually has children
        if (childrenOf.has(cur) && childrenOf.get(cur).length > 0) focusId = cur;
      }
    }

    const focusDescendants = focusId ? getDescendants(focusId) : new Set();

    // ── Ring 1: direct children of root ──
    const ring1Radius = Math.max(ring1.length * (nW * 0.3 + gap) / (2 * Math.PI), 170);

    // Assign angles to ring-1 nodes
    const ring1Angles = new Map();
    ring1.forEach((m, i) => {
      ring1Angles.set(m.id, (i / ring1.length) * 2 * Math.PI - Math.PI / 2);
    });

    // ── Position map ──
    const posMap = new Map();
    posMap.set(root.id, { x: 0, y: 0 });

    // Place ring-1 nodes
    ring1.forEach(m => {
      const angle = ring1Angles.get(m.id);
      const r = ring1Radius;
      posMap.set(m.id, { x: Math.cos(angle) * r, y: Math.sin(angle) * r });
    });

    // Place deeper nodes: fan out behind their parent, along the parent's radial angle
    const placeChildren = (parentId, parentAngle, parentR, depth) => {
      const kids = childrenOf.get(parentId) || [];
      if (kids.length === 0) return;
      const expanded = focusId && (parentId === focusId || focusDescendants.has(parentId));
      const childR = parentR + (expanded ? (nH + gap * 0.8) : 70);
      // Spread children in a small arc centered on parent's angle
      const arcSpan = expanded ? Math.min(kids.length * 0.25, 1.2) : Math.min(kids.length * 0.08, 0.4);
      kids.forEach((m, i) => {
        const offset = kids.length === 1 ? 0 : (i / (kids.length - 1) - 0.5) * arcSpan;
        const angle = parentAngle + offset;
        const r = childR;
        posMap.set(m.id, { x: Math.cos(angle) * r, y: Math.sin(angle) * r });
        placeChildren(m.id, angle, r, depth + 1);
      });
    };
    ring1.forEach(m => {
      placeChildren(m.id, ring1Angles.get(m.id), ring1Radius, 2);
    });

    // ── Determine node visual size ──
    // "scale" per node: 1.0 = full, smaller = collapsed
    const getNodeScale = (m) => {
      if (m.id === root.id) return focusId ? 0.3 : 1.0;
      if (ring1Ids.has(m.id)) {
        if (!focusId) return 1.0;
        return m.id === focusId ? 1.15 : 0.55;
      }
      // Deeper node
      if (!focusId) return 0.3; // tiny dots when nothing focused
      if (focusDescendants.has(m.id)) return 1.0; // expanded
      return 0.0; // hidden — belongs to a different branch
    };

    // ── Draw a node at given position and scale ──
    const drawNode = (parent, x, y, m, isRoot, scale) => {
      if (scale <= 0) return; // hidden

      const ng = parent.append("g")
        .attr("transform", `translate(${x},${y})`)
        .style("cursor", "pointer");

      const clr = POS_CLR[m.pos] || T.dim;
      const isSel = m.id === selectedWord?.id;
      const isDetail = m.id === detailWord?.id;

      const baseW = isRoot ? 155 : nW;
      const baseH = isRoot ? 62 : nH;
      const w = baseW * scale;
      const h = baseH * scale;

      // For tiny nodes (scale < 0.5), just draw a small dot with lemma
      if (scale < 0.5) {
        const dotR = Math.max(6 * scale, 3);
        ng.append("circle").attr("r", dotR)
          .attr("fill", clr).attr("opacity", 0.5);
        if (scale >= 0.25) {
          ng.append("text").attr("text-anchor", "middle").attr("y", dotR + 10)
            .attr("fill", T.dim).attr("font-size", `${Math.max(7 * scale / 0.3, 5)}px`)
            .attr("font-family", T.font).attr("opacity", 0.6).text(m.lemma);
        }
        ng.on("click", (event) => { event.stopPropagation(); onSelectMember(m); })
          .on("contextmenu", (event) => {
            event.preventDefault(); event.stopPropagation();
            if (onNodeAction) onNodeAction(m, event.clientX, event.clientY);
          });
        return;
      }

      // Full node rendering (scaled)
      if (isSel) {
        ng.append("rect").attr("x", -w/2 - 6).attr("y", -h/2 - 6)
          .attr("width", w + 12).attr("height", h + 12).attr("rx", 14 * scale)
          .attr("fill", T.gold).attr("opacity", .12);
      }
      if (isDetail && !isSel) {
        ng.append("rect").attr("x", -w/2 - 4).attr("y", -h/2 - 4)
          .attr("width", w + 8).attr("height", h + 8).attr("rx", 12 * scale)
          .attr("fill", T.blue).attr("opacity", .1);
      }

      ng.append("rect").attr("x", -w/2).attr("y", -h/2)
        .attr("width", w).attr("height", h).attr("rx", 8 * scale)
        .attr("fill", isRoot ? T.raised : T.surface)
        .attr("stroke", isSel ? T.gold : (isRoot ? T.gold : clr))
        .attr("stroke-width", isSel ? 2 : (isRoot ? 1.5 : .8))
        .attr("stroke-opacity", isSel ? 1 : (isRoot ? .7 : .25));

      if (isRoot) {
        ng.append("text").attr("text-anchor", "middle").attr("y", -h/2 - 4 * scale)
          .attr("fill", T.goldDim).attr("font-size", `${10 * scale}px`).attr("font-family", T.mono)
          .attr("letter-spacing", "1.5px").text("ROOT");
      }

      const fontSize = (isRoot ? 18 : 15) * scale;
      ng.append("text").attr("text-anchor", "middle").attr("y", (isRoot ? -10 : -12) * scale)
        .attr("fill", isSel ? T.gold : T.bright)
        .attr("font-size", `${fontSize}px`)
        .attr("font-weight", (isRoot || isSel) ? 700 : 500)
        .attr("font-family", T.font).text(m.lemma);

      ng.append("text").attr("text-anchor", "middle").attr("y", (isRoot ? 5 : 1) * scale)
        .attr("fill", clr).attr("font-size", `${11 * scale}px`).attr("font-weight", 600)
        .attr("font-family", T.font).text(m.pos || "");

      if (scale >= 0.5) {
        const def = (m.short_def || "").replace(/,\s*$/, "");
        const maxChars = isRoot ? 35 : 25;
        const defText = def.length > maxChars ? def.slice(0, maxChars) + "…" : def;
        ng.append("text").attr("text-anchor", "middle").attr("y", (isRoot ? 18 : 14) * scale)
          .attr("fill", T.dim).attr("font-size", `${11 * scale}px`).attr("font-style", "italic")
          .attr("font-family", T.font).text(defText);
      }

      // Child count badge for ring-1 nodes with children (when collapsed)
      const kidCount = (childrenOf.get(m.id) || []).length;
      if (kidCount > 0 && !focusId && !isRoot) {
        ng.append("circle").attr("cx", w/2 + 2).attr("cy", -h/2 - 2)
          .attr("r", 7).attr("fill", T.gold).attr("opacity", 0.8);
        ng.append("text").attr("x", w/2 + 2).attr("y", -h/2 + 1)
          .attr("text-anchor", "middle").attr("fill", T.bg)
          .attr("font-size", "9px").attr("font-weight", 700)
          .attr("font-family", T.mono).text(kidCount);
      }

      ng.on("mouseenter", function() {
        d3.select(this).select("rect").transition().duration(80)
          .attr("stroke", T.gold).attr("stroke-opacity", 1);
      }).on("mouseleave", function() {
        if (m.id !== selectedWord?.id) {
          d3.select(this).select("rect").transition().duration(80)
            .attr("stroke", isRoot ? T.gold : clr)
            .attr("stroke-opacity", isRoot ? .7 : .25);
        }
      }).on("click", (event) => { event.stopPropagation(); onSelectMember(m); })
        .on("contextmenu", (event) => {
          event.preventDefault(); event.stopPropagation();
          if (onNodeAction) onNodeAction(m, event.clientX, event.clientY);
        });
    };

    // ── Draw connections ──
    others.forEach(m => {
      const scale = getNodeScale(m);
      if (scale <= 0) return;
      const pos = posMap.get(m.id);
      if (!pos) return;
      const pid = (m.parent_lemma_id && memberById.has(m.parent_lemma_id)) ? m.parent_lemma_id : root.id;
      const parentPos = posMap.get(pid) || { x: 0, y: 0 };

      g.append("line")
        .attr("x1", parentPos.x).attr("y1", parentPos.y)
        .attr("x2", pos.x).attr("y2", pos.y)
        .attr("stroke", T.border).attr("stroke-width", scale >= 0.5 ? 1 : 0.5)
        .attr("stroke-dasharray", scale >= 0.5 ? "4,4" : "2,3")
        .attr("opacity", scale >= 0.5 ? .5 : .25);

      if (scale >= 0.5 && m.relation && m.relation !== "root") {
        const lbl = m.relation.replace("prefix ", "").slice(0, 12);
        const mx = (parentPos.x + pos.x) * 0.5, my = (parentPos.y + pos.y) * 0.5;
        g.append("text").attr("x", mx).attr("y", my - 4)
          .attr("text-anchor", "middle").attr("fill", T.goldDim)
          .attr("font-size", "9px").attr("font-family", T.mono)
          .attr("opacity", .7).text(lbl);
      }
    });

    // ── Draw all nodes ──
    // Draw non-focused first, then focused branch, then root on top
    others.forEach(m => {
      const scale = getNodeScale(m);
      if (scale <= 0 || (focusId && (m.id === focusId || focusDescendants.has(m.id)))) return;
      const pos = posMap.get(m.id);
      if (pos) drawNode(g, pos.x, pos.y, m, false, scale);
    });
    // Draw focused branch
    if (focusId) {
      const focusMember = memberById.get(focusId);
      const focusPos = posMap.get(focusId);
      // Draw focused descendants first, then the focus node on top
      others.forEach(m => {
        if (!focusDescendants.has(m.id)) return;
        const pos = posMap.get(m.id);
        if (pos) drawNode(g, pos.x, pos.y, m, false, getNodeScale(m));
      });
      if (focusMember && focusPos) drawNode(g, focusPos.x, focusPos.y, focusMember, false, getNodeScale(focusMember));
    }
    // Draw root last (on top)
    drawNode(g, 0, 0, root, true, getNodeScale(root));

    // Auto-fit
    if (zoomRef.current) {
      let maxR = ring1Radius + nW / 2 + 30;
      if (focusId) {
        // Include expanded children in the fit
        posMap.forEach((pos) => {
          const dist = Math.sqrt(pos.x * pos.x + pos.y * pos.y);
          if (dist + nW / 2 + 30 > maxR) maxR = dist + nW / 2 + 30;
        });
      }
      const fitScale = Math.min(width / (maxR * 2 + 40), height / (maxR * 2 + 40), 1);
      const t = d3.zoomIdentity.translate(width / 2, height / 2).scale(fitScale);
      svg.call(zoomRef.current.transform, t);
    }

  }, [family, selectedWord, detailWord, width, height, onSelectMember, onNodeAction]);

  // Always render the SVG so zoom bindings persist.
  // Overlay the placeholder when there's no family.
  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <svg ref={svgRef} width={width} height={height}
        style={{ position: "absolute", top: 0, left: 0, display: "block", background: T.bg }} />
      {!family && (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center",
          justifyContent: "center", flexDirection: "column", gap: 8, pointerEvents: "none" }}>
          <div style={{ fontSize: 32, opacity: .1 }}>&#x27E1;</div>
          <div style={{ color: T.dim, fontSize: 15, fontFamily: T.font }}>
            Select a word to see its derivational family</div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   FORMS / DETAIL PANEL
   ═══════════════════════════════════════════════════ */
function FormsPanel({ lemmaId, workId, scope }) {
  const activeWorkId = scope === "work" && workId ? workId : null;
  const url = lemmaId
    ? `${API}/lemma/${lemmaId}${activeWorkId ? `?work_id=${activeWorkId}` : ""}`
    : null;
  const { data, loading } = useApi(url);
  const [tab, setTab] = useState("forms");
  useEffect(() => setTab("forms"), [lemmaId]);

  const groupedForms = useMemo(() => {
    if (!data?.forms) return [];
    const groups = new Map();
    data.forms.forEach(f => {
      const key = [f.pos, f.tense, f.mood, f.voice].filter(Boolean).join(" ") || "other";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(f);
    });
    return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [data?.forms]);

  if (!lemmaId) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
      height: "100%", color: T.dim, fontSize: 14, fontStyle: "italic", padding: 16, textAlign: "center" }}>
      Click a word to see details</div>
  );
  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
      height: "100%", color: T.dim }}>Loading...</div>
  );
  if (!data) return null;

  const tabs = [
    { id: "forms", label: "Forms", n: data.forms?.length || 0 },
    { id: "works", label: "Works", n: data.top_works?.length || 0 },
    { id: "defs", label: "Defs", n: data.definitions?.length || 0 },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Header */}
      <div style={{ padding: "12px 14px 8px", borderBottom: `1px solid ${T.border}`, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: 24, fontWeight: 700, color: T.bright, fontFamily: T.font }}>{data.lemma}</span>
          <span style={{ fontSize: 13, color: POS_CLR[data.pos] || T.dim, fontWeight: 600 }}>{data.pos}</span>
          <span style={{ fontSize: 11, color: T.dim, fontFamily: T.mono }}>
            #{data.frequency_rank} · ×{data.total_occurrences?.toLocaleString()}</span>
        </div>
        {data.short_def && (
          <div style={{ fontSize: 13, color: T.dim, fontStyle: "italic", marginTop: 2, lineHeight: 1.4 }}>
            {data.short_def.slice(0, 100)}</div>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: `1px solid ${T.border}`, flexShrink: 0 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            flex: 1, padding: "7px 0", background: "none", border: "none",
            borderBottom: tab === t.id ? `2px solid ${T.gold}` : "2px solid transparent",
            color: tab === t.id ? T.gold : T.dim,
            fontSize: 12, fontFamily: T.font, letterSpacing: .6, cursor: "pointer",
          }}>
            {t.label.toUpperCase()}
            {t.n > 0 && <span style={{ opacity: .5, marginLeft: 2 }}>({t.n})</span>}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px" }}>
        {tab === "forms" && (
          <div>
            {groupedForms.map(([group, forms], gi) => (
              <div key={gi} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 11, color: T.goldDim, letterSpacing: 1, marginBottom: 3,
                  textTransform: "uppercase" }}>{group}</div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <tbody>
                    {forms.map((f, fi) => (
                      <tr key={fi} style={{ borderBottom: `1px solid ${T.border}` }}>
                        <td style={{ padding: "3px 4px", color: T.bright, fontFamily: T.font, fontSize: 14, fontWeight: 500 }}>{f.form}</td>
                        <td style={{ padding: "3px 4px", color: T.dim, fontSize: 11 }}>
                          {[f.person, f.number, f.gender, f.gram_case, f.degree].filter(Boolean).join(", ")}</td>
                        <td style={{ padding: "3px 2px", color: T.dim, fontSize: 11, fontFamily: T.mono, textAlign: "right" }}>{f.morph_tag}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
            {groupedForms.length === 0 && (
              <div style={{ color: T.dim, fontSize: 13, fontStyle: "italic" }}>No forms recorded</div>
            )}
          </div>
        )}

        {tab === "works" && (data.top_works || []).map((w, i) => (
          <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 6, padding: "3px 0",
            borderBottom: `1px solid ${T.border}` }}>
            <span style={{ fontFamily: T.mono, fontSize: 12, color: T.gold, minWidth: 42, textAlign: "right" }}>×{w.count}</span>
            <span style={{ fontSize: 14, color: T.bright }}>{w.author}</span>
            <span style={{ fontSize: 13, color: T.dim, fontStyle: "italic" }}>{w.title}</span>
          </div>
        ))}

        {tab === "defs" && (
          <div>
            {data.definitions?.length > 0 ? data.definitions.map((d, i) => (
              <div key={i} style={{ borderBottom: `1px solid ${T.border}`, paddingBottom: 6, marginBottom: 6 }}>
                <div style={{ fontSize: 11, color: T.goldDim, letterSpacing: 1, marginBottom: 2 }}>{d.source?.toUpperCase()}</div>
                <div style={{ fontSize: 13, color: T.text, lineHeight: 1.5 }}>{(d.short_def || d.definition || "").slice(0, 400)}</div>
              </div>
            )) : data.lsj_def ? (
              <div style={{ fontSize: 13, color: T.text, lineHeight: 1.5 }}>{data.lsj_def.slice(0, 600)}</div>
            ) : (
              <div style={{ color: T.dim, fontSize: 13, fontStyle: "italic" }}>No definitions</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   SUPERUSER: Add Word Modal
   ═══════════════════════════════════════════════════ */
const RELATION_OPTIONS = [
  "root", "derived",
  "prefix ἀνά-", "prefix ἀντί-", "prefix ἀπό-", "prefix διά-",
  "prefix εἰσ-", "prefix ἐκ-", "prefix ἐν-", "prefix ἐπί-",
  "prefix κατά-", "prefix μετά-", "prefix παρά-", "prefix περί-",
  "prefix πρό-", "prefix σύν-", "prefix ὑπέρ-", "prefix ὑπό-",
  "prefix ἀ- (privative)", "prefix ἀν- (privative)",
  "prefix δυσ-", "prefix εὐ-",
];

function AddWordModal({ familyId, familyLabel, familyMembers, onClose, onDone }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState(null);
  const [relation, setRelation] = useState("derived");
  const [customRel, setCustomRel] = useState("");
  const [useCustom, setUseCustom] = useState(false);
  const [parentLemmaId, setParentLemmaId] = useState("");
  const [error, setError] = useState(null);
  const [conflict, setConflict] = useState(null);
  const [saving, setSaving] = useState(false);

  const doSearch = useCallback(() => {
    if (!query.trim()) return;
    setSearching(true);
    fetch(`${API}/search?q=${encodeURIComponent(query.trim())}&limit=20`)
      .then(r => r.json()).then(d => { setResults(d.results || []); setSearching(false); })
      .catch(() => setSearching(false));
  }, [query]);

  const doAdd = useCallback(() => {
    if (!selected) return;
    setSaving(true);
    setError(null);
    setConflict(null);
    const rel = useCustom ? customRel.trim() : relation;
    const body = { lemma_id: selected.id, relation: rel };
    if (parentLemmaId) body.parent_lemma_id = parseInt(parentLemmaId);
    fetch(`${API}/family/${familyId}/add-member`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(async r => {
      const d = await r.json();
      if (r.ok) { onDone(); onClose(); }
      else if (d.conflict) { setConflict(d.conflict); setSaving(false); }
      else { setError(d.error || "Failed"); setSaving(false); }
    }).catch(() => { setError("Network error"); setSaving(false); });
  }, [selected, relation, customRel, useCustom, familyId, onDone, onClose]);

  const doMerge = useCallback(() => {
    if (!conflict) return;
    setSaving(true);
    fetch(`${API}/family/${familyId}/merge/${conflict.existing_family_id}`, { method: "POST" })
      .then(async r => {
        if (r.ok) { onDone(); onClose(); }
        else { setError("Merge failed"); setSaving(false); }
      }).catch(() => { setError("Network error"); setSaving(false); });
  }, [conflict, familyId, onDone, onClose]);

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8,
        width: 420, maxHeight: "70vh", display: "flex", flexDirection: "column",
        boxShadow: "0 8px 32px rgba(0,0,0,.5)",
      }}>
        {/* Header */}
        <div style={{ padding: "10px 14px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 14, color: T.gold, fontWeight: 600 }}>Add Word to Family</span>
          <button onClick={onClose} style={{ background: "none", border: "none",
            color: T.dim, cursor: "pointer", fontSize: 18, padding: 0 }}>x</button>
        </div>

        {/* Search */}
        <div style={{ padding: "8px 14px", display: "flex", gap: 6 }}>
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && doSearch()}
            placeholder="Search lemma or definition..."
            style={{ flex: 1, background: T.bg, border: `1px solid ${T.borderL}`,
              borderRadius: 4, padding: "6px 8px", color: T.text, fontSize: 14,
              fontFamily: T.font, outline: "none" }} autoFocus />
          <button onClick={doSearch} disabled={searching} style={{
            background: T.gold, border: "none", borderRadius: 4, padding: "6px 12px",
            color: T.bg, fontSize: 13, fontWeight: 600, cursor: "pointer",
          }}>Search</button>
        </div>

        {/* Results */}
        <div style={{ flex: 1, overflowY: "auto", maxHeight: 200 }}>
          {results.map(r => (
            <div key={r.id} onClick={() => { setSelected(r); setConflict(null); setError(null); }}
              style={{
                padding: "5px 14px", cursor: "pointer", fontSize: 14,
                background: selected?.id === r.id ? T.goldGlow : "transparent",
                borderLeft: selected?.id === r.id ? `3px solid ${T.gold}` : "3px solid transparent",
                display: "flex", alignItems: "baseline", gap: 6,
              }}>
              <span style={{ color: selected?.id === r.id ? T.gold : T.bright, fontWeight: 500 }}>{r.lemma}</span>
              <span style={{ fontSize: 11, color: POS_CLR[r.pos] || T.dim }}>{r.pos}</span>
              <span style={{ fontSize: 12, color: T.dim, fontStyle: "italic", flex: 1,
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.short_def}</span>
            </div>
          ))}
          {searching && <div style={{ padding: 12, color: T.dim, fontSize: 13, textAlign: "center" }}>Searching...</div>}
        </div>

        {/* Relation picker + action */}
        {selected && !conflict && (
          <div style={{ padding: "8px 14px", borderTop: `1px solid ${T.border}`,
            display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontSize: 12, color: T.dim }}>
              Adding <strong style={{ color: T.bright }}>{selected.lemma}</strong> to <strong style={{ color: T.gold }}>{familyLabel}</strong>
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <select value={useCustom ? "__custom__" : relation}
                onChange={e => {
                  if (e.target.value === "__custom__") setUseCustom(true);
                  else { setUseCustom(false); setRelation(e.target.value); }
                }}
                style={{ background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 4,
                  padding: "4px 6px", color: T.text, fontSize: 13, fontFamily: T.font, flex: 1 }}>
                {RELATION_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
                <option value="__custom__">Custom...</option>
              </select>
              {useCustom && (
                <input value={customRel} onChange={e => setCustomRel(e.target.value)}
                  placeholder="Custom relation..."
                  style={{ background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 4,
                    padding: "4px 6px", color: T.text, fontSize: 13, fontFamily: T.font, flex: 1 }} />
              )}
            </div>
            {/* Parent picker */}
            {familyMembers?.length > 0 && (
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 12, color: T.dim, flexShrink: 0 }}>Derives from:</span>
                <select value={parentLemmaId} onChange={e => setParentLemmaId(e.target.value)}
                  style={{ background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 4,
                    padding: "4px 6px", color: T.text, fontSize: 13, fontFamily: T.font, flex: 1 }}>
                  <option value="">Root (direct)</option>
                  {familyMembers.map(m => (
                    <option key={m.id} value={m.id}>{m.lemma} ({m.pos})</option>
                  ))}
                </select>
              </div>
            )}
            {error && <div style={{ fontSize: 12, color: T.red }}>{error}</div>}
            <button onClick={doAdd} disabled={saving} style={{
              background: T.gold, border: "none", borderRadius: 4, padding: "6px 0",
              color: T.bg, fontSize: 13, fontWeight: 600, cursor: "pointer",
            }}>{saving ? "Adding..." : "Add to Family"}</button>
          </div>
        )}

        {/* Merge prompt */}
        {conflict && (
          <div style={{ padding: "10px 14px", borderTop: `1px solid ${T.border}`,
            display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontSize: 13, color: T.orange }}>
              <strong>{selected?.lemma}</strong> already belongs to family: <strong>{conflict.existing_family_label}</strong>
            </div>
            <div style={{ fontSize: 12, color: T.dim }}>Merge that family into this one?</div>
            {error && <div style={{ fontSize: 12, color: T.red }}>{error}</div>}
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={doMerge} disabled={saving} style={{
                flex: 1, background: T.gold, border: "none", borderRadius: 4, padding: "6px 0",
                color: T.bg, fontSize: 13, fontWeight: 600, cursor: "pointer",
              }}>{saving ? "Merging..." : "Merge Families"}</button>
              <button onClick={() => setConflict(null)} style={{
                flex: 1, background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4,
                padding: "6px 0", color: T.text, fontSize: 13, cursor: "pointer",
              }}>Cancel</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   SUPERUSER: Node Action Popover
   ═══════════════════════════════════════════════════ */
function NodeActionPopover({ member, familyId, familyMembers, x, y, onClose, onDone }) {
  const [editingRel, setEditingRel] = useState(false);
  const [editingParent, setEditingParent] = useState(false);
  const [relation, setRelation] = useState(member.relation || "derived");
  const [parentLemmaId, setParentLemmaId] = useState(member.parent_lemma_id || "");
  const [confirmRemove, setConfirmRemove] = useState(false);

  const doUpdateRelation = () => {
    fetch(`${API}/family/${familyId}/member/${member.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ relation }),
    }).then(r => { if (r.ok) { onDone(); onClose(); } });
  };

  const doUpdateParent = () => {
    fetch(`${API}/family/${familyId}/member/${member.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parent_lemma_id: parentLemmaId ? parseInt(parentLemmaId) : null }),
    }).then(r => { if (r.ok) { onDone(); onClose(); } });
  };

  const doRemove = () => {
    fetch(`${API}/family/${familyId}/member/${member.id}`, { method: "DELETE" })
      .then(r => { if (r.ok) { onDone(); onClose(); } });
  };

  // Other members this node could derive from (exclude self)
  const parentOptions = (familyMembers || []).filter(m => m.id !== member.id);

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 999 }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        position: "absolute", left: x, top: y,
        background: T.surface, border: `1px solid ${T.border}`, borderRadius: 6,
        padding: 8, minWidth: 200, boxShadow: "0 4px 16px rgba(0,0,0,.4)",
      }}>
        <div style={{ fontSize: 13, color: T.bright, fontWeight: 600, marginBottom: 6 }}>{member.lemma}</div>

        {!editingRel && !editingParent && !confirmRemove && (
          <>
            <button onClick={() => setEditingRel(true)} style={{
              display: "block", width: "100%", textAlign: "left", background: "none",
              border: "none", padding: "4px 6px", color: T.text, fontSize: 13,
              cursor: "pointer", borderRadius: 3,
            }}
              onMouseEnter={e => e.currentTarget.style.background = T.hover}
              onMouseLeave={e => e.currentTarget.style.background = "none"}>
              Edit Relation ({member.relation})
            </button>
            <button onClick={() => setEditingParent(true)} style={{
              display: "block", width: "100%", textAlign: "left", background: "none",
              border: "none", padding: "4px 6px", color: T.text, fontSize: 13,
              cursor: "pointer", borderRadius: 3,
            }}
              onMouseEnter={e => e.currentTarget.style.background = T.hover}
              onMouseLeave={e => e.currentTarget.style.background = "none"}>
              Change Parent {member.parent_lemma_id
                ? `(${parentOptions.find(m => m.id === member.parent_lemma_id)?.lemma || "..."})`
                : "(root)"}
            </button>
            <button onClick={() => setConfirmRemove(true)} style={{
              display: "block", width: "100%", textAlign: "left", background: "none",
              border: "none", padding: "4px 6px", color: T.red, fontSize: 13,
              cursor: "pointer", borderRadius: 3,
            }}
              onMouseEnter={e => e.currentTarget.style.background = T.hover}
              onMouseLeave={e => e.currentTarget.style.background = "none"}>
              Remove from Family
            </button>
          </>
        )}

        {editingRel && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <select value={relation} onChange={e => setRelation(e.target.value)}
              style={{ background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 3,
                padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font }}>
              {RELATION_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <button onClick={doUpdateRelation} style={{
              background: T.gold, border: "none", borderRadius: 3, padding: "4px 0",
              color: T.bg, fontSize: 12, fontWeight: 600, cursor: "pointer",
            }}>Save</button>
          </div>
        )}

        {editingParent && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontSize: 12, color: T.dim }}>Derives from:</div>
            <select value={parentLemmaId} onChange={e => setParentLemmaId(e.target.value)}
              style={{ background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 3,
                padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font }}>
              <option value="">Root (direct)</option>
              {parentOptions.map(m => (
                <option key={m.id} value={m.id}>{m.lemma} ({m.pos})</option>
              ))}
            </select>
            <button onClick={doUpdateParent} style={{
              background: T.gold, border: "none", borderRadius: 3, padding: "4px 0",
              color: T.bg, fontSize: 12, fontWeight: 600, cursor: "pointer",
            }}>Save</button>
          </div>
        )}

        {confirmRemove && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontSize: 12, color: T.dim }}>Remove <strong>{member.lemma}</strong>?</div>
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={doRemove} style={{
                flex: 1, background: T.red, border: "none", borderRadius: 3, padding: "4px 0",
                color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer",
              }}>Remove</button>
              <button onClick={() => setConfirmRemove(false)} style={{
                flex: 1, background: T.raised, border: `1px solid ${T.border}`, borderRadius: 3,
                padding: "4px 0", color: T.text, fontSize: 12, cursor: "pointer",
              }}>Cancel</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   SUPERUSER: Merge Family Modal
   Search for another family by root or word, then merge.
   ═══════════════════════════════════════════════════ */
function MergeFamilyModal({ familyId, familyLabel, onClose, onDone }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState(null);
  const [merging, setMerging] = useState(false);
  const [error, setError] = useState(null);

  const doSearch = useCallback(() => {
    if (!query.trim()) return;
    setSearching(true);
    fetch(`${API}/family/search?q=${encodeURIComponent(query.trim())}&limit=20`)
      .then(r => r.json()).then(d => {
        // Filter out our own family
        setResults((d.results || []).filter(r => r.id !== familyId));
        setSearching(false);
      }).catch(() => setSearching(false));
  }, [query, familyId]);

  const doMerge = useCallback(() => {
    if (!selected) return;
    setMerging(true);
    setError(null);
    fetch(`${API}/family/${familyId}/merge/${selected.id}`, { method: "POST" })
      .then(async r => {
        if (r.ok) { onDone(); onClose(); }
        else { const d = await r.json(); setError(d.error || "Merge failed"); setMerging(false); }
      }).catch(() => { setError("Network error"); setMerging(false); });
  }, [selected, familyId, onDone, onClose]);

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8,
        width: 420, maxHeight: "70vh", display: "flex", flexDirection: "column",
        boxShadow: "0 8px 32px rgba(0,0,0,.5)",
      }}>
        <div style={{ padding: "10px 14px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 14, color: T.gold, fontWeight: 600 }}>Merge Another Family</span>
          <button onClick={onClose} style={{ background: "none", border: "none",
            color: T.dim, cursor: "pointer", fontSize: 18, padding: 0 }}>x</button>
        </div>
        <div style={{ padding: "6px 14px", fontSize: 12, color: T.dim }}>
          Merging into: <strong style={{ color: T.gold }}>{familyLabel}</strong>
        </div>

        <div style={{ padding: "8px 14px", display: "flex", gap: 6 }}>
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && doSearch()}
            placeholder="Search by root, label, or word..."
            style={{ flex: 1, background: T.bg, border: `1px solid ${T.borderL}`,
              borderRadius: 4, padding: "6px 8px", color: T.text, fontSize: 14,
              fontFamily: T.font, outline: "none" }} autoFocus />
          <button onClick={doSearch} disabled={searching} style={{
            background: T.gold, border: "none", borderRadius: 4, padding: "6px 12px",
            color: T.bg, fontSize: 13, fontWeight: 600, cursor: "pointer",
          }}>Search</button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", maxHeight: 250 }}>
          {results.map(r => (
            <div key={r.id} onClick={() => { setSelected(r); setError(null); }}
              style={{
                padding: "6px 14px", cursor: "pointer", fontSize: 14,
                background: selected?.id === r.id ? T.goldGlow : "transparent",
                borderLeft: selected?.id === r.id ? `3px solid ${T.gold}` : "3px solid transparent",
                display: "flex", alignItems: "baseline", gap: 8,
              }}>
              <span style={{ color: selected?.id === r.id ? T.gold : T.bright, fontWeight: 500 }}>{r.label}</span>
              <span style={{ fontSize: 11, color: T.dim, fontFamily: T.mono }}>{r.member_count} words</span>
            </div>
          ))}
          {searching && <div style={{ padding: 12, color: T.dim, fontSize: 13, textAlign: "center" }}>Searching...</div>}
          {!searching && results.length === 0 && query && (
            <div style={{ padding: 12, color: T.dim, fontSize: 13, textAlign: "center", fontStyle: "italic" }}>
              No matching families found</div>
          )}
        </div>

        {selected && (
          <div style={{ padding: "8px 14px", borderTop: `1px solid ${T.border}`,
            display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontSize: 12, color: T.dim }}>
              Merge <strong style={{ color: T.bright }}>{selected.label}</strong> ({selected.member_count} words) into <strong style={{ color: T.gold }}>{familyLabel}</strong>?
            </div>
            {error && <div style={{ fontSize: 12, color: T.red }}>{error}</div>}
            <button onClick={doMerge} disabled={merging} style={{
              background: T.gold, border: "none", borderRadius: 4, padding: "6px 0",
              color: T.bg, fontSize: 13, fontWeight: 600, cursor: "pointer",
            }}>{merging ? "Merging..." : "Merge Families"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   SUPERUSER: Rename Family Modal
   ═══════════════════════════════════════════════════ */
function RenameFamilyModal({ familyId, currentRoot, currentLabel, onClose, onDone }) {
  const [root, setRoot] = useState(currentRoot || "");
  const [label, setLabel] = useState(currentLabel || "");
  const [saving, setSaving] = useState(false);

  const doSave = () => {
    setSaving(true);
    fetch(`${API}/family/${familyId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ root: root.trim(), label: label.trim() }),
    }).then(r => {
      if (r.ok) { onDone(); onClose(); }
      else setSaving(false);
    }).catch(() => setSaving(false));
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8,
        width: 340, boxShadow: "0 8px 32px rgba(0,0,0,.5)",
        display: "flex", flexDirection: "column", gap: 10, padding: 14,
      }}>
        <div style={{ fontSize: 14, color: T.gold, fontWeight: 600 }}>Rename Family</div>
        <div>
          <div style={{ fontSize: 11, color: T.dim, marginBottom: 3, letterSpacing: .5 }}>ROOT STEM</div>
          <input value={root} onChange={e => setRoot(e.target.value)}
            style={{ width: "100%", background: T.bg, border: `1px solid ${T.borderL}`,
              borderRadius: 4, padding: "6px 8px", color: T.text, fontSize: 15,
              fontFamily: T.font, outline: "none", boxSizing: "border-box" }} />
        </div>
        <div>
          <div style={{ fontSize: 11, color: T.dim, marginBottom: 3, letterSpacing: .5 }}>LABEL</div>
          <input value={label} onChange={e => setLabel(e.target.value)}
            style={{ width: "100%", background: T.bg, border: `1px solid ${T.borderL}`,
              borderRadius: 4, padding: "6px 8px", color: T.text, fontSize: 15,
              fontFamily: T.font, outline: "none", boxSizing: "border-box" }} />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={doSave} disabled={saving} style={{
            flex: 1, background: T.gold, border: "none", borderRadius: 4, padding: "6px 0",
            color: T.bg, fontSize: 13, fontWeight: 600, cursor: "pointer",
          }}>{saving ? "Saving..." : "Save"}</button>
          <button onClick={onClose} style={{
            flex: 1, background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4,
            padding: "6px 0", color: T.text, fontSize: 13, cursor: "pointer",
          }}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   MAIN APP
   ═══════════════════════════════════════════════════ */
export default function App() {
  const [selectedAuthors, setSelectedAuthors] = useState(new Set());
  const [selectedWorks, setSelectedWorks] = useState(new Set());
  const [vocabSort, setVocabSort] = useState("frequency");
  const [vocabSearch, setVocabSearch] = useState("");
  const [posFilter, setPosFilter] = useState(new Set());
  const [selectedWord, setSelectedWord] = useState(null);
  const [detailWord, setDetailWord] = useState(null);
  const [leftPinned, setLeftPinned] = useState(true);
  const [rightPinned, setRightPinned] = useState(false);
  const [familyVersion, setFamilyVersion] = useState(0);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [nodeAction, setNodeAction] = useState(null); // { member, x, y }
  const [familyScope, setFamilyScope] = useState("all"); // "all" | "work"
  const centerRef = useRef(null);
  const [centerDims, setCenterDims] = useState({ w: 600, h: 500 });

  const { data: authData } = useApi(`${API}/authors`);
  const authors = authData?.authors || [];

  const [worksMap, setWorksMap] = useState({});
  useEffect(() => {
    authors.forEach(a => {
      if (!worksMap[a.author]) {
        fetch(`${API}/works?author=${encodeURIComponent(a.author)}`)
          .then(r => r.json()).then(d => {
            setWorksMap(prev => ({ ...prev, [a.author]: d.works || [] }));
          }).catch(() => {});
      }
    });
  }, [authors]);

  const vocabUrl = useMemo(() => {
    const al = [...selectedAuthors], wl = [...selectedWorks];
    if (al.length === 0 && wl.length === 0) return null;
    if (al.length > 0) return `${API}/vocab?author=${encodeURIComponent(al[0])}&limit=2000&sort=${vocabSort}&min_freq=1`;
    if (wl.length > 0) return `${API}/vocab?work_id=${wl[0]}&limit=2000&sort=${vocabSort}&min_freq=1`;
    return null;
  }, [selectedAuthors, selectedWorks, vocabSort]);

  const { data: vocabData, loading: vocabLoading } = useApi(vocabUrl);

  const [extraVocab, setExtraVocab] = useState([]);
  useEffect(() => {
    const al = [...selectedAuthors], wl = [...selectedWorks];
    const fetches = [];
    if (al.length > 1) al.slice(1).forEach(a => {
      fetches.push(fetch(`${API}/vocab?author=${encodeURIComponent(a)}&limit=2000&sort=frequency&min_freq=1`)
        .then(r => r.json()).then(d => d.vocab || []).catch(() => []));
    });
    const wf = al.length > 0 ? wl : [...wl].slice(1);
    wf.forEach(wid => {
      fetches.push(fetch(`${API}/vocab?work_id=${wid}&limit=2000&sort=frequency&min_freq=1`)
        .then(r => r.json()).then(d => d.vocab || []).catch(() => []));
    });
    if (fetches.length === 0) { setExtraVocab([]); return; }
    Promise.all(fetches).then(r => setExtraVocab(r.flat()));
  }, [selectedAuthors, selectedWorks]);

  const vocab = useMemo(() => {
    const all = [...(vocabData?.vocab || []), ...extraVocab];
    const map = new Map();
    all.forEach(w => {
      const ex = map.get(w.id);
      if (!ex || (w.work_freq || 0) > (ex.work_freq || 0)) map.set(w.id, w);
    });
    let list = [...map.values()];
    if (vocabSearch) {
      const q = vocabSearch.toLowerCase();
      list = list.filter(w => w.lemma.toLowerCase().includes(q) || (w.short_def || "").toLowerCase().includes(q));
    }
    if (posFilter.size > 0) {
      list = list.filter(w => posFilter.has(w.pos));
    }
    if (vocabSort === "alpha") list.sort((a, b) => a.lemma.localeCompare(b.lemma, "el"));
    else list.sort((a, b) => (b.work_freq || b.total_occurrences || 0) - (a.work_freq || a.total_occurrences || 0));
    return list;
  }, [vocabData, extraVocab, vocabSort, vocabSearch, posFilter]);

  const { data: statusData } = useApi(`${API}/status`);
  const connected = !!statusData;
  const superuser = !!statusData?.superuser;

  const { data: lemmaDetail } = useApi(selectedWord ? `${API}/lemma/${selectedWord.id}?v=${familyVersion}` : null);
  const familyAll = lemmaDetail?.family || null;
  const bumpFamily = useCallback(() => setFamilyVersion(v => v + 1), []);

  const vocabIds = useMemo(() => new Set(vocab.map(w => w.id)), [vocab]);
  const hasWorkFilter = selectedAuthors.size > 0 || selectedWorks.size > 0;
  const family = useMemo(() => {
    if (!familyAll) return null;
    if (familyScope !== "work" || !hasWorkFilter) return familyAll;
    const filtered = familyAll.members.filter(m => vocabIds.has(m.id));
    if (filtered.length === 0) return familyAll; // fallback if no members match
    return { ...familyAll, members: filtered };
  }, [familyAll, familyScope, hasWorkFilter, vocabIds]);

  const togglePos = useCallback(pos => {
    setPosFilter(prev => { const n = new Set(prev); n.has(pos) ? n.delete(pos) : n.add(pos); return n; });
  }, []);

  const toggleAuthor = useCallback(a => {
    setSelectedAuthors(prev => { const n = new Set(prev); n.has(a) ? n.delete(a) : n.add(a); return n; });
  }, []);
  const toggleWork = useCallback(id => {
    setSelectedWorks(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }, []);

  useEffect(() => {
    if (!centerRef.current) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        setCenterDims({ w: e.contentRect.width, h: e.contentRect.height });
      }
    });
    ro.observe(centerRef.current);
    // Initial measure
    const r = centerRef.current.getBoundingClientRect();
    setCenterDims({ w: r.width, h: r.height });
    return () => ro.disconnect();
  }, [leftPinned, rightPinned]);

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column",
      background: T.bg, color: T.text, fontFamily: T.font, overflow: "hidden" }}>
      <link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@300;400&display=swap" rel="stylesheet" />

      {/* Header */}
      <header style={{ borderBottom: `1px solid ${T.border}`, padding: "7px 14px",
        display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
        <span style={{ fontSize: 20, fontWeight: 700, color: T.bright, letterSpacing: 1 }}>ΓΛΩΣΣΑ</span>
        <span style={{ fontSize: 13, color: T.dim, letterSpacing: 1 }}>Vocabulary Explorer</span>
        <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, letterSpacing: 1,
          background: connected ? "rgba(107,156,107,.15)" : "rgba(196,87,74,.15)",
          color: connected ? T.green : T.red,
          border: `1px solid ${connected ? "rgba(107,156,107,.3)" : "rgba(196,87,74,.3)"}`,
        }}>{connected ? "CONNECTED" : "CONNECTING"}</span>
        {superuser && (
          <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, letterSpacing: 1,
            background: "rgba(212,168,67,.15)", color: T.gold,
            border: `1px solid rgba(212,168,67,.3)`,
          }}>SUPERUSER</span>
        )}
        <div style={{ flex: 1 }} />
        {selectedWord && (
          <span style={{ fontSize: 13, color: T.dim }}>
            Family: <strong style={{ color: T.gold }}>{family?.label || "loading..."}</strong>
          </span>
        )}
      </header>

      {/* Main layout */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* LEFT: Works + Word list */}
        <CollapsiblePanel side="left" label="WORKS & VOCABULARY"
          expandedWidth={420} pinned={leftPinned} onTogglePin={() => setLeftPinned(p => !p)}>
          <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
            {/* Works panel */}
            <div style={{ width: 200, flexShrink: 0, borderRight: `1px solid ${T.border}`,
              display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <WorkSelector authors={authors} works={worksMap}
                selectedAuthors={selectedAuthors} selectedWorks={selectedWorks}
                onToggleAuthor={toggleAuthor} onToggleWork={toggleWork} />
            </div>
            {/* Word list */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <WordList vocab={vocab} selectedId={selectedWord?.id}
                onSelect={w => { setSelectedWord(w); setDetailWord(w); setRightPinned(true); }}
                sort={vocabSort} onSortChange={setVocabSort}
                searchQ={vocabSearch} onSearchChange={setVocabSearch}
                loading={vocabLoading}
                posFilter={posFilter} onPosFilterChange={togglePos} />
            </div>
          </div>
        </CollapsiblePanel>

        {/* CENTER: Family tree */}
        <div ref={centerRef} style={{ flex: 1, display: "flex", flexDirection: "column",
          overflow: "hidden", position: "relative", background: T.bg }}>
          {/* Superuser toolbar */}
          {superuser && family && (
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 12px",
              background: "rgba(212,168,67,0.08)", borderBottom: `1px solid ${T.goldDim}`,
              flexShrink: 0 }}>
              <span style={{ fontSize: 11, fontFamily: T.mono, letterSpacing: 1.5, color: T.goldDim,
                fontWeight: 700 }}>EDIT MODE</span>
              <button onClick={() => setShowAddModal(true)} style={{
                background: T.gold, border: "none", borderRadius: 4, padding: "3px 10px",
                color: T.bg, fontSize: 12, fontWeight: 600, cursor: "pointer",
              }}>+ Add Word</button>
              <button onClick={() => setShowMergeModal(true)} style={{
                background: T.raised, border: `1px solid ${T.borderL}`, borderRadius: 4, padding: "3px 10px",
                color: T.text, fontSize: 12, fontWeight: 600, cursor: "pointer",
              }}>Merge Family</button>
              <button onClick={() => setShowRenameModal(true)} style={{
                background: T.raised, border: `1px solid ${T.borderL}`, borderRadius: 4, padding: "3px 10px",
                color: T.text, fontSize: 12, fontWeight: 600, cursor: "pointer",
              }}>Rename Root</button>
              <span style={{ fontSize: 11, color: T.dim, fontStyle: "italic" }}>Right-click a node to edit</span>
            </div>
          )}
          {hasWorkFilter && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 12px",
              borderBottom: `1px solid ${T.border}`, flexShrink: 0, background: T.surface }}>
              <span style={{ fontSize: 11, color: T.dim }}>Scope:</span>
              {["all", "work"].map(s => (
                <button key={s} onClick={() => setFamilyScope(s)} style={{
                  background: familyScope === s ? T.bright : "transparent",
                  color: familyScope === s ? T.bg : T.dim,
                  border: `1px solid ${familyScope === s ? T.bright : T.borderL}`,
                  borderRadius: 3, padding: "1px 8px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                }}>{s === "all" ? "All Works" : "This Work"}</button>
              ))}
              {familyScope === "work" && family && (
                <span style={{ fontSize: 11, color: T.dim, fontStyle: "italic" }}>
                  ({family.members.length} of {familyAll?.members?.length || 0} members)
                </span>
              )}
            </div>
          )}
          <div style={{ flex: 1, position: "relative" }}>
            <FamilyTree family={family} selectedWord={selectedWord} detailWord={detailWord}
              onSelectMember={m => setDetailWord(m)}
              onNodeAction={superuser ? (m, x, y) => setNodeAction({ member: m, x, y }) : undefined}
              width={centerDims.w} height={centerDims.h - (superuser && family ? 30 : 0)} />
          </div>
        </div>

        {/* RIGHT: Details */}
        <CollapsiblePanel side="right" label="DETAILS"
          expandedWidth={300} pinned={rightPinned} onTogglePin={() => setRightPinned(p => !p)}>
          <FormsPanel lemmaId={detailWord?.id} workId={[...selectedWorks][0] || null} scope={familyScope} />
        </CollapsiblePanel>
      </div>

      {/* Superuser: Add Word Modal */}
      {showAddModal && family && (
        <AddWordModal familyId={family.id} familyLabel={family.label}
          familyMembers={family.members}
          onClose={() => setShowAddModal(false)} onDone={bumpFamily} />
      )}

      {/* Superuser: Node Action Popover */}
      {nodeAction && family && (
        <NodeActionPopover member={nodeAction.member} familyId={family.id}
          familyMembers={family.members}
          x={nodeAction.x} y={nodeAction.y}
          onClose={() => setNodeAction(null)} onDone={bumpFamily} />
      )}

      {/* Superuser: Merge Family Modal */}
      {showMergeModal && family && (
        <MergeFamilyModal familyId={family.id} familyLabel={family.label}
          onClose={() => setShowMergeModal(false)} onDone={bumpFamily} />
      )}

      {/* Superuser: Rename Family Modal */}
      {showRenameModal && family && (
        <RenameFamilyModal familyId={family.id} currentRoot={family.root} currentLabel={family.label}
          onClose={() => setShowRenameModal(false)} onDone={bumpFamily} />
      )}
    </div>
  );
}