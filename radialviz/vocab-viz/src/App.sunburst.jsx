import { useState, useEffect, useRef, useCallback, useMemo, createContext, useContext } from "react";
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

/* ═══════════════════════════════════════════════════
   GLOBAL LOADING BAR
   Thin animated gold bar at top of viewport.
   ═══════════════════════════════════════════════════ */
const LoadingContext = createContext({ start: () => {}, stop: () => {} });

function useLoadingTracker() {
  const countRef = useRef(0);
  const [visible, setVisible] = useState(false);
  const timerRef = useRef(null);

  const start = useCallback(() => {
    countRef.current++;
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    setVisible(true);
  }, []);

  const stop = useCallback(() => {
    countRef.current = Math.max(0, countRef.current - 1);
    if (countRef.current === 0) {
      // Keep bar visible for 300ms minimum to avoid flash
      timerRef.current = setTimeout(() => { setVisible(false); timerRef.current = null; }, 300);
    }
  }, []);

  return { visible, start, stop };
}

function LoadingBar({ visible }) {
  if (!visible) return null;
  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, height: 3, zIndex: 9999,
      background: T.border, overflow: "hidden",
    }}>
      <div style={{
        height: "100%", background: `linear-gradient(90deg, transparent, ${T.gold}, transparent)`,
        width: "40%",
        animation: "loadbar 1.2s ease-in-out infinite",
      }} />
      <style>{`@keyframes loadbar { 0% { transform: translateX(-100%); } 100% { transform: translateX(350%); } }`}</style>
    </div>
  );
}

function useApi(url, loadingCtx) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!url) { setData(null); return; }
    let c = false;
    setLoading(true);
    if (loadingCtx) loadingCtx.start();
    fetch(url).then(r => r.json()).then(d => { if (!c) setData(d); })
      .catch(() => {}).finally(() => {
        if (!c) setLoading(false);
        if (loadingCtx) loadingCtx.stop();
      });
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
  const [sortBy, setSortBy] = useState("corpus"); // "corpus" | "alpha"

  const filtered = useMemo(() => {
    let list = authors;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(a =>
        a.author.toLowerCase().includes(q) ||
        (works[a.author] || []).some(w => (w.title || "").toLowerCase().includes(q))
      );
    }
    if (sortBy === "alpha") {
      list = [...list].sort((a, b) => a.author.localeCompare(b.author));
    }
    return list;
  }, [authors, works, search, sortBy]);

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
      <div style={{ padding: "6px 8px", borderBottom: `1px solid ${T.border}`, display: "flex", gap: 4 }}>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Filter..."
          style={{ flex: 1, background: T.surface, border: `1px solid ${T.borderL}`,
            borderRadius: 4, padding: "4px 7px", color: T.text, fontSize: 14,
            fontFamily: T.font, outline: "none" }} />
        <select value={sortBy} onChange={e => setSortBy(e.target.value)}
          style={{ background: T.surface, border: `1px solid ${T.borderL}`,
            borderRadius: 4, padding: "4px", color: T.text, fontSize: 12,
            fontFamily: T.font, cursor: "pointer" }}>
          <option value="corpus">Size</option>
          <option value="alpha">A-Z</option>
        </select>
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

function WordList({ vocab, selectedId, onSelect, sort, onSortChange, searchQ, onSearchChange, loading, posFilter, onPosFilterChange, totalCount, canLoadMore, onLoadMore }) {
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
              flex: 1, minWidth: 0, wordBreak: "break-word",
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
      <div style={{ padding: "4px 10px", borderTop: `1px solid ${T.border}`, fontSize: 12, color: T.dim, flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span>{vocab.length}{totalCount > vocab.length ? ` of ${totalCount}` : ""} words</span>
        {canLoadMore && (
          <button onClick={onLoadMore} style={{
            background: T.gold, border: "none", borderRadius: 3, padding: "2px 8px",
            color: T.bg, fontSize: 11, fontWeight: 600, cursor: "pointer",
          }}>Load more</button>
        )}
      </div>
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
  const onSelectRef = useRef(onSelectMember);
  onSelectRef.current = onSelectMember;
  const onNodeActionRef = useRef(onNodeAction);
  onNodeActionRef.current = onNodeAction;

  // Set up D3 zoom
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

  // Draw sunburst
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    let g = svg.select("g.family-content");
    if (g.empty()) {
      g = svg.append("g").attr("class", "family-content");
    }
    g.selectAll("*").remove();

    // Remove any leftover tooltip
    d3.select("body").selectAll(".family-tooltip").remove();

    if (!family?.members?.length) {
      if (zoomRef.current) {
        const t = d3.zoomIdentity.translate(width / 2, height / 2);
        svg.call(zoomRef.current.transform, t);
      }
      return;
    }

    // ── Convert flat members array to nested hierarchy ──
    const members = [...family.members];
    let rootIdx = members.findIndex(m => m.relation === "root" && m.total_occurrences === Math.max(...members.filter(x => x.relation === "root").map(x => x.total_occurrences)));
    if (rootIdx < 0) rootIdx = 0;
    const rootMember = members[rootIdx];
    const others = members.filter((_, i) => i !== rootIdx);

    const memberById = new Map(members.map(m => [m.id, m]));
    const childrenOf = new Map();
    others.forEach(m => {
      const pid = (m.parent_lemma_id && memberById.has(m.parent_lemma_id)) ? m.parent_lemma_id : rootMember.id;
      if (!childrenOf.has(pid)) childrenOf.set(pid, []);
      childrenOf.get(pid).push(m);
    });

    // Build nested tree data for d3.hierarchy
    const buildTree = (member) => {
      const node = {
        lemma: member.lemma,
        pos: member.pos || "",
        def: (member.short_def || "").replace(/,\s*$/, ""),
        relation: member.relation || "",
        member: member, // keep reference to original member
      };
      const kids = childrenOf.get(member.id);
      if (kids && kids.length > 0) {
        // Sort by POS so same types are grouped together in the sunburst
        const sorted = [...kids].sort((a, b) => (a.pos || "").localeCompare(b.pos || ""));
        node.children = sorted.map(k => buildTree(k));
      }
      return node;
    };
    const treeData = buildTree(rootMember);

    // ── D3 partition (sunburst) layout ──
    const root = d3.hierarchy(treeData).sum(d => d.children ? 0 : 1);

    // Scale radii based on leaf count so text fits
    const leafCount = root.leaves().length;
    const rScale = Math.max(1, leafCount / 14);
    const R_ROOT = Math.round(70 * rScale);
    const R1_INNER = Math.round(90 * rScale);
    const R1_OUTER = Math.round(210 * rScale);
    const R2_INNER = Math.round(220 * rScale);
    const R2_OUTER = Math.round(320 * rScale);

    // Support deeper levels
    const innerR = (d) => {
      if (d.depth === 0) return 0;
      if (d.depth === 1) return R1_INNER;
      if (d.depth === 2) return R2_INNER;
      return R2_INNER + (d.depth - 2) * Math.round(100 * rScale);
    };
    const outerR = (d) => {
      if (d.depth === 0) return R_ROOT;
      if (d.depth === 1) return R1_OUTER;
      if (d.depth === 2) return R2_OUTER;
      return R2_OUTER + (d.depth - 2) * Math.round(100 * rScale);
    };

    const partition = d3.partition()
      .size([2 * Math.PI, 1])
      .padding(0.01);
    partition(root);

    const arc = d3.arc()
      .startAngle(d => d.x0)
      .endAngle(d => d.x1)
      .innerRadius(d => innerR(d))
      .outerRadius(d => outerR(d))
      .padAngle(0.008)
      .padRadius(R1_INNER);

    // Find max outer radius for auto-fit
    let maxOuterR = R2_OUTER;
    root.descendants().forEach(d => {
      const oR = outerR(d);
      if (oR > maxOuterR) maxOuterR = oR;
    });

    // Center and fit
    const fitScale = Math.min(width, height) / (maxOuterR * 2 + 80);
    if (zoomRef.current) {
      svg.call(zoomRef.current.transform, d3.zoomIdentity
        .translate(width / 2, height / 2).scale(fitScale));
    }

    // Rotation state
    let currentRotation = 0;
    const spinG = g.append("g");

    // Draw arcs
    const slices = spinG.selectAll(".slice")
      .data(root.descendants())
      .join("g")
      .attr("class", "slice")
      .style("cursor", "pointer");

    // Root circle
    slices.filter(d => d.depth === 0)
      .append("circle").attr("r", R_ROOT)
      .attr("fill", T.raised).attr("stroke", T.gold)
      .attr("stroke-width", 2).attr("stroke-opacity", 0.8);
    slices.filter(d => d.depth === 0)
      .append("circle").attr("r", R_ROOT + 6)
      .attr("fill", "none").attr("stroke", T.gold)
      .attr("stroke-width", 1).attr("stroke-opacity", 0.15);

    // Non-root arcs
    slices.filter(d => d.depth > 0)
      .append("path").attr("d", arc)
      .attr("fill", d => {
        const clr = POS_CLR[d.data.pos] || T.dim;
        return d.depth >= 2 ? d3.color(clr).darker(0.8) : d3.color(clr).darker(1.5);
      })
      .attr("stroke", T.bg).attr("stroke-width", 1.5).attr("opacity", 0.85);

    // Add a highlight overlay path to each non-root slice (hidden by default)
    slices.filter(d => d.depth > 0)
      .append("path").attr("class", "highlight-ring").attr("d", arc)
      .attr("fill", "none").attr("stroke", T.gold).attr("stroke-width", 3)
      .attr("opacity", 0)
      .style("pointer-events", "none");

    // Show highlight on the initially selected word
    slices.filter(d => d.depth > 0 && d.data.member?.id === selectedWord?.id)
      .select(".highlight-ring").attr("opacity", 0.9);

    // Tooltip (create early so hover handlers can reference it)
    const tooltip = d3.select("body").selectAll(".family-tooltip").data([0]).join("div")
      .attr("class", "family-tooltip")
      .style("position", "fixed").style("pointer-events", "none")
      .style("background", T.surface).style("border", `1px solid ${T.border}`)
      .style("border-radius", "6px").style("padding", "8px 12px")
      .style("font-size", "13px").style("color", T.bright)
      .style("display", "none").style("z-index", "999")
      .style("font-family", T.font);

    // Track which member is currently focused
    let focusedId = selectedWord?.id || null;

    // Hover + tooltip combined
    slices.filter(d => d.depth > 0)
      .on("mouseenter", function(e, d) {
        if (d.data.member?.id === focusedId) return; // already highlighted
        d3.select(this).select("path")
          .transition().duration(100)
          .attr("opacity", 1).attr("stroke", T.gold).attr("stroke-width", 2);
      })
      .on("mousemove", function(e, d) {
        const posColor = POS_CLR[d.data.pos] || T.dim;
        tooltip.style("display", "block")
          .style("left", (e.clientX + 15) + "px")
          .style("top", (e.clientY - 10) + "px")
          .html(`<strong>${d.data.lemma}</strong><br>
            <span style="color:${posColor};font-weight:600">${d.data.pos}</span><br>
            <em style="color:${T.dim};font-size:11px">${d.data.def || ""}</em>
            ${d.data.relation ? `<br><span style="color:${T.goldDim};font-size:10px;font-family:${T.mono}">${d.data.relation}</span>` : ""}`);
      })
      .on("mouseleave", function(e, d) {
        if (d.data.member?.id !== focusedId) {
          d3.select(this).select("path")
            .transition().duration(150)
            .attr("opacity", 0.85).attr("stroke", T.bg).attr("stroke-width", 1.5);
        }
        tooltip.style("display", "none");
      });

    // Click — highlight, rotate, and select
    slices.filter(d => d.depth > 0)
      .on("click", function(e, d) {
        e.stopPropagation();

        // Clear all highlights
        spinG.selectAll(".highlight-ring").attr("opacity", 0);
        // Reset all arc strokes
        spinG.selectAll(".slice").select("path")
          .attr("stroke", T.bg).attr("stroke-width", 1.5).attr("opacity", 0.85);

        // Highlight clicked slice
        d3.select(this).select(".highlight-ring").attr("opacity", 0.9);
        focusedId = d.data.member?.id || null;

        // Select the member
        if (d.data.member) onSelectRef.current(d.data.member);

        const midAngle = (d.x0 + d.x1) / 2;
        const targetRotation = -(midAngle * 180 / Math.PI) + 90;
        currentRotation = targetRotation;

        spinG.transition().duration(600).ease(d3.easeCubicInOut)
          .attr("transform", `rotate(${currentRotation})`);

        spinG.selectAll(".root-text")
          .transition().duration(600).ease(d3.easeCubicInOut)
          .attr("transform", `rotate(${-currentRotation})`);

        spinG.selectAll(".arc-label").each(function() {
          const labelD = d3.select(this).datum();
          const lMid = (labelD.x0 + labelD.x1) / 2;
          const lMidR = (innerR(labelD) + outerR(labelD)) / 2;
          const worldAngle = lMid + currentRotation * Math.PI / 180;
          const lx = lMidR * Math.sin(lMid);
          const ly = -lMidR * Math.cos(lMid);
          const wa = ((worldAngle % (2*Math.PI)) + 2*Math.PI) % (2*Math.PI);
          const textRot = (lMid * 180 / Math.PI) - 90 + (wa > Math.PI ? 180 : 0);
          d3.select(this)
            .transition().duration(600).ease(d3.easeCubicInOut)
            .attr("transform", `translate(${lx},${ly}) rotate(${textRot})`);
        });
      });

    // Context menu
    slices.filter(d => d.depth > 0)
      .on("contextmenu", function(e, d) {
        e.preventDefault(); e.stopPropagation();
        if (d.data.member && onNodeActionRef.current) onNodeActionRef.current(d.data.member, e.clientX, e.clientY);
      });

    // Root text
    const rootG = slices.filter(d => d.depth === 0);
    const rootTextG = rootG.append("g").attr("class", "root-text");
    const rFS = Math.min(20, Math.round(R_ROOT * 0.28));
    rootTextG.append("text")
      .attr("text-anchor", "middle").attr("y", -rFS)
      .attr("fill", T.goldDim).attr("font-size", "9px")
      .attr("font-family", T.mono).attr("letter-spacing", "2px")
      .text("ROOT");
    rootTextG.append("text")
      .attr("text-anchor", "middle").attr("y", rFS * 0.3)
      .attr("fill", T.bright).attr("font-size", rFS + "px").attr("font-weight", 700)
      .attr("font-family", T.font).text(rootMember.lemma);
    rootTextG.append("text")
      .attr("text-anchor", "middle").attr("y", rFS * 1.2)
      .attr("fill", POS_CLR[rootMember.pos] || T.dim).attr("font-size", "11px").attr("font-weight", 600)
      .attr("font-family", T.font).text(rootMember.pos || "");
    rootTextG.append("text")
      .attr("text-anchor", "middle").attr("y", rFS * 2)
      .attr("fill", T.dim).attr("font-size", "9px").attr("font-style", "italic")
      .attr("font-family", T.font)
      .text((rootMember.short_def || "").length > 20 ? (rootMember.short_def || "").slice(0, 20) + "…" : (rootMember.short_def || ""));

    // Root click
    rootG.on("click", (e) => { e.stopPropagation(); onSelectRef.current(rootMember); })
      .on("contextmenu", (e) => {
        e.preventDefault(); e.stopPropagation();
        if (onNodeActionRef.current) onNodeActionRef.current(rootMember, e.clientX, e.clientY);
      });

    // Arc labels
    slices.filter(d => d.depth > 0).each(function(d) {
      const el = d3.select(this);
      const midAngle = (d.x0 + d.x1) / 2;
      const midR = (innerR(d) + outerR(d)) / 2;
      const arcSpan = d.x1 - d.x0;

      if (arcSpan < 0.04) return;

      const x = midR * Math.sin(midAngle);
      const y = -midR * Math.cos(midAngle);
      const rotation = (midAngle * 180 / Math.PI) - 90 + (midAngle > Math.PI ? 180 : 0);

      const textG = el.append("g")
        .attr("class", "arc-label")
        .datum(d)
        .attr("transform", `translate(${x},${y}) rotate(${rotation})`);

      const fontSize = arcSpan > 0.2 ? "13px" : arcSpan > 0.1 ? "11px" : "9px";

      const showDetails = arcSpan > 0.12;

      textG.append("text")
        .attr("text-anchor", "middle")
        .attr("dy", showDetails ? "-0.3em" : "0.1em")
        .attr("fill", T.bright).attr("font-size", fontSize).attr("font-weight", 500)
        .attr("font-family", T.font).text(d.data.lemma);

      if (showDetails) {
        textG.append("text")
          .attr("text-anchor", "middle").attr("dy", "1em")
          .attr("fill", POS_CLR[d.data.pos] || T.dim)
          .attr("font-size", "9px").attr("font-weight", 600)
          .attr("font-family", T.font).text(d.data.pos);
      }

      if (d.data.relation && arcSpan > 0.15) {
        textG.append("text")
          .attr("text-anchor", "middle").attr("dy", "2.2em")
          .attr("fill", T.goldDim).attr("font-size", "7px").attr("font-family", T.mono)
          .attr("opacity", 0.7).text(d.data.relation);
      }
    });

  }, [family, selectedWord, width, height]);

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
  const [vocabLimit, setVocabLimit] = useState(500);
  const centerRef = useRef(null);
  const [centerDims, setCenterDims] = useState({ w: 600, h: 500 });

  // Global loading tracker
  const loading = useLoadingTracker();

  const { data: authData } = useApi(`${API}/authors`, loading);
  const authors = authData?.authors || [];

  const [worksMap, setWorksMap] = useState({});
  useEffect(() => {
    authors.forEach(a => {
      if (!worksMap[a.author]) {
        loading.start();
        fetch(`${API}/works?author=${encodeURIComponent(a.author)}`)
          .then(r => r.json()).then(d => {
            setWorksMap(prev => ({ ...prev, [a.author]: d.works || [] }));
          }).catch(() => {}).finally(() => loading.stop());
      }
    });
  }, [authors]);

  const vocabUrl = useMemo(() => {
    const al = [...selectedAuthors], wl = [...selectedWorks];
    if (al.length === 0 && wl.length === 0) return null;
    if (al.length > 0) return `${API}/vocab?author=${encodeURIComponent(al[0])}&limit=${vocabLimit}&sort=${vocabSort}&min_freq=1`;
    if (wl.length > 0) return `${API}/vocab?work_id=${wl[0]}&limit=${vocabLimit}&sort=${vocabSort}&min_freq=1`;
    return null;
  }, [selectedAuthors, selectedWorks, vocabSort, vocabLimit]);

  const { data: vocabData, loading: vocabLoading } = useApi(vocabUrl, loading);

  const [extraVocab, setExtraVocab] = useState([]);
  useEffect(() => {
    const al = [...selectedAuthors], wl = [...selectedWorks];
    const fetches = [];
    if (al.length > 1) al.slice(1).forEach(a => {
      fetches.push(fetch(`${API}/vocab?author=${encodeURIComponent(a)}&limit=${vocabLimit}&sort=frequency&min_freq=1`)
        .then(r => r.json()).then(d => d.vocab || []).catch(() => []));
    });
    const wf = al.length > 0 ? wl : [...wl].slice(1);
    wf.forEach(wid => {
      fetches.push(fetch(`${API}/vocab?work_id=${wid}&limit=${vocabLimit}&sort=frequency&min_freq=1`)
        .then(r => r.json()).then(d => d.vocab || []).catch(() => []));
    });
    if (fetches.length === 0) { setExtraVocab([]); return; }
    loading.start();
    Promise.all(fetches).then(r => setExtraVocab(r.flat())).finally(() => loading.stop());
  }, [selectedAuthors, selectedWorks, vocabLimit]);

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

  const { data: statusData } = useApi(`${API}/status`, loading);
  const connected = !!statusData;
  const superuser = !!statusData?.superuser;

  const { data: lemmaDetail } = useApi(selectedWord ? `${API}/lemma/${selectedWord.id}?v=${familyVersion}` : null, loading);
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
    setVocabLimit(500);
  }, []);
  const toggleWork = useCallback(id => {
    setSelectedWorks(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
    setVocabLimit(500);
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
      <LoadingBar visible={loading.visible} />
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
                posFilter={posFilter} onPosFilterChange={togglePos}
                totalCount={vocabData?.count || vocab.length}
                canLoadMore={(vocabData?.count || 0) >= vocabLimit}
                onLoadMore={() => setVocabLimit(prev => prev + 500)} />
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