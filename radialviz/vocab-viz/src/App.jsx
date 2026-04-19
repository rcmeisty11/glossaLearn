import { useState, useEffect, useRef, useCallback, useMemo, createContext, useContext } from "react";
import * as d3 from "d3";
import FamilyTreeSunburst from "./FamilyTreeSunburst.jsx";
import './App.css';



import Flashcard from './components/flashcard';
import Perception from './components/perception';
import { ReactMediaRecorder } from "react-media-recorder";

const ELIDE_SPEECH_TRAINING = import.meta.env.SKIP_SPEECH;

const BASE = import.meta.env.PROD ? "https://apiaws.glossalearn.com" : "http://127.0.0.1:5000";
const API = BASE + "/api";

const T = {
  bg: "#0e0d0b", surface: "#1a1815", raised: "#211f1a",
  hover: "#2f2d28", border: "#302c25", borderL: "#3d372e",
  text: "#c8bfa8", dim: "#8a7f6e", bright: "#efe6d0",
  gold: "#d4a843", goldDim: "#a68432", goldGlow: "rgba(212,168,67,0.10)",
  red: "#c4574a", blue: "#5a8fb4", green: "#6b9c6b",
  purple: "#8b6fa8", teal: "#5a9e94", orange: "#c4864a",
  rose: "#b4697a", cyan: "#5aafb4",
  font: "'EB Garamond',Georgia,serif",
  // Font size scale — bump everything up for readability
  xs: 13, sm: 14, md: 16, lg: 18, xl: 26,
};
const POS_CLR = {
  noun: T.gold, verb: T.blue, adjective: T.green, adverb: T.purple,
  pronoun: T.teal, preposition: T.orange, conjunction: T.rose,
  particle: T.cyan, article: T.dim, "": T.dim,
};

/* ═══════════════════════════════════════════════════
   GLOBAL LOADING BAR
   Thin animated gold bar at top of viewport.
   ═══════════════════════════════════════════════════ */
const LoadingContext = createContext({ start: () => { }, stop: () => { } });

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
      .catch(() => { }).finally(() => {
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
          style={{
            flex: 1, background: T.surface, border: `1px solid ${T.borderL}`,
            borderRadius: 4, padding: "4px 7px", color: T.text, fontSize: 14,
            fontFamily: T.font, outline: "none"
          }} />
        <select value={sortBy} onChange={e => setSortBy(e.target.value)}
          style={{
            background: T.surface, border: `1px solid ${T.borderL}`,
            borderRadius: 4, padding: "4px", color: T.text, fontSize: 12,
            fontFamily: T.font, cursor: "pointer"
          }}>
          <option value="corpus">Size</option>
          <option value="alpha">A-Z</option>
        </select>
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {filtered.map(a => {
          const authorWorks = works[a.author] || [];
          const exp = expanded.has(a.author);
          const selectedCount = authorWorks.filter(w => selectedWorks.has(w.id)).length;
          return (
            <div key={a.author}>
              <div onClick={() => {
                const n = new Set(expanded);
                n.has(a.author) ? n.delete(a.author) : n.add(a.author);
                setExpanded(n);
              }}
                style={{
                  display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", fontSize: 16,
                  cursor: "pointer", userSelect: "none"
                }}
                onMouseEnter={e => { e.currentTarget.style.background = T.hover; }}
                onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}>
                <span style={{ color: T.dim, fontSize: 12, width: 14, textAlign: "center", flexShrink: 0 }}>
                  {exp ? "▾" : "▸"}</span>
                <span style={{
                  color: selectedCount > 0 ? T.gold : T.text, fontWeight: selectedCount > 0 ? 600 : 400,
                  flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap"
                }}>
                  {a.author}</span>
                <span style={{ color: T.dim, fontSize: 13, fontFamily: T.mono, flexShrink: 0 }}>
                  {selectedCount > 0 ? `${selectedCount}/` : ""}{a.work_count}</span>
              </div>
              {exp && authorWorks.map(w => {
                const ws = selectedWorks.has(w.id);
                return (
                  <label key={w.id} style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "4px 10px 4px 34px", cursor: "pointer", fontSize: 15
                  }}>
                    <input type="checkbox" checked={ws}
                      onChange={() => onToggleWork(w.id)} style={{ accentColor: T.gold, flexShrink: 0 }} />
                    <span style={{
                      color: ws ? T.bright : T.dim,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap"
                    }}>
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

function StyledInput({ searchQ, onSearchChange, placeholder }) {
  return (
    <input value={searchQ} onChange={e => onSearchChange(e.target.value)}
      placeholder={placeholder}
      style={{
        flex: 1, background: T.surface, border: `1px solid ${T.borderL}`,
        borderRadius: 4, padding: "4px 7px", color: T.text, fontSize: 14,
        fontFamily: T.font, outline: "none"
      }} />
  )
}

function WordList({ vocab, selectedId, onSelect, sort, onSortChange, searchQ, onSearchChange, loading, posFilter, onPosFilterChange, totalCount, canLoadMore, onLoadMore }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
      <div style={{ padding: "6px 8px", borderBottom: `1px solid ${T.border}`, display: "flex", gap: 4 }}>
        <StyledInput placeholder={"Search..."} searchQ={searchQ} onSearchChange={onSearchChange} />
        <select value={sort} onChange={e => onSortChange(e.target.value)}
          style={{
            background: T.surface, border: `1px solid ${T.borderL}`,
            borderRadius: 4, padding: "4px", color: T.text, fontSize: 12,
            fontFamily: T.font, cursor: "pointer"
          }}>
          <option value="frequency">Freq</option>
          <option value="alpha">A-Z</option>
        </select>
      </div>
      {/* POS filter chips */}
      <div style={{
        padding: "4px 8px", borderBottom: `1px solid ${T.border}`,
        display: "flex", flexWrap: "wrap", gap: 3
      }}>
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
              padding: "6px 10px", cursor: "pointer", fontSize: 17,
              background: selectedId === w.id ? T.goldGlow : "transparent",
              borderLeft: selectedId === w.id ? `3px solid ${T.gold}` : "3px solid transparent",
            }}>
            <span style={{
              fontFamily: T.font,
              color: selectedId === w.id ? T.gold : T.bright,
              fontWeight: selectedId === w.id ? 700 : 400,
              flex: 1, minWidth: 0, wordBreak: "break-word",
            }}>{w.lemma}</span>
            <span style={{ fontSize: 13, color: POS_CLR[w.pos] || T.dim, flexShrink: 0 }}>{w.pos}</span>
            <span style={{ fontSize: 13, color: T.dim, fontFamily: T.mono, flexShrink: 0 }}>
              {w.work_freq || w.total_occurrences}</span>
          </div>
        ))}
        {!loading && vocab.length === 0 && (
          <div style={{ padding: 16, textAlign: "center", color: T.dim, fontSize: 14, fontStyle: "italic" }}>
            Select works to see vocabulary</div>
        )}
      </div>
      <div style={{
        padding: "4px 10px", borderTop: `1px solid ${T.border}`, fontSize: 12, color: T.dim, flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "space-between"
      }}>
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
function FamilyTree({ family, selectedWord, detailWord, onSelectMember, onNodeAction, onReparent, linkedFamilies, width, height }) {
  const svgRef = useRef(null);
  const zoomRef = useRef(null);
  const [expandedCrossIds, setExpandedCrossIds] = useState(new Set()); // member IDs whose linked families are expanded
  const [showExplicitLinked, setShowExplicitLinked] = useState(false); // root badge: toggle explicit linked families

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

    // Build set of member IDs that belong to other families (for badge icon)
    const crossFamilyIds = new Set();
    (linkedFamilies || []).forEach(lf => {
      (lf.shared_members || []).forEach(id => crossFamilyIds.add(id));
    });

    // Track all drawn node groups for drag-and-drop targeting
    const drawnNodes = []; // { ng, m, x, y, scale, fId }

    // ── Draw a node at given position and scale ──
    const drawNode = (parent, x, y, m, isRoot, scale, fId) => {
      if (scale <= 0) return; // hidden
      if (!fId) fId = family.id;

      const ng = parent.append("g")
        .attr("transform", `translate(${x},${y})`)
        .style("cursor", "pointer");

      drawnNodes.push({ ng, m, x, y, scale, fId });

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
        ng.append("rect").attr("x", -w / 2 - 6).attr("y", -h / 2 - 6)
          .attr("width", w + 12).attr("height", h + 12).attr("rx", 14 * scale)
          .attr("fill", T.gold).attr("opacity", .12);
      }
      if (isDetail && !isSel) {
        ng.append("rect").attr("x", -w / 2 - 4).attr("y", -h / 2 - 4)
          .attr("width", w + 8).attr("height", h + 8).attr("rx", 12 * scale)
          .attr("fill", T.blue).attr("opacity", .1);
      }

      ng.append("rect").attr("x", -w / 2).attr("y", -h / 2)
        .attr("width", w).attr("height", h).attr("rx", 8 * scale)
        .attr("fill", isRoot ? T.raised : T.surface)
        .attr("stroke", isSel ? T.gold : (isRoot ? T.gold : clr))
        .attr("stroke-width", isSel ? 2 : (isRoot ? 1.5 : .8))
        .attr("stroke-opacity", isSel ? 1 : (isRoot ? .7 : .25));

      if (isRoot) {
        ng.append("text").attr("text-anchor", "middle").attr("y", -h / 2 - 4 * scale)
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
        ng.append("circle").attr("cx", w / 2 + 2).attr("cy", -h / 2 - 2)
          .attr("r", 7).attr("fill", T.gold).attr("opacity", 0.8);
        ng.append("text").attr("x", w / 2 + 2).attr("y", -h / 2 + 1)
          .attr("text-anchor", "middle").attr("fill", T.bg)
          .attr("font-size", "9px").attr("font-weight", 700)
          .attr("font-family", T.mono).text(kidCount);
      }

      // Cross-family badge for members that belong to another family
      if (crossFamilyIds.has(m.id) && fId === family.id) {
        const isExpanded = expandedCrossIds.has(m.id);
        const badge = ng.append("g").style("cursor", "pointer");
        badge.append("circle").attr("cx", -w / 2 - 2).attr("cy", -h / 2 - 2)
          .attr("r", 8).attr("fill", isExpanded ? T.gold : T.blue).attr("opacity", 0.9);
        badge.append("text").attr("x", -w / 2 - 2).attr("y", -h / 2 + 2)
          .attr("text-anchor", "middle").attr("fill", "#fff")
          .attr("font-size", "10px").attr("font-weight", 700)
          .attr("font-family", T.mono).text("⟷");
        badge.on("click", (event) => {
          event.stopPropagation();
          setExpandedCrossIds(prev => {
            const next = new Set(prev);
            if (next.has(m.id)) next.delete(m.id); else next.add(m.id);
            return next;
          });
        });
        badge.on("mouseenter", function () {
          d3.select(this).select("circle").transition().duration(100).attr("r", 10);
        }).on("mouseleave", function () {
          d3.select(this).select("circle").transition().duration(100).attr("r", 8);
        });
      }

      // Root badge for explicit linked families
      if (isRoot && (linkedFamilies || []).some(lf => !lf.shared_members || lf.shared_members.length === 0)) {
        const badge = ng.append("g").style("cursor", "pointer");
        badge.append("circle").attr("cx", -w / 2 - 2).attr("cy", -h / 2 - 2)
          .attr("r", 8).attr("fill", showExplicitLinked ? T.gold : T.blue).attr("opacity", 0.9);
        badge.append("text").attr("x", -w / 2 - 2).attr("y", -h / 2 + 2)
          .attr("text-anchor", "middle").attr("fill", "#fff")
          .attr("font-size", "10px").attr("font-weight", 700)
          .attr("font-family", T.mono).text("⟷");
        badge.on("click", (event) => {
          event.stopPropagation();
          setShowExplicitLinked(prev => !prev);
        });
        badge.on("mouseenter", function () {
          d3.select(this).select("circle").transition().duration(100).attr("r", 10);
        }).on("mouseleave", function () {
          d3.select(this).select("circle").transition().duration(100).attr("r", 8);
        });
      }

      ng.on("mouseenter", function () {
        d3.select(this).select("rect").transition().duration(80)
          .attr("stroke", T.gold).attr("stroke-opacity", 1);
      }).on("mouseleave", function () {
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

    // ── Render linked families (only when badge is clicked) ──
    const linkedOffsets = []; // track bounding for auto-fit
    const activeLinked = (linkedFamilies || []).filter(lf => {
      // Shared-member families: show if any shared member's badge is expanded
      if (lf.shared_members && lf.shared_members.length > 0) {
        return lf.shared_members.some(sid => expandedCrossIds.has(sid));
      }
      // Explicit linked families: show via root badge
      return showExplicitLinked;
    });
    if (activeLinked.length > 0) {
      // Compute main family's max extent from center
      let mainMaxR = ring1Radius + nW / 2 + 30;
      posMap.forEach((pos) => {
        const dist = Math.sqrt(pos.x * pos.x + pos.y * pos.y) + nW;
        if (dist > mainMaxR) mainMaxR = dist;
      });

      activeLinked.forEach((lf, li) => {
        if (!lf.members || lf.members.length === 0) return;

        // Build linked family tree first so we know its size
        const lMembers = [...lf.members];
        let lRootIdx = lMembers.findIndex(m => m.relation === "root" && m.total_occurrences === Math.max(...lMembers.filter(x => x.relation === "root").map(x => x.total_occurrences)));
        if (lRootIdx < 0) lRootIdx = 0;
        const lRoot = lMembers[lRootIdx];
        const lOthers = lMembers.filter((_, i) => i !== lRootIdx);

        const lMemberById = new Map(lMembers.map(m => [m.id, m]));
        const lChildrenOf = new Map();
        lOthers.forEach(m => {
          const pid = (m.parent_lemma_id && lMemberById.has(m.parent_lemma_id)) ? m.parent_lemma_id : lRoot.id;
          if (!lChildrenOf.has(pid)) lChildrenOf.set(pid, []);
          lChildrenOf.get(pid).push(m);
        });

        const lRing1 = lChildrenOf.get(lRoot.id) || [];
        const lRing1Radius = Math.max(lRing1.length * (nW * 0.3 + gap * 0.6) / (2 * Math.PI), 130);

        // Place linked family in the direction of the shared member relative to center
        const linkedR = lRing1Radius + nW + 60;
        const separation = mainMaxR + linkedR + 100;
        // Find the shared member's position to determine direction
        let dirAngle = li * (Math.PI * 0.4) - ((activeLinked.length - 1) * Math.PI * 0.2); // fallback spread
        if (lf.shared_members && lf.shared_members.length > 0) {
          for (const sid of lf.shared_members) {
            const sp = posMap.get(sid);
            if (sp && (sp.x !== 0 || sp.y !== 0)) {
              dirAngle = Math.atan2(sp.y, sp.x);
              break;
            }
          }
        }
        const offsetX = Math.cos(dirAngle) * separation;
        const offsetY = Math.sin(dirAngle) * separation;

        // Position linked nodes
        const lPosMap = new Map();
        lPosMap.set(lRoot.id, { x: offsetX, y: offsetY });

        lRing1.forEach((m, i) => {
          const angle = (i / lRing1.length) * 2 * Math.PI - Math.PI / 2;
          lPosMap.set(m.id, { x: offsetX + Math.cos(angle) * lRing1Radius, y: offsetY + Math.sin(angle) * lRing1Radius });
        });

        // Find shared members: use API-provided shared_members, or detect from overlapping member lists
        const mainMemberIds = new Set((family.members || []).map(m => m.id));
        const linkedMemberIds = new Set(lMembers.map(m => m.id));
        const sharedIds = (lf.shared_members && lf.shared_members.length > 0)
          ? lf.shared_members.filter(sid => mainMemberIds.has(sid) && linkedMemberIds.has(sid))
          : lMembers.filter(m => mainMemberIds.has(m.id)).map(m => m.id);

        if (sharedIds.length > 0) {
          // Draw bridge lines through shared members
          sharedIds.forEach(sid => {
            const mainPos = posMap.get(sid);
            const linkedPos = lPosMap.get(sid);
            if (!mainPos || !linkedPos) return;
            g.append("line")
              .attr("x1", mainPos.x).attr("y1", mainPos.y)
              .attr("x2", linkedPos.x).attr("y2", linkedPos.y)
              .attr("stroke", T.gold).attr("stroke-width", 2.5)
              .attr("stroke-dasharray", "8,6").attr("opacity", 0.6);
            // Label at midpoint
            const mx = (mainPos.x + linkedPos.x) / 2, my = (mainPos.y + linkedPos.y) / 2;
            const sharedMember = lMembers.find(m => m.id === sid);
            g.append("text").attr("x", mx).attr("y", my - 8)
              .attr("text-anchor", "middle").attr("fill", T.gold)
              .attr("font-size", "10px").attr("font-family", T.mono)
              .attr("font-weight", 700).attr("opacity", 0.8)
              .text(sharedMember ? sharedMember.lemma : "shared");
          });
        } else {
          // Fallback: bridge from main root to linked root
          g.append("line")
            .attr("x1", 0).attr("y1", 0)
            .attr("x2", offsetX).attr("y2", offsetY)
            .attr("stroke", T.gold).attr("stroke-width", 2)
            .attr("stroke-dasharray", "8,6").attr("opacity", 0.4);
        }

        // Bridge label
        const mx = offsetX / 2, my = offsetY / 2;
        g.append("text").attr("x", mx).attr("y", my - (sharedIds.length > 0 ? 20 : 8))
          .attr("text-anchor", "middle").attr("fill", T.goldDim)
          .attr("font-size", "10px").attr("font-family", T.mono)
          .attr("font-weight", 600).attr("opacity", 0.7)
          .text(lf.link_type || "related");
        if (lf.note) {
          g.append("text").attr("x", mx).attr("y", my + (sharedIds.length > 0 ? -6 : 8))
            .attr("text-anchor", "middle").attr("fill", T.dim)
            .attr("font-size", "9px").attr("font-family", T.font)
            .attr("font-style", "italic").attr("opacity", 0.6)
            .text(lf.note);
        }

        // Draw linked connections
        lOthers.forEach(m => {
          const pos = lPosMap.get(m.id);
          if (!pos) return;
          const pid = (m.parent_lemma_id && lMemberById.has(m.parent_lemma_id)) ? m.parent_lemma_id : lRoot.id;
          const parentPos = lPosMap.get(pid) || { x: offsetX, y: offsetY };

          g.append("line")
            .attr("x1", parentPos.x).attr("y1", parentPos.y)
            .attr("x2", pos.x).attr("y2", pos.y)
            .attr("stroke", T.border).attr("stroke-width", 0.8)
            .attr("stroke-dasharray", "4,4").attr("opacity", 0.35);
        });

        // Draw linked nodes
        lOthers.forEach(m => {
          const pos = lPosMap.get(m.id);
          if (pos) drawNode(g, pos.x, pos.y, m, false, 0.75, lf.id);
        });
        // Linked root
        drawNode(g, offsetX, offsetY, lRoot, true, 0.85, lf.id);

        // Track for auto-fit
        lPosMap.forEach(pos => linkedOffsets.push(pos));
      });
    }

    // ── Drag-and-drop (superuser only) ──
    // Requires minimum 30px drag distance to prevent accidental reparenting on clicks
    if (onReparent) {
      const MIN_DRAG_PX = 30;
      drawnNodes.forEach(({ ng, m, x, y, fId }) => {
        let dragLine = null;
        let startScreenX, startScreenY, dragging = false;
        ng.call(d3.drag()
          .on("start", function (event) {
            event.sourceEvent.stopPropagation();
            startScreenX = event.sourceEvent.clientX;
            startScreenY = event.sourceEvent.clientY;
            dragging = false;
          })
          .on("drag", function (event) {
            const dx = event.sourceEvent.clientX - startScreenX;
            const dy = event.sourceEvent.clientY - startScreenY;
            if (!dragging && Math.hypot(dx, dy) < MIN_DRAG_PX) return; // not yet a real drag
            if (!dragging) {
              // Start the drag line now
              dragging = true;
              const t = d3.zoomTransform(svg.node());
              dragLine = svg.append("line")
                .attr("stroke", T.gold).attr("stroke-width", 2)
                .attr("stroke-dasharray", "6,4").attr("opacity", 0.7)
                .attr("x1", t.applyX(x)).attr("y1", t.applyY(y))
                .attr("x2", event.sourceEvent.offsetX).attr("y2", event.sourceEvent.offsetY);
            }
            if (dragLine) dragLine.attr("x2", event.sourceEvent.offsetX).attr("y2", event.sourceEvent.offsetY);
          })
          .on("end", function (event) {
            if (dragLine) dragLine.remove();
            if (!dragging) return; // was just a click, not a drag
            // Find closest node to drop point
            const t = d3.zoomTransform(svg.node());
            const dropX = t.invertX(event.sourceEvent.offsetX);
            const dropY = t.invertY(event.sourceEvent.offsetY);
            let closest = null, closestDist = Infinity;
            drawnNodes.forEach(n => {
              if (n.m.id === m.id) return;
              const dist = Math.hypot(n.x - dropX, n.y - dropY);
              if (dist < closestDist) { closestDist = dist; closest = n; }
            });
            if (!closest || closestDist > nW * 1.5) return; // too far — ignore

            const isCross = closest.fId !== fId;
            const action = isCross ? "Move" : "Reparent";
            const msg = `${action} "${m.lemma}" → under "${closest.m.lemma}"${isCross ? " (different family)" : ""}?`;
            if (!window.confirm(msg)) return;

            if (!isCross) {
              onReparent(m.id, closest.m.id, fId);
            } else {
              onReparent(m.id, closest.m.id, fId, closest.fId);
            }
          })
        );
      });
    }

    // Auto-fit
    if (zoomRef.current) {
      let maxR = ring1Radius + nW / 2 + 30;
      if (focusId) {
        posMap.forEach((pos) => {
          const dist = Math.sqrt(pos.x * pos.x + pos.y * pos.y);
          if (dist + nW / 2 + 30 > maxR) maxR = dist + nW / 2 + 30;
        });
      }
      // Include linked families in fit
      let minX = -maxR, maxX = maxR, minY = -maxR, maxY = maxR;
      linkedOffsets.forEach(pos => {
        minX = Math.min(minX, pos.x - nW);
        maxX = Math.max(maxX, pos.x + nW);
        minY = Math.min(minY, pos.y - nH);
        maxY = Math.max(maxY, pos.y + nH);
      });
      const totalW = maxX - minX + 80;
      const totalH = maxY - minY + 80;
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;
      const fitScale = Math.min(width / totalW, height / totalH, 1);
      const t = d3.zoomIdentity.translate(width / 2 - cx * fitScale, height / 2 - cy * fitScale).scale(fitScale);
      svg.call(zoomRef.current.transform, t);
    }

  }, [family, selectedWord, detailWord, linkedFamilies, width, height, onSelectMember, onNodeAction, expandedCrossIds, showExplicitLinked]);

  // Always render the SVG so zoom bindings persist.
  // Overlay the placeholder when there's no family.
  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <svg ref={svgRef} width={width} height={height}
        style={{ position: "absolute", top: 0, left: 0, display: "block", background: T.bg }} />
      {!family && (
        <div style={{
          position: "absolute", inset: 0, display: "flex", alignItems: "center",
          justifyContent: "center", flexDirection: "column", gap: 8, pointerEvents: "none"
        }}>
          <div style={{ fontSize: 32, opacity: .1 }}>&#x27E1;</div>
          <div style={{ color: T.dim, fontSize: 15, fontFamily: T.font }}>
            Select a word to see its derivational family</div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   SENTENCES TAB (inside FormsPanel)
   ═══════════════════════════════════════════════════ */
function SentencesTab({ lemmaId, lemma, works, activeWorkId }) {
  const [sentence, setSentence] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);

  const loadSentence = useCallback((off) => {
    if (!lemmaId || !activeWorkId) return;
    setLoading(true);
    fetch(`${API}/lemma/${lemmaId}/sentences?work_id=${activeWorkId}&limit=1&offset=${off}`)
      .then(r => r.json())
      .then(d => {
        setTotal(d.total || 0);
        if (d.sentences?.length > 0) { setSentence(d.sentences[0]); setError(null); }
        else setError("No sentence found for this lemma in the selected work.");
      })
      .catch(() => setError("Failed to load sentence."))
      .finally(() => setLoading(false));
  }, [lemmaId, activeWorkId]);

  // Auto-load first sentence when lemma or work changes
  useEffect(() => {
    setSentence(null);
    setError(null);
    setOffset(0);
    setTotal(0);
    if (!lemmaId || !activeWorkId) {
      setError("Select a work on the left to see an example sentence.");
      return;
    }
    loadSentence(0);
  }, [lemmaId, activeWorkId, loadSentence]);

  const nextSentence = () => {
    const next = (offset + 1) % total; // cycle back to 0
    setOffset(next);
    loadSentence(next);
  };

  if (loading) return <div style={{ color: T.dim, fontSize: 13, paddingTop: 8 }}>Loading...</div>;

  if (error) return <div style={{ color: T.dim, fontSize: 13, fontStyle: "italic", paddingTop: 8 }}>{error}</div>;

  if (!sentence) return null;

  return (
    <div style={{ paddingTop: 6 }}>
      <div style={{ fontSize: 11, color: T.goldDim, letterSpacing: 0.5, marginBottom: 4 }}>
        {sentence.work_author}, <em>{sentence.work_title}</em> {sentence.passage && `(${sentence.passage})`}
      </div>
      <div style={{ fontSize: 19, color: T.bright, fontFamily: T.font, lineHeight: 1.7 }}>
        {sentence.text}
      </div>
      {total > 1 && (
        <button onClick={nextSentence}
          style={{
            marginTop: 8, padding: "5px 12px", background: T.raised, color: T.gold,
            border: `1px solid ${T.border}`, borderRadius: 4, fontSize: 11, fontFamily: T.font,
            cursor: "pointer"
          }}>
          Another sentence ({offset + 1}/{total})
        </button>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   FORMS / DETAIL PANEL
   ═══════════════════════════════════════════════════ */
function FormsPanel({ lemmaId, workId, scope, language }) {
  const activeWorkId = scope === "work" && workId ? workId : null;
  // we need to relocate all of these to some 'api' file/directory
  // this is not scalable
  // why? this tightly couples logic unpacking whatever was returned from the api to component level code
  // ideally, we'd have types and autocomplete and all of that joy coming from those api files
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
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      height: "100%", color: T.dim, fontSize: 14, fontStyle: "italic", padding: 16, textAlign: "center"
    }}>
      Click a word to see details</div>
  );
  if (loading) return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      height: "100%", color: T.dim
    }}>Loading...</div>
  );
  if (!data) return null;

  let tabs = [
    { id: "forms", label: "Forms", n: data.forms?.length || 0 },
    { id: "works", label: "Works", n: data.top_works?.length || 0 },
    { id: "defs", label: "Defs", n: data.definitions?.length || 0 },
    { id: "sents", label: "Sents" },
    { id: "production", label: "Pronounce" },
  ];

  if (ELIDE_SPEECH_TRAINING) {
    tabs = [
      { id: "forms", label: "Forms", n: data.forms?.length || 0 },
      { id: "works", label: "Works", n: data.top_works?.length || 0 },
      { id: "defs", label: "Defs", n: data.definitions?.length || 0 },
      { id: "sents", label: "Sents" },
    ];
  }

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
                <div style={{
                  fontSize: 11, color: T.goldDim, letterSpacing: 1, marginBottom: 3,
                  textTransform: "uppercase"
                }}>{group}</div>
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
          <div key={i} style={{
            display: "flex", alignItems: "baseline", gap: 6, padding: "3px 0",
            borderBottom: `1px solid ${T.border}`
          }}>
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

        {tab === "sents" && <SentencesTab lemmaId={lemmaId} lemma={data.lemma} works={data.top_works} activeWorkId={activeWorkId || workId} />}
        {tab === "production" && <ProductionTraining language={2} toPronounce={data.lemma} />}
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
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center"
    }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8,
        width: 420, maxHeight: "70vh", display: "flex", flexDirection: "column",
        boxShadow: "0 8px 32px rgba(0,0,0,.5)",
      }}>
        {/* Header */}
        <div style={{
          padding: "10px 14px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between"
        }}>
          <span style={{ fontSize: 14, color: T.gold, fontWeight: 600 }}>Add Word to Family</span>
          <button onClick={onClose} style={{
            background: "none", border: "none",
            color: T.dim, cursor: "pointer", fontSize: 18, padding: 0
          }}>x</button>
        </div>

        {/* Search */}
        <div style={{ padding: "8px 14px", display: "flex", gap: 6 }}>
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && doSearch()}
            placeholder="Search lemma or definition..."
            style={{
              flex: 1, background: T.bg, border: `1px solid ${T.borderL}`,
              borderRadius: 4, padding: "6px 8px", color: T.text, fontSize: 14,
              fontFamily: T.font, outline: "none"
            }} autoFocus />
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
              <span style={{
                fontSize: 12, color: T.dim, fontStyle: "italic", flex: 1,
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap"
              }}>{r.short_def}</span>
            </div>
          ))}
          {searching && <div style={{ padding: 12, color: T.dim, fontSize: 13, textAlign: "center" }}>Searching...</div>}
        </div>

        {/* Relation picker + action */}
        {selected && !conflict && (
          <div style={{
            padding: "8px 14px", borderTop: `1px solid ${T.border}`,
            display: "flex", flexDirection: "column", gap: 6
          }}>
            <div style={{ fontSize: 12, color: T.dim }}>
              Adding <strong style={{ color: T.bright }}>{selected.lemma}</strong> to <strong style={{ color: T.gold }}>{familyLabel}</strong>
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <select value={useCustom ? "__custom__" : relation}
                onChange={e => {
                  if (e.target.value === "__custom__") setUseCustom(true);
                  else { setUseCustom(false); setRelation(e.target.value); }
                }}
                style={{
                  background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 4,
                  padding: "4px 6px", color: T.text, fontSize: 13, fontFamily: T.font, flex: 1
                }}>
                {RELATION_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
                <option value="__custom__">Custom...</option>
              </select>
              {useCustom && (
                <input value={customRel} onChange={e => setCustomRel(e.target.value)}
                  placeholder="Custom relation..."
                  style={{
                    background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 4,
                    padding: "4px 6px", color: T.text, fontSize: 13, fontFamily: T.font, flex: 1
                  }} />
              )}
            </div>
            {/* Parent picker */}
            {familyMembers?.length > 0 && (
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 12, color: T.dim, flexShrink: 0 }}>Derives from:</span>
                <select value={parentLemmaId} onChange={e => setParentLemmaId(e.target.value)}
                  style={{
                    background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 4,
                    padding: "4px 6px", color: T.text, fontSize: 13, fontFamily: T.font, flex: 1
                  }}>
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
          <div style={{
            padding: "10px 14px", borderTop: `1px solid ${T.border}`,
            display: "flex", flexDirection: "column", gap: 6
          }}>
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
function NodeActionPopover({ member, familyId, familyMembers, familyRootId, x, y, onClose, onDone }) {
  const [editingRel, setEditingRel] = useState(false);
  const [editingParent, setEditingParent] = useState(false);
  const [editingDef, setEditingDef] = useState(false);
  const [mergingLemma, setMergingLemma] = useState(false);
  const [addingToFamily, setAddingToFamily] = useState(false);
  const [relation, setRelation] = useState(member.relation || "derived");
  const [parentLemmaId, setParentLemmaId] = useState(member.parent_lemma_id || "");
  const [shortDef, setShortDef] = useState(member.short_def || "");
  const [pos, setPos] = useState(member.pos || "");
  const [mergeSearch, setMergeSearch] = useState("");
  const [mergeResults, setMergeResults] = useState([]);
  const [mergeTarget, setMergeTarget] = useState(null);
  const [familySearch, setFamilySearch] = useState("");
  const [familySearchResults, setFamilySearchResults] = useState([]);
  const [targetFamily, setTargetFamily] = useState(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [confirmSplit, setConfirmSplit] = useState(false);
  const [splitting, setSplitting] = useState(false);

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

  const doSplit = () => {
    setSplitting(true);
    fetch(`${API}/family/${familyId}/split/${member.id}`, { method: "POST" })
      .then(r => { if (r.ok) { onDone(); onClose(); } else setSplitting(false); })
      .catch(() => setSplitting(false));
  };

  const doUpdateDef = () => {
    fetch(`${API}/lemma/${member.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ short_def: shortDef, pos }),
    }).then(r => { if (r.ok) { onDone(); onClose(); } });
  };

  const doMergeSearch = (q) => {
    setMergeSearch(q);
    if (q.trim().length < 2) { setMergeResults([]); return; }
    fetch(`${API}/search?q=${encodeURIComponent(q.trim())}&limit=10`)
      .then(r => r.json())
      .then(d => setMergeResults((d.results || []).filter(r => r.id !== member.id)))
      .catch(() => setMergeResults([]));
  };

  const doMergeLemma = () => {
    if (!mergeTarget) return;
    if (!window.confirm(`Merge "${mergeTarget.lemma}" (id:${mergeTarget.id}) INTO "${member.lemma}" (id:${member.id})? This will delete "${mergeTarget.lemma}" and move all its forms/occurrences.`)) return;
    fetch(`${API}/lemma/${member.id}/merge/${mergeTarget.id}`, { method: "POST" })
      .then(r => { if (r.ok) { onDone(); onClose(); } });
  };

  const doFamilySearch = (q) => {
    setFamilySearch(q);
    if (q.trim().length < 2) { setFamilySearchResults([]); return; }
    fetch(`${API}/family/search?q=${encodeURIComponent(q.trim())}&limit=10`)
      .then(r => r.json())
      .then(d => setFamilySearchResults((d.results || []).filter(r => r.id !== familyId)))
      .catch(() => setFamilySearchResults([]));
  };

  const doAddToFamily = () => {
    if (!targetFamily) return;
    fetch(`${API}/family/${targetFamily.id}/add-member?allow_multi=1`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lemma_id: member.id, relation: "derived" }),
    }).then(r => { if (r.ok) { onDone(); onClose(); } });
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

        {!editingRel && !editingParent && !editingDef && !mergingLemma && !addingToFamily && !confirmRemove && !confirmSplit && (
          <>
            <button onClick={() => setEditingDef(true)} style={{
              display: "block", width: "100%", textAlign: "left", background: "none",
              border: "none", padding: "4px 6px", color: T.text, fontSize: 13,
              cursor: "pointer", borderRadius: 3,
            }}
              onMouseEnter={e => e.currentTarget.style.background = T.hover}
              onMouseLeave={e => e.currentTarget.style.background = "none"}>
              Edit Definition
            </button>
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
            <button onClick={() => setMergingLemma(true)} style={{
              display: "block", width: "100%", textAlign: "left", background: "none",
              border: "none", padding: "4px 6px", color: T.text, fontSize: 13,
              cursor: "pointer", borderRadius: 3,
            }}
              onMouseEnter={e => e.currentTarget.style.background = T.hover}
              onMouseLeave={e => e.currentTarget.style.background = "none"}>
              Merge Duplicate Lemma
            </button>
            <button onClick={() => setAddingToFamily(true)} style={{
              display: "block", width: "100%", textAlign: "left", background: "none",
              border: "none", padding: "4px 6px", color: T.text, fontSize: 13,
              cursor: "pointer", borderRadius: 3,
            }}
              onMouseEnter={e => e.currentTarget.style.background = T.hover}
              onMouseLeave={e => e.currentTarget.style.background = "none"}>
              Add to Another Family
            </button>
            {member.id !== familyRootId && (
              <button onClick={() => setConfirmSplit(true)} style={{
                display: "block", width: "100%", textAlign: "left", background: "none",
                border: "none", padding: "4px 6px", color: T.blue, fontSize: 13,
                cursor: "pointer", borderRadius: 3,
              }}
                onMouseEnter={e => e.currentTarget.style.background = T.hover}
                onMouseLeave={e => e.currentTarget.style.background = "none"}>
                Split to Linked Family
              </button>
            )}
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
              style={{
                background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 3,
                padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font
              }}>
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
              style={{
                background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 3,
                padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font
              }}>
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

        {confirmSplit && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontSize: 12, color: T.dim }}>
              Split <strong>{member.lemma}</strong> and its children into a new linked family?
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={doSplit} disabled={splitting} style={{
                flex: 1, background: T.blue, border: "none", borderRadius: 3, padding: "4px 0",
                color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer",
              }}>{splitting ? "Splitting..." : "Split"}</button>
              <button onClick={() => setConfirmSplit(false)} style={{
                flex: 1, background: T.raised, border: `1px solid ${T.border}`, borderRadius: 3,
                padding: "4px 0", color: T.text, fontSize: 12, cursor: "pointer",
              }}>Cancel</button>
            </div>
          </div>
        )}

        {editingDef && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontSize: 12, color: T.dim }}>Definition:</div>
            <input value={shortDef} onChange={e => setShortDef(e.target.value)}
              placeholder="Short definition"
              style={{
                background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 3,
                padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font
              }} />
            <div style={{ fontSize: 12, color: T.dim }}>POS:</div>
            <input value={pos} onChange={e => setPos(e.target.value)}
              placeholder="Part of speech"
              style={{
                background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 3,
                padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font
              }} />
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={doUpdateDef} style={{
                flex: 1, background: T.gold, border: "none", borderRadius: 3, padding: "4px 0",
                color: T.bg, fontSize: 12, fontWeight: 600, cursor: "pointer",
              }}>Save</button>
              <button onClick={() => setEditingDef(false)} style={{
                flex: 1, background: T.raised, border: `1px solid ${T.border}`, borderRadius: 3,
                padding: "4px 0", color: T.text, fontSize: 12, cursor: "pointer",
              }}>Cancel</button>
            </div>
          </div>
        )}

        {mergingLemma && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontSize: 12, color: T.dim }}>Search for duplicate lemma to merge into <strong>{member.lemma}</strong>:</div>
            <input value={mergeSearch} onChange={e => doMergeSearch(e.target.value)}
              placeholder="Type lemma to search..."
              autoFocus
              style={{
                background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 3,
                padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font
              }} />
            {mergeResults.length > 0 && (
              <div style={{
                maxHeight: 150, overflowY: "auto", border: `1px solid ${T.border}`,
                borderRadius: 3, background: T.bg
              }}>
                {mergeResults.map(r => (
                  <div key={r.id} onClick={() => setMergeTarget(r)}
                    style={{
                      padding: "3px 6px", fontSize: 12, cursor: "pointer",
                      color: mergeTarget?.id === r.id ? T.gold : T.text,
                      background: mergeTarget?.id === r.id ? T.hover : "none",
                    }}
                    onMouseEnter={e => { if (mergeTarget?.id !== r.id) e.currentTarget.style.background = T.hover; }}
                    onMouseLeave={e => { if (mergeTarget?.id !== r.id) e.currentTarget.style.background = "none"; }}>
                    {r.lemma} <span style={{ color: T.dim }}>({r.pos || "?"}) — {r.short_def || "no def"}</span>
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={doMergeLemma} disabled={!mergeTarget} style={{
                flex: 1, background: mergeTarget ? T.red : T.raised, border: "none", borderRadius: 3,
                padding: "4px 0", color: mergeTarget ? "#fff" : T.dim, fontSize: 12, fontWeight: 600,
                cursor: mergeTarget ? "pointer" : "default",
              }}>Merge</button>
              <button onClick={() => { setMergingLemma(false); setMergeSearch(""); setMergeResults([]); setMergeTarget(null); }} style={{
                flex: 1, background: T.raised, border: `1px solid ${T.border}`, borderRadius: 3,
                padding: "4px 0", color: T.text, fontSize: 12, cursor: "pointer",
              }}>Cancel</button>
            </div>
          </div>
        )}

        {addingToFamily && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontSize: 12, color: T.dim }}>Add <strong>{member.lemma}</strong> to another family:</div>
            <input value={familySearch} onChange={e => doFamilySearch(e.target.value)}
              placeholder="Search families by root..."
              autoFocus
              style={{
                background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 3,
                padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font
              }} />
            {familySearchResults.length > 0 && (
              <div style={{
                maxHeight: 150, overflowY: "auto", border: `1px solid ${T.border}`,
                borderRadius: 3, background: T.bg
              }}>
                {familySearchResults.map(r => (
                  <div key={r.id} onClick={() => setTargetFamily(r)}
                    style={{
                      padding: "3px 6px", fontSize: 12, cursor: "pointer",
                      color: targetFamily?.id === r.id ? T.gold : T.text,
                      background: targetFamily?.id === r.id ? T.hover : "none",
                    }}
                    onMouseEnter={e => { if (targetFamily?.id !== r.id) e.currentTarget.style.background = T.hover; }}
                    onMouseLeave={e => { if (targetFamily?.id !== r.id) e.currentTarget.style.background = "none"; }}>
                    {r.label || r.root} <span style={{ color: T.dim }}>({r.member_count || "?"} members)</span>
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={doAddToFamily} disabled={!targetFamily} style={{
                flex: 1, background: targetFamily ? T.blue : T.raised, border: "none", borderRadius: 3,
                padding: "4px 0", color: targetFamily ? "#fff" : T.dim, fontSize: 12, fontWeight: 600,
                cursor: targetFamily ? "pointer" : "default",
              }}>Add</button>
              <button onClick={() => { setAddingToFamily(false); setFamilySearch(""); setFamilySearchResults([]); setTargetFamily(null); }} style={{
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
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center"
    }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8,
        width: 420, maxHeight: "70vh", display: "flex", flexDirection: "column",
        boxShadow: "0 8px 32px rgba(0,0,0,.5)",
      }}>
        <div style={{
          padding: "10px 14px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between"
        }}>
          <span style={{ fontSize: 14, color: T.gold, fontWeight: 600 }}>Merge Another Family</span>
          <button onClick={onClose} style={{
            background: "none", border: "none",
            color: T.dim, cursor: "pointer", fontSize: 18, padding: 0
          }}>x</button>
        </div>
        <div style={{ padding: "6px 14px", fontSize: 12, color: T.dim }}>
          Merging into: <strong style={{ color: T.gold }}>{familyLabel}</strong>
        </div>

        <div style={{ padding: "8px 14px", display: "flex", gap: 6 }}>
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && doSearch()}
            placeholder="Search by root, label, or word..."
            style={{
              flex: 1, background: T.bg, border: `1px solid ${T.borderL}`,
              borderRadius: 4, padding: "6px 8px", color: T.text, fontSize: 14,
              fontFamily: T.font, outline: "none"
            }} autoFocus />
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
          <div style={{
            padding: "8px 14px", borderTop: `1px solid ${T.border}`,
            display: "flex", flexDirection: "column", gap: 6
          }}>
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
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center"
    }}
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
            style={{
              width: "100%", background: T.bg, border: `1px solid ${T.borderL}`,
              borderRadius: 4, padding: "6px 8px", color: T.text, fontSize: 15,
              fontFamily: T.font, outline: "none", boxSizing: "border-box"
            }} />
        </div>
        <div>
          <div style={{ fontSize: 11, color: T.dim, marginBottom: 3, letterSpacing: .5 }}>LABEL</div>
          <input value={label} onChange={e => setLabel(e.target.value)}
            style={{
              width: "100%", background: T.bg, border: `1px solid ${T.borderL}`,
              borderRadius: 4, padding: "6px 8px", color: T.text, fontSize: 15,
              fontFamily: T.font, outline: "none", boxSizing: "border-box"
            }} />
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
   SUPERUSER: Edit History Panel
   Shows recent edits with revert capability.
   ═══════════════════════════════════════════════════ */
const ACTION_LABELS = {
  update_lemma: "Edit Lemma",
  add_member: "Add Member",
  remove_member: "Remove Member",
  merge_families: "Merge Families",
  update_member_relation: "Update Relation",
  split_to_linked_family: "Split Family",
  move_member_cross_family: "Move Member",
  update_family: "Rename Family",
  create_link: "Create Link",
  delete_link: "Delete Link",
  unlink_families: "Unlink Families",
  update_member: "Update Member",
  split_family: "Split Family",
  merge: "Merge Families",
  remove_link: "Remove Link",
  create: "Create Family",
};

function formatAction(action) {
  return ACTION_LABELS[action] || action.replace(/_/g, " ");
}

function EditHistoryPanel({ onClose, onRevert }) {
  const [edits, setEdits] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [reverting, setReverting] = useState(null);
  const [offset, setOffset] = useState(0);
  const LIMIT = 30;

  const loadEdits = useCallback((off = 0) => {
    setLoading(true);
    fetch(`${API}/edit-history?limit=${LIMIT}&offset=${off}`)
      .then(r => r.json())
      .then(data => {
        setEdits(data.edits || []);
        setTotal(data.total || 0);
        setOffset(off);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => { loadEdits(0); }, [loadEdits]);

  const doRevert = (editId) => {
    if (!confirm("Revert this edit? This will undo the change.")) return;
    setReverting(editId);
    fetch(`${API}/edit-history/${editId}/revert`, { method: "POST" })
      .then(r => r.json())
      .then(data => {
        setReverting(null);
        if (data.status === "ok") {
          loadEdits(offset);
          if (onRevert) onRevert();
        } else {
          alert(data.error || "Revert failed");
        }
      })
      .catch(() => { setReverting(null); alert("Revert request failed"); });
  };

  const formatTime = (ts) => {
    if (!ts) return "";
    const d = new Date(ts + "Z");
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return "just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  const formatDetail = (edit) => {
    const parts = [];
    if (edit.lemma_name) parts.push(edit.lemma_name);
    if (edit.family_root && !parts.includes(edit.family_root)) parts.push(`family: ${edit.family_root}`);
    const d = edit.detail;
    if (d) {
      if (d.short_def) parts.push(`def: "${d.short_def}"`);
      if (d.relation) parts.push(`rel: ${d.relation}`);
      if (d.merged_from) parts.push(`merged from #${d.merged_from}`);
      if (d.other_family_id) parts.push(`linked #${d.other_family_id}`);
    }
    return parts.join(" · ") || "";
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center"
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8,
        width: 520, maxHeight: "80vh", boxShadow: "0 8px 32px rgba(0,0,0,.5)",
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "12px 16px", borderBottom: `1px solid ${T.border}`,
        }}>
          <span style={{ fontSize: 15, color: T.gold, fontWeight: 600 }}>Edit History</span>
          <span style={{ fontSize: 12, color: T.dim }}>{total} total edits</span>
        </div>

        {/* List */}
        <div style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}>
          {loading ? (
            <div style={{ padding: 20, textAlign: "center", color: T.dim }}>Loading...</div>
          ) : edits.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: T.dim }}>No edits recorded yet</div>
          ) : edits.map(edit => (
            <div key={edit.id} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "8px 16px",
              borderBottom: `1px solid ${T.border}22`,
              background: edit.action.startsWith("revert_") ? "rgba(107,156,107,0.06)" : "transparent",
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{
                    fontSize: 12, fontWeight: 600, color: edit.action.startsWith("revert_") ? T.green : T.text,
                  }}>{formatAction(edit.action)}</span>
                  <span style={{ fontSize: 11, color: T.dim }}>#{edit.id}</span>
                  <span style={{ fontSize: 11, color: T.dim, marginLeft: "auto" }}>{formatTime(edit.timestamp)}</span>
                </div>
                <div style={{
                  fontSize: 11, color: T.dim, marginTop: 2,
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                }}>{formatDetail(edit)}</div>
              </div>
              {edit.reversible && !edit.action.startsWith("revert_") && (
                <button
                  onClick={() => doRevert(edit.id)}
                  disabled={reverting === edit.id}
                  style={{
                    background: T.raised, border: `1px solid ${T.borderL}`, borderRadius: 4,
                    padding: "3px 8px", color: T.gold, fontSize: 11, fontWeight: 600,
                    cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0,
                  }}
                >{reverting === edit.id ? "..." : "Revert"}</button>
              )}
            </div>
          ))}
        </div>

        {/* Pagination + Close */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 16px", borderTop: `1px solid ${T.border}`,
        }}>
          <div style={{ display: "flex", gap: 6 }}>
            {offset > 0 && (
              <button onClick={() => loadEdits(Math.max(0, offset - LIMIT))} style={{
                background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4,
                padding: "4px 10px", color: T.text, fontSize: 12, cursor: "pointer",
              }}>Newer</button>
            )}
            {offset + LIMIT < total && (
              <button onClick={() => loadEdits(offset + LIMIT)} style={{
                background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4,
                padding: "4px 10px", color: T.text, fontSize: 12, cursor: "pointer",
              }}>Older</button>
            )}
          </div>
          <button onClick={onClose} style={{
            background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4,
            padding: "4px 14px", color: T.text, fontSize: 12, cursor: "pointer",
          }}>Close</button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   SUPERUSER: LSJ Review Panel
   Two tabs: Definition review and Family review.
   ═══════════════════════════════════════════════════ */
function LSJReviewPanel({ onClose, onUpdate }) {
  const [tab, setTab] = useState("definitions"); // "definitions" | "families"
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [search, setSearch] = useState("");
  const [missingOnly, setMissingOnly] = useState(false);
  const [actionableOnly, setActionableOnly] = useState(true);
  const [acting, setActing] = useState(null); // id being acted on
  const [editDef, setEditDef] = useState({}); // {id: editedText}
  const LIMIT = 15;

  const loadItems = useCallback((off = 0) => {
    setLoading(true);
    const base = tab === "definitions"
      ? `${API}/lsj/review/definitions?status=pending&limit=${LIMIT}&offset=${off}${missingOnly ? "&missing_only=1" : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`
      : `${API}/lsj/review/families?status=pending&limit=${LIMIT}&offset=${off}${actionableOnly ? "&actionable=1" : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`;
    fetch(base)
      .then(r => r.json())
      .then(data => {
        setItems(data.items || []);
        setTotal(data.total || 0);
        setOffset(off);
        setStats(data.stats || {});
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [tab, missingOnly, actionableOnly, search]);

  useEffect(() => { loadItems(0); }, [loadItems]);

  const doAction = (id, action, body = {}) => {
    setActing(id);
    const url = tab === "definitions"
      ? `${API}/lsj/review/definitions/${id}/${action}`
      : `${API}/lsj/review/families/${id}/${action}`;
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(r => r.json())
      .then(data => {
        setActing(null);
        if (data.status === "ok") {
          loadItems(offset);
          if (onUpdate) onUpdate();
        } else {
          alert(data.error || "Action failed");
        }
      })
      .catch(() => { setActing(null); alert("Request failed"); });
  };

  const tabBtn = (label, value) => (
    <button onClick={() => { setTab(value); setOffset(0); }} style={{
      background: tab === value ? T.gold : T.raised,
      color: tab === value ? T.bg : T.text,
      border: tab === value ? "none" : `1px solid ${T.border}`,
      borderRadius: 4, padding: "4px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
    }}>{label}</button>
  );

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center"
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8,
        width: 680, maxHeight: "85vh", boxShadow: "0 8px 32px rgba(0,0,0,.5)",
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{
          padding: "12px 16px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", gap: 8,
        }}>
          {tabBtn("Definitions", "definitions")}
          {tabBtn("Families", "families")}
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: T.dim }}>
            {tab === "definitions"
              ? `${stats.pending || 0} pending · ${stats.missing || 0} missing`
              : `${stats.actionable || 0} actionable · ${stats.pending || 0} pending`
            }
          </span>
        </div>

        {/* Filters */}
        <div style={{
          padding: "8px 16px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search lemma..."
            style={{
              flex: 1, background: T.bg, border: `1px solid ${T.borderL}`,
              borderRadius: 4, padding: "4px 8px", color: T.text, fontSize: 12,
              fontFamily: T.font, outline: "none",
            }}
            onKeyDown={e => { if (e.key === "Enter") loadItems(0); }}
          />
          {tab === "definitions" && (
            <label style={{ fontSize: 11, color: T.dim, display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
              <input type="checkbox" checked={missingOnly} onChange={e => setMissingOnly(e.target.checked)} />
              Missing only
            </label>
          )}
          {tab === "families" && (
            <label style={{ fontSize: 11, color: T.dim, display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
              <input type="checkbox" checked={actionableOnly} onChange={e => setActionableOnly(e.target.checked)} />
              Actionable only
            </label>
          )}
        </div>

        {/* Items list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}>
          {loading ? (
            <div style={{ padding: 20, textAlign: "center", color: T.dim }}>Loading...</div>
          ) : items.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: T.dim }}>No items to review</div>
          ) : tab === "definitions" ? (
            /* Definition review items */
            items.map(item => (
              <div key={item.id} style={{
                padding: "10px 16px", borderBottom: `1px solid ${T.border}22`,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                  <span style={{ fontSize: 14, fontWeight: 600, color: T.gold, fontFamily: T.font }}>{item.lemma}</span>
                  <span style={{ fontSize: 10, color: T.dim, background: T.raised, padding: "1px 5px", borderRadius: 3 }}>{item.match_type}</span>
                  {item.missing_current_def ? (
                    <span style={{ fontSize: 10, color: T.red, background: "rgba(196,87,74,0.15)", padding: "1px 5px", borderRadius: 3 }}>MISSING DEF</span>
                  ) : null}
                </div>
                <div style={{ fontSize: 12, color: T.dim, marginBottom: 3 }}>
                  <b>Current:</b> {item.current_short_def || <i style={{ color: T.red }}>none</i>}
                </div>
                <div style={{ fontSize: 12, color: T.text, marginBottom: 4 }}>
                  <b>LSJ:</b> {item.lsj_short_def || item.lsj_full_def || <i style={{ color: T.dim }}>no definition</i>}
                </div>
                {/* Editable override */}
                <input
                  value={editDef[item.id] !== undefined ? editDef[item.id] : (item.lsj_short_def || item.lsj_full_def || "")}
                  onChange={e => setEditDef(prev => ({ ...prev, [item.id]: e.target.value }))}
                  style={{
                    width: "100%", background: T.bg, border: `1px solid ${T.borderL}`,
                    borderRadius: 4, padding: "4px 8px", color: T.text, fontSize: 12,
                    fontFamily: T.font, outline: "none", boxSizing: "border-box", marginBottom: 6,
                  }}
                />
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    onClick={() => doAction(item.id, "approve", {
                      definition: editDef[item.id] !== undefined ? editDef[item.id] : undefined
                    })}
                    disabled={acting === item.id}
                    style={{
                      background: T.green, border: "none", borderRadius: 4, padding: "3px 10px",
                      color: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer",
                    }}
                  >{acting === item.id ? "..." : "Approve"}</button>
                  <button
                    onClick={() => doAction(item.id, "reject")}
                    disabled={acting === item.id}
                    style={{
                      background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4, padding: "3px 10px",
                      color: T.dim, fontSize: 11, cursor: "pointer",
                    }}
                  >Skip</button>
                </div>
              </div>
            ))
          ) : (
            /* Family review items */
            items.map(item => (
              <div key={item.id} style={{
                padding: "10px 16px", borderBottom: `1px solid ${T.border}22`,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: T.text, fontFamily: T.font }}>{item.child_headword}</span>
                  <span style={{ fontSize: 11, color: T.dim }}>→</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: T.gold, fontFamily: T.font }}>{item.parent_headword}</span>
                  <span style={{ fontSize: 10, color: T.dim, background: T.raised, padding: "1px 5px", borderRadius: 3 }}>{item.relation_type}</span>
                </div>
                <div style={{ fontSize: 11, color: T.dim, marginBottom: 2 }}>
                  Child: {item.child_lemma_id ? `#${item.child_lemma_id}` : <span style={{ color: T.red }}>not in vocab</span>}
                  {item.child_family ? ` · Family: ${item.child_family.root}` : " · no family"}
                  {" | "}
                  Parent: {item.parent_lemma_id ? `#${item.parent_lemma_id}` : <span style={{ color: T.red }}>not in vocab</span>}
                  {item.parent_family ? ` · Family: ${item.parent_family.root}` : " · no family"}
                </div>
                {item.child_family && item.parent_family && item.child_family.id === item.parent_family.id ? (
                  <div style={{ fontSize: 11, color: T.green, marginBottom: 4 }}>Already in same family</div>
                ) : null}
                <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                  <button
                    onClick={() => doAction(item.id, "approve", { relation: "derived" })}
                    disabled={acting === item.id || !item.child_lemma_id || !item.parent_lemma_id}
                    style={{
                      background: (item.child_lemma_id && item.parent_lemma_id) ? T.green : T.raised,
                      border: "none", borderRadius: 4, padding: "3px 10px",
                      color: "#fff", fontSize: 11, fontWeight: 600,
                      cursor: (item.child_lemma_id && item.parent_lemma_id) ? "pointer" : "not-allowed",
                      opacity: (item.child_lemma_id && item.parent_lemma_id) ? 1 : 0.5,
                    }}
                  >{acting === item.id ? "..." : "Add to Family"}</button>
                  <button
                    onClick={() => doAction(item.id, "reject")}
                    disabled={acting === item.id}
                    style={{
                      background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4, padding: "3px 10px",
                      color: T.dim, fontSize: 11, cursor: "pointer",
                    }}
                  >Skip</button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Pagination + Close */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 16px", borderTop: `1px solid ${T.border}`,
        }}>
          <div style={{ display: "flex", gap: 6 }}>
            {offset > 0 && (
              <button onClick={() => loadItems(Math.max(0, offset - LIMIT))} style={{
                background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4,
                padding: "4px 10px", color: T.text, fontSize: 12, cursor: "pointer",
              }}>Prev</button>
            )}
            {offset + LIMIT < total && (
              <button onClick={() => loadItems(offset + LIMIT)} style={{
                background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4,
                padding: "4px 10px", color: T.text, fontSize: 12, cursor: "pointer",
              }}>Next</button>
            )}
            <span style={{ fontSize: 11, color: T.dim, alignSelf: "center" }}>
              {offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
            </span>
          </div>
          <button onClick={onClose} style={{
            background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4,
            padding: "4px 14px", color: T.text, fontSize: 12, cursor: "pointer",
          }}>Close</button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   SUPERUSER: Link Family Modal
   Search for another family and create a visual link.
   ═══════════════════════════════════════════════════ */
const LINK_TYPES = ["related", "cognate", "compound", "variant", "antonym"];

function LinkFamilyModal({ familyId, familyLabel, onClose, onDone }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState(null);
  const [linkType, setLinkType] = useState("related");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const doSearch = useCallback(() => {
    if (!query.trim()) return;
    setSearching(true);
    fetch(`${API}/family/search?q=${encodeURIComponent(query.trim())}&limit=20`)
      .then(r => r.json()).then(d => {
        setResults((d.results || []).filter(r => r.id !== familyId));
        setSearching(false);
      }).catch(() => setSearching(false));
  }, [query, familyId]);

  const doLink = useCallback(() => {
    if (!selected) return;
    setSaving(true); setError(null);
    fetch(`${API}/family/${familyId}/link/${selected.id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ link_type: linkType, note: note.trim() }),
    }).then(async r => {
      if (r.ok) { onDone(); onClose(); }
      else { const d = await r.json(); setError(d.error || "Link failed"); setSaving(false); }
    }).catch(() => { setError("Network error"); setSaving(false); });
  }, [selected, familyId, linkType, note, onDone, onClose]);

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center"
    }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8,
        width: 420, maxHeight: "70vh", display: "flex", flexDirection: "column",
        boxShadow: "0 8px 32px rgba(0,0,0,.5)",
      }}>
        <div style={{
          padding: "10px 14px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between"
        }}>
          <span style={{ fontSize: 14, color: T.gold, fontWeight: 600 }}>Link Another Family</span>
          <button onClick={onClose} style={{
            background: "none", border: "none",
            color: T.dim, cursor: "pointer", fontSize: 18, padding: 0
          }}>x</button>
        </div>
        <div style={{ padding: "6px 14px", fontSize: 12, color: T.dim }}>
          Linking to: <strong style={{ color: T.gold }}>{familyLabel}</strong>
        </div>

        <div style={{ padding: "8px 14px", display: "flex", gap: 6 }}>
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && doSearch()}
            placeholder="Search by root, label, or word..."
            style={{
              flex: 1, background: T.bg, border: `1px solid ${T.borderL}`,
              borderRadius: 4, padding: "6px 8px", color: T.text, fontSize: 14,
              fontFamily: T.font, outline: "none"
            }} autoFocus />
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
          <div style={{
            padding: "8px 14px", borderTop: `1px solid ${T.border}`,
            display: "flex", flexDirection: "column", gap: 6
          }}>
            <div style={{ fontSize: 12, color: T.dim }}>
              Link <strong style={{ color: T.bright }}>{selected.label}</strong> ({selected.member_count} words) to <strong style={{ color: T.gold }}>{familyLabel}</strong>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: T.dim, marginBottom: 2 }}>Link type</div>
                <select value={linkType} onChange={e => setLinkType(e.target.value)}
                  style={{
                    width: "100%", background: T.bg, border: `1px solid ${T.borderL}`,
                    borderRadius: 3, padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font
                  }}>
                  {LINK_TYPES.map(lt => <option key={lt} value={lt}>{lt}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: T.dim, marginBottom: 2 }}>Note (optional)</div>
                <input value={note} onChange={e => setNote(e.target.value)}
                  style={{
                    width: "100%", background: T.bg, border: `1px solid ${T.borderL}`,
                    borderRadius: 3, padding: "3px 5px", color: T.text, fontSize: 12,
                    fontFamily: T.font, outline: "none", boxSizing: "border-box"
                  }} />
              </div>
            </div>
            {error && <div style={{ fontSize: 12, color: T.red }}>{error}</div>}
            <button onClick={doLink} disabled={saving} style={{
              background: T.gold, border: "none", borderRadius: 4, padding: "6px 0",
              color: T.bg, fontSize: 13, fontWeight: 600, cursor: "pointer",
            }}>{saving ? "Linking..." : "Link Families"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   SUPERUSER: Inline Search Bar
   ═══════════════════════════════════════════════════ */
function SuperuserSearch({ familyId, familyMembers, onDone }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(null); // word to add
  const [relation, setRelation] = useState("derived");
  const [parentLemmaId, setParentLemmaId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [conflict, setConflict] = useState(null);
  const [mode, setMode] = useState("words"); // "words" | "families"
  const timerRef = useRef(null);
  const wrapRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) { setOpen(false); setSelected(null); } };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Debounced search as user types
  useEffect(() => {
    clearTimeout(timerRef.current);
    if (!query.trim()) { setResults([]); return; }
    timerRef.current = setTimeout(() => {
      const url = mode === "families"
        ? `${API}/family/search?q=${encodeURIComponent(query.trim())}&limit=15`
        : `${API}/search?q=${encodeURIComponent(query.trim())}&limit=15`;
      fetch(url).then(r => r.json()).then(d => {
        setResults(d.results || []);
        setOpen(true);
      }).catch(() => { });
    }, 250);
    return () => clearTimeout(timerRef.current);
  }, [query, mode]);

  const currentMemberIds = useMemo(() => new Set((familyMembers || []).map(m => m.id)), [familyMembers]);

  const doAdd = () => {
    if (!selected) return;
    setSaving(true); setError(null); setConflict(null);
    const body = { lemma_id: selected.id, relation };
    if (parentLemmaId) body.parent_lemma_id = parseInt(parentLemmaId);
    fetch(`${API}/family/${familyId}/add-member`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(async r => {
      const d = await r.json();
      if (r.ok) { onDone(); setSelected(null); setQuery(""); setOpen(false); }
      else if (d.conflict) { setConflict(d.conflict); setSaving(false); }
      else { setError(d.error || "Failed"); setSaving(false); }
    }).catch(() => { setError("Network error"); setSaving(false); });
  };

  const doMerge = () => {
    if (!conflict) return;
    setSaving(true);
    fetch(`${API}/family/${familyId}/merge/${conflict.existing_family_id}`, { method: "POST" })
      .then(async r => {
        if (r.ok) { onDone(); setSelected(null); setQuery(""); setOpen(false); setConflict(null); }
        else { setError("Merge failed"); setSaving(false); }
      }).catch(() => { setError("Network error"); setSaving(false); });
  };

  const doMergeFamily = (targetFamilyId) => {
    setSaving(true);
    fetch(`${API}/family/${familyId}/merge/${targetFamilyId}`, { method: "POST" })
      .then(async r => {
        if (r.ok) { onDone(); setSelected(null); setQuery(""); setOpen(false); }
        else { setError("Merge failed"); setSaving(false); }
      }).catch(() => { setError("Network error"); setSaving(false); });
  };

  const parentOptions = (familyMembers || []).filter(m => m.id !== selected?.id);

  return (
    <div ref={wrapRef} style={{ position: "relative", display: "flex", alignItems: "center", gap: 4 }}>
      {/* Mode toggle */}
      <select value={mode} onChange={e => { setMode(e.target.value); setResults([]); setSelected(null); }}
        style={{
          background: T.bg, border: `1px solid ${T.borderL}`, borderRadius: 3,
          padding: "2px 4px", color: T.dim, fontSize: 11, fontFamily: T.mono, cursor: "pointer"
        }}>
        <option value="words">Words</option>
        <option value="families">Families</option>
      </select>

      {/* Search input */}
      <input value={query} onChange={e => setQuery(e.target.value)}
        onFocus={() => { if (results.length > 0) setOpen(true); }}
        placeholder={mode === "families" ? "Search families..." : "Search words to add..."}
        style={{
          width: 180, background: T.bg, border: `1px solid ${T.borderL}`,
          borderRadius: 4, padding: "3px 8px", color: T.text, fontSize: 12,
          fontFamily: T.font, outline: "none"
        }} />

      {/* Dropdown */}
      {open && results.length > 0 && !selected && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4,
          width: 360, maxHeight: 300, overflowY: "auto", zIndex: 1000,
          background: T.surface, border: `1px solid ${T.border}`, borderRadius: 6,
          boxShadow: "0 8px 24px rgba(0,0,0,.5)"
        }}>
          {mode === "words" ? results.map(r => {
            const inFamily = currentMemberIds.has(r.id);
            return (
              <div key={r.id} onClick={() => { if (!inFamily) setSelected(r); }}
                style={{
                  padding: "6px 12px", cursor: inFamily ? "default" : "pointer",
                  display: "flex", alignItems: "baseline", gap: 6,
                  background: inFamily ? "rgba(107,156,107,.08)" : "transparent",
                  borderBottom: `1px solid ${T.border}`
                }}
                onMouseEnter={e => { if (!inFamily) e.currentTarget.style.background = T.hover; }}
                onMouseLeave={e => { e.currentTarget.style.background = inFamily ? "rgba(107,156,107,.08)" : "transparent"; }}>
                <span style={{ color: T.bright, fontWeight: 500, fontSize: 14, fontFamily: T.font }}>{r.lemma}</span>
                <span style={{ color: POS_CLR[r.pos] || T.dim, fontSize: 11, fontWeight: 600 }}>{r.pos}</span>
                <span style={{
                  color: T.dim, fontSize: 11, fontStyle: "italic", flex: 1,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap"
                }}>
                  {(r.short_def || "").slice(0, 40)}</span>
                {inFamily && <span style={{ color: T.green, fontSize: 10, fontFamily: T.mono }}>IN FAMILY</span>}
              </div>
            );
          }) : results.map(r => (
            <div key={r.id} style={{
              padding: "6px 12px", cursor: "pointer",
              display: "flex", alignItems: "baseline", gap: 6,
              borderBottom: `1px solid ${T.border}`
            }}
              onMouseEnter={e => { e.currentTarget.style.background = T.hover; }}
              onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}
              onClick={() => doMergeFamily(r.id)}>
              <span style={{ color: T.bright, fontWeight: 500, fontSize: 14, fontFamily: T.font }}>{r.label}</span>
              <span style={{ color: T.dim, fontSize: 11, fontFamily: T.mono }}>{r.member_count} words</span>
              <span style={{ color: T.gold, fontSize: 10, fontFamily: T.mono, marginLeft: "auto" }}>MERGE</span>
            </div>
          ))}
        </div>
      )}

      {/* Selected word — add flow */}
      {selected && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4,
          width: 340, zIndex: 1000, background: T.surface,
          border: `1px solid ${T.border}`, borderRadius: 6, padding: 12,
          boxShadow: "0 8px 24px rgba(0,0,0,.5)"
        }}>
          <div style={{ fontSize: 14, color: T.bright, fontWeight: 600, marginBottom: 8 }}>
            Add <span style={{ color: T.gold }}>{selected.lemma}</span> ({selected.pos})
          </div>

          {conflict ? (
            <div>
              <div style={{ fontSize: 12, color: T.dim, marginBottom: 6 }}>
                Already in family "<strong>{conflict.existing_family_label}</strong>".
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button onClick={doMerge} disabled={saving} style={{
                  flex: 1, background: T.gold, border: "none", borderRadius: 4, padding: "5px 0",
                  color: T.bg, fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}>Merge Families</button>
                <button onClick={() => { setConflict(null); setSelected(null); }} style={{
                  flex: 1, background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4,
                  padding: "5px 0", color: T.text, fontSize: 12, cursor: "pointer",
                }}>Cancel</button>
              </div>
            </div>
          ) : (
            <>
              <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 11, color: T.dim, marginBottom: 2 }}>Relation</div>
                  <select value={relation} onChange={e => setRelation(e.target.value)}
                    style={{
                      width: "100%", background: T.bg, border: `1px solid ${T.borderL}`,
                      borderRadius: 3, padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font
                    }}>
                    {RELATION_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 11, color: T.dim, marginBottom: 2 }}>Parent</div>
                  <select value={parentLemmaId} onChange={e => setParentLemmaId(e.target.value)}
                    style={{
                      width: "100%", background: T.bg, border: `1px solid ${T.borderL}`,
                      borderRadius: 3, padding: "3px 5px", color: T.text, fontSize: 12, fontFamily: T.font
                    }}>
                    <option value="">Root (direct)</option>
                    {parentOptions.map(m => (
                      <option key={m.id} value={m.id}>{m.lemma} ({m.pos})</option>
                    ))}
                  </select>
                </div>
              </div>
              {error && <div style={{ fontSize: 11, color: T.red, marginBottom: 4 }}>{error}</div>}
              <div style={{ display: "flex", gap: 6 }}>
                <button onClick={doAdd} disabled={saving} style={{
                  flex: 1, background: T.gold, border: "none", borderRadius: 4, padding: "5px 0",
                  color: T.bg, fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}>{saving ? "Adding..." : "Add to Family"}</button>
                <button onClick={() => { setSelected(null); setError(null); setConflict(null); }} style={{
                  flex: 1, background: T.raised, border: `1px solid ${T.border}`, borderRadius: 4,
                  padding: "5px 0", color: T.text, fontSize: 12, cursor: "pointer",
                }}>Cancel</button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}


function decodeB64String(str) {
  const binary = atob(str);
  const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
  return new TextDecoder("utf-8").decode(bytes);
}


const languages = ['arabic', 'english', 'greek'];

function ProductionTraining({ language, toPronounce }) {
  console.log("lang", language);
  const [toSay, setToSay] = useState(toPronounce);
  const [mediaBlobUrl, setMediaBlobUrl] = useState('');
  const [lastWordsUttered, setlastWordsUttered] = useState('');
  const [recording, setRecording] = useState(false);
  async function getProductionTask() {
    try {
      const response = await fetch(`${BASE}/get_production_task?language=${languages[language]}`, {
        method: "GET",
      });

      const data = await response.json();
      return decodeB64String(data.text);
    } catch (err) {
      console.log("failed to get production task:", err);
      return null;
    }
  }
  async function sendAudioToServer(blob) {
    const copy = await fetch(blob).then((r) => r.blob());
    const formData = new FormData();
    formData.append("file", new File([copy], "recording.webm", { type: copy.type }));
    formData.append("language", languages[language]);

    try {
      const response = await fetch(`${BASE}/transcribe`, {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      console.log(data);
      setlastWordsUttered(data.text.toLocaleLowerCase('el').toLocaleLowerCase('en'));
      return data.text;
    } catch (err) {
      console.log("Failed to send audio:", err);
      return null;
    }
  }
  return (
    <>
      {!toPronounce && <button style={{
        padding: "2px 7px", borderRadius: 3, fontSize: 11, fontWeight: 600,
        letterSpacing: .3, cursor: "pointer", fontFamily: T.font,
        background: false ? clr : "transparent",
        color: 'white',
        border: `1px solid ${false ? clr : T.borderL}`,
        opacity: false ? 1 : 0.6,
        width: '10%'
      }}
        onClick={async () => {
          setToSay((await getProductionTask()).toLocaleLowerCase('el').toLocaleLowerCase('en'))
          setlastWordsUttered('');
        }}>Get New Production Task</button>}
      <ReactMediaRecorder
        render={({ status, startRecording, stopRecording, mediaBlobUrl: blobUrl }) => {
          console.log(blobUrl);
          if (typeof blobUrl !== 'undefined') {
            setMediaBlobUrl(blobUrl);
          }
          return (
            <div>
              <button style={{
                padding: "2px 7px", borderRadius: 3, fontSize: 11, fontWeight: 600,
                letterSpacing: .3, cursor: "pointer", fontFamily: T.font,
                background: false ? clr : "transparent",
                color: 'white',
                border: `1px solid ${false ? clr : T.borderL}`,
                opacity: false ? 1 : 0.6,
              }}
                onClick={(e) => {
                  const innerRec = recording;
                  setRecording(!innerRec);
                  return innerRec ? stopRecording(e) : startRecording(e);
                }}>{recording ? 'Stop' : 'Start'} Recording</button>
              <div>
                {blobUrl && <video src={blobUrl} controls autoPlay loop />}</div>
            </div>
          )
        }}
      />

      <Flashcard callback={() => sendAudioToServer(mediaBlobUrl)} toSay={toSay} lastWordsUttered={lastWordsUttered} />
    </>
  )
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
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [showHistoryPanel, setShowHistoryPanel] = useState(false);
  const [showLSJReview, setShowLSJReview] = useState(false);
  const [linkedFamilies, setLinkedFamilies] = useState([]);
  const [nodeAction, setNodeAction] = useState(null); // { member, x, y }
  const [familyScope, setFamilyScope] = useState("all"); // "all" | "work"
  const [vizMode, setVizMode] = useState("tree"); // "tree" | "sunburst"
  const [vocabLimit, setVocabLimit] = useState(500);
  const [headerSearch, setHeaderSearch] = useState("");
  const [headerResults, setHeaderResults] = useState([]);
  const [headerSearching, setHeaderSearching] = useState(false);
  const [headerDropdownOpen, setHeaderDropdownOpen] = useState(false);
  const headerSearchRef = useRef(null);
  const headerDropdownRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (headerSearchRef.current && !headerSearchRef.current.contains(e.target) &&
        headerDropdownRef.current && !headerDropdownRef.current.contains(e.target)) {
        setHeaderDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Debounced search
  const headerSearchTimer = useRef(null);
  const doHeaderSearch = useCallback((q) => {
    setHeaderSearch(q);
    if (headerSearchTimer.current) clearTimeout(headerSearchTimer.current);
    if (!q.trim()) { setHeaderResults([]); setHeaderDropdownOpen(false); return; }
    headerSearchTimer.current = setTimeout(() => {
      setHeaderSearching(true);
      fetch(`${API}/search?q=${encodeURIComponent(q.trim())}&limit=10`)
        .then(r => r.json()).then(d => {
          setHeaderResults(d.results || []);
          setHeaderDropdownOpen(true);
          setHeaderSearching(false);
        }).catch(() => setHeaderSearching(false));
    }, 300);
  }, []);

  const selectHeaderResult = useCallback((item) => {
    setSelectedWord(item);
    setDetailWord(item);
    setRightPinned(true);
    setHeaderSearch("");
    setHeaderResults([]);
    setHeaderDropdownOpen(false);
  }, []);
  const centerRef = useRef(null);
  const [centerDims, setCenterDims] = useState({ w: 600, h: 500 });
  const [headerExpanded, setHeaderExpanded] = useState(false);
  let views = ['Vocabulary Explorer', 'Speech Production', 'Speech Perception'];
  if (ELIDE_SPEECH_TRAINING) {
    views = ['Vocabulary Explorer'];
  }
  const [currentView, setCurrentView] = useState(0);


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
          }).catch(() => { }).finally(() => loading.stop());
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


  const handleReparent = useCallback((memberId, newParentId, sourceFamilyId, targetFamilyId) => {
    if (targetFamilyId && targetFamilyId !== sourceFamilyId) {
      // Cross-family move
      fetch(`${API}/family/${sourceFamilyId}/move-member/${memberId}/to/${targetFamilyId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_parent_id: newParentId, move_descendants: true }),
      }).then(r => { if (r.ok) bumpFamily(); });
    } else {
      // Same-family reparent
      fetch(`${API}/family/${sourceFamilyId}/member/${memberId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ parent_lemma_id: newParentId }),
      }).then(r => { if (r.ok) bumpFamily(); });
    }
  }, [bumpFamily]);

  const vocabIds = useMemo(() => new Set(vocab.map(w => w.id)), [vocab]);
  const hasWorkFilter = selectedAuthors.size > 0 || selectedWorks.size > 0;
  const family = useMemo(() => {
    if (!familyAll) return null;
    if (familyScope !== "work" || !hasWorkFilter) return familyAll;
    const filtered = familyAll.members.filter(m => vocabIds.has(m.id));
    if (filtered.length === 0) return familyAll; // fallback if no members match
    return { ...familyAll, members: filtered };
  }, [familyAll, familyScope, hasWorkFilter, vocabIds]);

  // Always fetch linked families (includes both explicit links and shared-member families)
  useEffect(() => {
    if (!family?.id) { setLinkedFamilies([]); return; }
    fetch(`${API}/family/${family.id}/linked`)
      .then(r => r.json()).then(d => setLinkedFamilies(d.linked_families || []))
      .catch(() => setLinkedFamilies([]));
  }, [family?.id, familyVersion]);

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



  // TODO: pull into separate view jsx
  const [language, setLanguage] = useState(0);
  const [audioUrl, setAudioUrl] = useState(null);
  const [transcription, setTranscription] = useState("");
  const videoRef = useRef(null);


  const fetchTask = async () => {
    try {
      const params = '?' + languages[language] + '=1';
      const response = await fetch(`${BASE}/get_perception_task${params}`);
      console.log(response);
      const blob = await response.blob();
      setAudioUrl(URL.createObjectURL(blob));

      const encodedTranscription = response.headers.get("X-Transcription");
      console.log("hi", encodedTranscription);

      if (encodedTranscription) {
        setTranscription(decodeB64String(encodedTranscription));
      }
    } catch (err) {
      console.log("Error fetching perception task:", err);
    }
  };
  const [languageHeaderExpanded, setLanguageHeaderExpanded] = useState(false);

  return (
    <div style={{
      height: "100vh", display: "flex", flexDirection: "column",
      background: T.bg, color: T.text, fontFamily: T.font, overflow: "hidden"
    }}>
      <LoadingBar visible={loading.visible} />
      <link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@300;400&display=swap" rel="stylesheet" />

      {/* Header */}
      <header style={{
        borderBottom: `1px solid ${T.border}`, padding: "7px 14px",
        display: "flex", alignItems: "center", gap: 10, flexShrink: 0
      }}>
        <span style={{ fontSize: 20, fontWeight: 700, color: T.bright, letterSpacing: 1 }}>ΓΛΩΣΣΑ</span>
        {!ELIDE_SPEECH_TRAINING && <span style={{ cursor: 'pointer' }} onClick={() => setHeaderExpanded(!headerExpanded)}>{headerExpanded ? "▾" : "▸"}</span>}
        <div>
          <div style={{ fontSize: 13, color: T.dim, letterSpacing: 1, textAlign: 'center' }}>{views[currentView]}
          </div>
          {views.map((_, idx) => <>
            {/* copied from above since we aren't using a scalable styling solution :( */}
            {(idx != currentView && headerExpanded) &&
              <div className='hover-color' onClick={() => {
                setCurrentView(idx);
                setHeaderExpanded(false);
              }} style={{ textAlign: 'center', cursor: 'pointer', fontSize: 13, color: T.dim, letterSpacing: 1 }}>{views[idx]}</div>}
          </>)}
        </div>
        {currentView !== 0 && <>
          <span style={{ cursor: 'pointer' }} onClick={() => setLanguageHeaderExpanded(!languageHeaderExpanded)}>{languageHeaderExpanded ? "▾" : "▸"}</span>

          <div>
            <div style={{ fontSize: 13, color: T.dim, letterSpacing: 1, textAlign: 'center' }}>
              Current Language: {languages[language]}
            </div>
            {/* copied, should be pulled out into separate component */}
            {languages.map((_, idx) => <>
              {/* copied from above since we aren't using a scalable styling solution :( */}
              {(idx != language && languageHeaderExpanded) &&
                <div className='hover-color' onClick={() => {
                  setLanguage(idx);
                  setLanguageHeaderExpanded(false);
                }} style={{ textAlign: 'center', cursor: 'pointer', fontSize: 13, color: T.dim, letterSpacing: 1 }}>{languages[idx]}</div>}
            </>)}
          </div></>}
        {currentView === 0 && <>
          <span style={{
            fontSize: 10, padding: "2px 6px", borderRadius: 3, letterSpacing: 1,
            background: connected ? "rgba(107,156,107,.15)" : "rgba(196,87,74,.15)",
            color: connected ? T.green : T.red,
            border: `1px solid ${connected ? "rgba(107,156,107,.3)" : "rgba(196,87,74,.3)"}`,
          }}>{connected ? "CONNECTED" : "CONNECTING"}
          </span></>

        }
        {superuser && (
          <span style={{
            fontSize: 10, padding: "2px 6px", borderRadius: 3, letterSpacing: 1,
            background: "rgba(212,168,67,.15)", color: T.gold,
            border: `1px solid rgba(212,168,67,.3)`,
          }}>SUPERUSER</span>
        )}
        {/* Quick Greek word search */}
        <div style={{ position: "relative", marginLeft: 12 }}>
          <input ref={headerSearchRef}
            value={headerSearch}
            onChange={e => doHeaderSearch(e.target.value)}
            onFocus={() => { if (headerResults.length > 0) setHeaderDropdownOpen(true); }}
            placeholder="Look up a Greek word..."
            style={{
              background: T.surface, color: T.text, border: `1px solid ${T.border}`,
              borderRadius: 4, padding: "4px 10px", fontSize: T.sm, fontFamily: T.font,
              width: 220, outline: "none",
            }}
            onKeyDown={e => {
              if (e.key === "Enter" && headerResults.length > 0) selectHeaderResult(headerResults[0]);
              if (e.key === "Escape") setHeaderDropdownOpen(false);
            }}
          />
          {headerSearching && <span style={{ position: "absolute", right: 8, top: 6, fontSize: 11, color: T.dim }}>...</span>}
          {headerDropdownOpen && headerResults.length > 0 && (
            <div ref={headerDropdownRef} style={{
              position: "absolute", top: "100%", left: 0, width: 320, maxHeight: 300,
              overflowY: "auto", background: T.raised, border: `1px solid ${T.borderL}`,
              borderRadius: 4, marginTop: 4, zIndex: 9999, boxShadow: "0 4px 12px rgba(0,0,0,.5)",
            }}>
              {headerResults.map(r => (
                <div key={r.id} onClick={() => selectHeaderResult(r)}
                  style={{
                    padding: "6px 10px", cursor: "pointer", display: "flex", alignItems: "baseline", gap: 8,
                    borderBottom: `1px solid ${T.border}`,
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = T.hover}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <span style={{ fontWeight: 600, color: T.bright, fontSize: T.md }}>{r.lemma}</span>
                  <span style={{ fontSize: 11, color: POS_CLR[r.pos] || T.dim }}>{r.pos}</span>
                  <span style={{ fontSize: 12, color: T.dim, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.short_def}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{ flex: 1 }} />
        {selectedWord && (
          <span style={{ fontSize: 13, color: T.dim }}>
            Family: <strong style={{ color: T.gold }}>{family?.label || "loading..."}</strong>
          </span>
        )}
        <a href="/about.html"
          style={{ fontSize: 11, letterSpacing: 1.5, color: T.dim, cursor: "pointer",
            fontFamily: T.mono, fontWeight: 600, padding: "2px 8px", borderRadius: 3,
            border: `1px solid ${T.border}`, textDecoration: "none", transition: "color 0.2s, border-color 0.2s" }}
          onMouseEnter={e => { e.currentTarget.style.color = T.gold; e.currentTarget.style.borderColor = T.goldDim; }}
          onMouseLeave={e => { e.currentTarget.style.color = T.dim; e.currentTarget.style.borderColor = T.border; }}
        >ABOUT</a>
      </header>

      {/* Main layout */}
      {currentView === 0 && <>

        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
          {/* LEFT: Works + Word list */}
          <CollapsiblePanel side="left" label="WORKS & VOCABULARY"
            // gah! why are we not using responsive units?
            // everything is not mobile responsive
            // we should also be using a css framework, as they simplify the actual grids
            expandedWidth={420} pinned={leftPinned} onTogglePin={() => setLeftPinned(p => !p)}>
            <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
              {/* Works panel */}
              <div style={{
                width: 200, flexShrink: 0, borderRight: `1px solid ${T.border}`,
                display: "flex", flexDirection: "column", overflow: "hidden"
              }}>
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
          <div ref={centerRef} style={{
            flex: 1, display: "flex", flexDirection: "column",
            overflow: "hidden", position: "relative", background: T.bg
          }}>
            {/* Superuser toolbar */}
            {superuser && family && (
              <div style={{
                display: "flex", alignItems: "center", gap: 10, padding: "4px 12px",
                background: "rgba(212,168,67,0.08)", borderBottom: `1px solid ${T.goldDim}`,
                flexShrink: 0
              }}>
                <span style={{
                  fontSize: 11, fontFamily: T.mono, letterSpacing: 1.5, color: T.goldDim,
                  fontWeight: 700
                }}>EDIT MODE</span>
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
                <button onClick={() => setShowLinkModal(true)} style={{
                  background: T.raised, border: `1px solid ${T.borderL}`, borderRadius: 4, padding: "3px 10px",
                  color: T.text, fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}>Link Family</button>
                <button onClick={() => setShowHistoryPanel(true)} style={{
                  background: T.raised, border: `1px solid ${T.borderL}`, borderRadius: 4, padding: "3px 10px",
                  color: T.text, fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}>History</button>
                <button onClick={() => setShowLSJReview(true)} style={{
                  background: T.raised, border: `1px solid ${T.borderL}`, borderRadius: 4, padding: "3px 10px",
                  color: T.text, fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}>LSJ Review</button>
                <SuperuserSearch familyId={family.id} familyMembers={family.members} onDone={bumpFamily} />
                <div style={{ flex: 1 }} />
                <span style={{ fontSize: 11, color: T.dim, fontStyle: "italic" }}>Right-click a node to edit · Drag to reparent</span>
              </div>)}
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
            <div style={{
              alignItems: "center", gap: 6, padding: "3px 12px",
              borderBottom: `1px solid ${T.border}`, flexShrink: 0, background: T.surface
            }}>
              {hasWorkFilter && (
                <div>
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
              <div><span style={{ fontSize: 11, color: T.dim }}>View:</span>
                {["tree", "sunburst"].map(m => (
                  <button key={m} onClick={() => setVizMode(m)} style={{
                    background: vizMode === m ? T.bright : "transparent",
                    color: vizMode === m ? T.bg : T.dim,
                    border: `1px solid ${vizMode === m ? T.bright : T.borderL}`,
                    borderRadius: 3, padding: "1px 8px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                  }}>{m === "tree" ? "Tree" : "Sunburst"}</button>
                ))}</div>

            </div>

            <div style={{ flex: 1, position: "relative" }}>
              {vizMode === "sunburst" ? (
                <FamilyTreeSunburst family={family} selectedWord={selectedWord} detailWord={detailWord}
                  onSelectMember={m => setDetailWord(m)}
                  onNodeAction={superuser ? (m, x, y) => setNodeAction({ member: m, x, y }) : undefined}
                  linkedFamilies={linkedFamilies.length > 0 ? linkedFamilies : undefined}
                  width={centerDims.w} height={centerDims.h - (superuser && family ? 30 : 0)} />
              ) : (
                <FamilyTree family={family} selectedWord={selectedWord} detailWord={detailWord}
                  onSelectMember={m => setDetailWord(m)}
                  onNodeAction={superuser ? (m, x, y) => setNodeAction({ member: m, x, y }) : undefined}
                  onReparent={superuser ? handleReparent : undefined}
                  linkedFamilies={linkedFamilies.length > 0 ? linkedFamilies : undefined}
                  width={centerDims.w} height={centerDims.h - (superuser && family ? 30 : 0)} />
              )}
            </div>
          </div>

          {/* RIGHT: Details */}
          <CollapsiblePanel side="right" label="DETAILS"
            expandedWidth={350} pinned={rightPinned} onTogglePin={() => setRightPinned(p => !p)}>
            <FormsPanel lemmaId={detailWord?.id} workId={[...selectedWorks][0] || null} scope={familyScope} language={language} />
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
            familyRootId={(() => {
              const members = family.members || [];
              const roots = members.filter(m => m.relation === "root");
              if (roots.length > 0) return roots.reduce((a, b) => (a.total_occurrences || 0) >= (b.total_occurrences || 0) ? a : b).id;
              return members[0]?.id;
            })()}
            x={nodeAction.x} y={nodeAction.y}
            onClose={() => setNodeAction(null)} onDone={() => { bumpFamily(); setShowLinked(true); }} />
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

        {/* Superuser: Link Family Modal */}
        {showLinkModal && family && (
          <LinkFamilyModal familyId={family.id} familyLabel={family.label}
            onClose={() => setShowLinkModal(false)} onDone={() => { bumpFamily(); setShowLinked(true); }} />
        )}

        {/* Superuser: Edit History Panel */}
        {showHistoryPanel && (
          <EditHistoryPanel
            onClose={() => setShowHistoryPanel(false)}
            onRevert={bumpFamily}
          />
        )}

        {/* Superuser: LSJ Review Panel */}
        {showLSJReview && (
          <LSJReviewPanel
            onClose={() => setShowLSJReview(false)}
            onUpdate={bumpFamily}
          />
        )}

      </>}


      {currentView === 1 && <ProductionTraining language={language} />}

      {currentView === 2 && <>
        <div style={{ margin: '2rem' }}>
          <button style={{
            padding: "2px 7px", borderRadius: 3, fontSize: 11, fontWeight: 600,
            letterSpacing: .3, cursor: "pointer", fontFamily: T.font,
            background: false ? clr : "transparent",
            color: 'white',
            border: `1px solid ${false ? clr : T.borderL}`,
            opacity: false ? 1 : 0.6,
          }} onClick={fetchTask}>Load New Task</button>
          <Perception audioUrl={audioUrl} videoRef={videoRef} transcription={transcription} />
        </div>
      </>}

    </div>)
}
