import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import * as d3 from "d3";

const API = "http://localhost:5000/api";

const T = {
  bg: "#0e0d0b", surface: "#1a1815", raised: "#211f1a",
  hover: "#2a2722", border: "#302c25", borderL: "#3d372e",
  text: "#c8bfa8", dim: "#8a7f6e", bright: "#efe6d0",
  gold: "#d4a843", goldDim: "#a68432", goldGlow: "rgba(212,168,67,0.10)",
  red: "#c4574a", blue: "#5a8fb4", green: "#6b9c6b",
  purple: "#8b6fa8", teal: "#5a9e94", orange: "#c4864a",
  rose: "#b4697a", cyan: "#5aafb4",
  font: "'EB Garamond', Georgia, serif",
  mono: "'JetBrains Mono', monospace",
};
const POS_CLR = {
  noun: T.gold, verb: T.blue, adjective: T.green, adverb: T.purple,
  pronoun: T.teal, preposition: T.orange, conjunction: T.rose,
  particle: T.cyan, article: T.dim, "": T.dim,
};
const FAM_COLORS = [T.gold, T.blue, T.green, T.purple, T.teal, T.orange, T.rose, T.cyan, T.red];

function useApi(url) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!url) { setData(null); return; }
    let cancel = false;
    setLoading(true); setError(null);
    fetch(url).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(d => { if (!cancel) setData(d); })
      .catch(e => { if (!cancel) setError(e.message); })
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [url]);
  return { data, loading, error };
}

function RadialViz({ vocab, onSelect, selectedId, width, height }) {
  const svgRef = useRef(null);
  const [tip, setTip] = useState(null);

  useEffect(() => {
    if (!svgRef.current || !vocab?.length) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    const cx = width / 2, cy = height / 2, maxR = Math.min(cx, cy) - 50;
    const g = svg.append("g").attr("transform", `translate(${cx},${cy})`);

    [1, .75, .5, .25].forEach((r, i) => {
      g.append("circle").attr("r", maxR * r).attr("fill", "none")
        .attr("stroke", T.border).attr("stroke-width", i === 0 ? .8 : .4)
        .attr("stroke-dasharray", i > 0 ? "1.5,4" : "none").attr("opacity", .5);
    });

    const groups = new Map();
    vocab.forEach(w => {
      const s = w.lemma.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      const stem = s.slice(0, Math.min(4, Math.max(3, Math.floor(s.length * 0.6))));
      if (!groups.has(stem)) groups.set(stem, []);
      groups.get(stem).push(w);
    });

    const sorted = [...groups.entries()].sort((a, b) => {
      if (b[1].length !== a[1].length) return b[1].length - a[1].length;
      return b[1].reduce((s, w) => s + (w.work_freq || 0), 0) -
             a[1].reduce((s, w) => s + (w.work_freq || 0), 0);
    });

    const nodes = [];
    let slot = 0, total = vocab.length, fci = 0;
    const arcs = [];

    sorted.forEach(([stem, members]) => {
      const isFam = members.length >= 2;
      const fc = isFam ? FAM_COLORS[fci++ % FAM_COLORS.length] : T.dim;
      const startSlot = slot;
      members.sort((a, b) => (b.work_freq || 0) - (a.work_freq || 0)).forEach(w => {
        const angle = (slot / total) * 2 * Math.PI - Math.PI / 2;
        const fn = Math.min((w.work_freq || 1) / 200, 1);
        const radius = maxR * (0.28 + fn * 0.58);
        nodes.push({
          ...w, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius,
          angle, radius, stem, fc, isFam,
          nr: 2.5 + Math.sqrt((w.work_freq || 1) / 15) * 1.5,
        });
        slot++;
      });
      if (isFam) arcs.push({ stem, color: fc,
        sa: (startSlot / total) * 2 * Math.PI - Math.PI / 2,
        ea: (slot / total) * 2 * Math.PI - Math.PI / 2, count: members.length });
    });

    const arcGen = d3.arc().innerRadius(maxR * .18).outerRadius(maxR * .98);
    arcs.forEach(a => {
      if (a.ea - a.sa < .02) return;
      g.append("path").attr("d", arcGen({ startAngle: a.sa, endAngle: a.ea }))
        .attr("fill", a.color).attr("opacity", .03)
        .attr("stroke", a.color).attr("stroke-width", .8).attr("stroke-opacity", .12);
    });

    const famMap = new Map();
    nodes.forEach(n => { if (!n.isFam) return;
      if (!famMap.has(n.stem)) famMap.set(n.stem, []);
      famMap.get(n.stem).push(n); });
    famMap.forEach(members => {
      if (members.length < 2) return;
      for (let i = 0; i < members.length - 1; i++) {
        const a = members[i], b = members[i + 1];
        g.append("path").attr("d", `M${a.x},${a.y}Q0,0 ${b.x},${b.y}`)
          .attr("fill", "none").attr("stroke", a.fc)
          .attr("stroke-width", .6).attr("stroke-opacity", .12);
      }
    });

    nodes.filter(n => n.isFam).forEach(n => {
      g.append("line").attr("x1", 0).attr("y1", 0).attr("x2", n.x).attr("y2", n.y)
        .attr("stroke", n.fc).attr("stroke-width", .3).attr("stroke-opacity", .07);
    });

    const nodeG = g.selectAll(".nd").data(nodes).join("g")
      .attr("class", "nd").attr("transform", d => `translate(${d.x},${d.y})`)
      .style("cursor", "pointer");

    nodeG.append("circle").attr("r", d => selectedId === d.id ? d.nr + 10 : 0)
      .attr("fill", d => d.fc).attr("opacity", .12);
    nodeG.append("circle").attr("r", d => d.nr)
      .attr("fill", d => selectedId === d.id ? T.gold : (d.isFam ? d.fc : POS_CLR[d.pos] || T.dim))
      .attr("stroke", d => selectedId === d.id ? T.gold : "none").attr("stroke-width", 1.5)
      .attr("opacity", d => selectedId === d.id ? 1 : (d.isFam ? .8 : .45));
    nodeG.append("text").attr("dy", d => -d.nr - 4).attr("text-anchor", "middle")
      .attr("fill", d => selectedId === d.id ? T.gold : (d.isFam ? T.bright : T.dim))
      .attr("font-size", d => selectedId === d.id ? "12px" : (d.nr > 5 ? "9.5px" : "0"))
      .attr("font-family", T.font).attr("font-weight", d => selectedId === d.id ? 700 : 400)
      .attr("opacity", d => selectedId === d.id ? 1 : .8).text(d => d.lemma);

    nodeG.on("mouseenter", function(ev, d) {
      setTip(d);
      d3.select(this).select("circle:nth-child(2)")
        .transition().duration(120).attr("r", d.nr + 3).attr("opacity", 1);
      d3.select(this).select("text")
        .transition().duration(120).attr("font-size", "11px").attr("fill", T.gold).attr("opacity", 1);
    }).on("mouseleave", function(ev, d) {
      setTip(null);
      const sel = selectedId === d.id;
      d3.select(this).select("circle:nth-child(2)")
        .transition().duration(120).attr("r", d.nr).attr("opacity", sel ? 1 : (d.isFam ? .8 : .45));
      d3.select(this).select("text").transition().duration(120)
        .attr("font-size", sel ? "12px" : (d.nr > 5 ? "9.5px" : "0"))
        .attr("fill", sel ? T.gold : (d.isFam ? T.bright : T.dim))
        .attr("opacity", sel ? 1 : .8);
    }).on("click", (ev, d) => onSelect(d));

    g.append("circle").attr("r", 18).attr("fill", T.surface).attr("stroke", T.border).attr("stroke-width", .5);
    g.append("text").attr("text-anchor", "middle").attr("y", -2)
      .attr("fill", T.dim).attr("font-size", "7px").attr("font-family", T.font)
      .attr("letter-spacing", "2px").text("ΛΕΞΙΣ");
    g.append("text").attr("text-anchor", "middle").attr("y", 8)
      .attr("fill", T.gold).attr("font-size", "6px").attr("font-family", T.font)
      .attr("letter-spacing", "1.5px").text(nodes.length + " WORDS");
  }, [vocab, selectedId, width, height, onSelect]);

  return (
    <div style={{ position: "relative" }}>
      <svg ref={svgRef} width={width} height={height} style={{ display: "block" }} />
      {tip && (
        <div style={{
          position: "absolute", bottom: 10, left: "50%", transform: "translateX(-50%)",
          background: T.raised, border: `1px solid ${T.borderL}`, borderRadius: 6,
          padding: "6px 14px", pointerEvents: "none", whiteSpace: "nowrap",
          boxShadow: "0 8px 30px rgba(0,0,0,.6)", fontFamily: T.font, fontSize: 13,
        }}>
          <span style={{ color: tip.fc || T.gold, fontWeight: 700 }}>{tip.lemma}</span>
          <span style={{ color: T.dim, margin: "0 6px" }}>·</span>
          <span style={{ color: T.dim, fontStyle: "italic", fontSize: 12 }}>
            {tip.short_def?.slice(0, 60) || tip.pos}</span>
          <span style={{ color: T.dim, margin: "0 6px" }}>·</span>
          <span style={{ color: T.goldDim, fontSize: 11 }}>x{tip.work_freq || 0}</span>
        </div>
      )}
    </div>
  );
}

function DetailPanel({ lemmaId }) {
  const { data, loading } = useApi(lemmaId ? `${API}/lemma/${lemmaId}` : null);
  const [tab, setTab] = useState("forms");
  useEffect(() => setTab("forms"), [lemmaId]);

  if (!lemmaId) return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", height: "100%", padding: 40, textAlign: "center" }}>
      <div style={{ fontSize: 36, opacity: .15, marginBottom: 12 }}>&#9737;</div>
      <div style={{ color: T.dim, fontSize: 14, fontFamily: T.font }}>
        Select a word from the radial map</div>
      <div style={{ color: T.dim, fontSize: 12, opacity: .5, marginTop: 8,
        fontFamily: T.font, maxWidth: 220, lineHeight: 1.7 }}>
        Click any node to see forms, definitions, derivational family, and attestations.</div>
    </div>
  );
  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
      height: "100%", color: T.dim }}>Loading...</div>
  );
  if (!data) return null;

  const tabs = [
    { id: "forms", label: "Forms", n: data.forms?.length || 0 },
    { id: "defs", label: "Definitions", n: data.definitions?.length || 0 },
    { id: "family", label: "Family", n: data.family?.members?.length || 0 },
    { id: "works", label: "Works", n: data.top_works?.length || 0 },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div style={{ padding: "18px 20px 14px", borderBottom: `1px solid ${T.border}` }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontFamily: T.font, fontSize: 26, fontWeight: 700, color: T.bright }}>
            {data.lemma}</span>
          <span style={{ fontSize: 12, color: POS_CLR[data.pos] || T.dim, fontWeight: 600 }}>
            {data.pos}</span>
          {data.frequency_rank && (
            <span style={{ fontSize: 10, color: T.dim, fontFamily: T.mono }}>
              #{data.frequency_rank}</span>)}
        </div>
        {data.short_def && (
          <div style={{ fontSize: 13, color: T.dim, fontStyle: "italic",
            fontFamily: T.font, marginTop: 4, lineHeight: 1.5 }}>
            {data.short_def.slice(0, 150)}</div>)}
      </div>

      <div style={{ display: "flex", borderBottom: `1px solid ${T.border}` }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            flex: 1, padding: "9px 0", background: "none", border: "none",
            borderBottom: tab === t.id ? `2px solid ${T.gold}` : "2px solid transparent",
            color: tab === t.id ? T.gold : T.dim,
            fontSize: 11, fontFamily: T.font, letterSpacing: .8, cursor: "pointer",
          }}>
            {t.label.toUpperCase()}
            {t.n > 0 && <span style={{ opacity: .5, marginLeft: 4 }}>({t.n})</span>}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "14px 18px" }}>
        {tab === "forms" && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {(data.forms || []).slice(0, 80).map((f, i) => (
              <div key={i} style={{
                background: T.raised, border: `1px solid ${T.border}`,
                borderRadius: 5, padding: "4px 9px", fontSize: 13, fontFamily: T.font, color: T.bright,
              }}>
                <span>{f.form}</span>
                {f.gram_case && <span style={{ color: T.dim, fontSize: 9, marginLeft: 5 }}>
                  {[f.gram_case, f.number, f.gender].filter(Boolean).join(" ")}</span>}
                {!f.gram_case && f.tense && <span style={{ color: T.dim, fontSize: 9, marginLeft: 5 }}>
                  {[f.tense, f.mood, f.voice].filter(Boolean).join(" ")}</span>}
              </div>
            ))}
            {(!data.forms?.length) && (
              <div style={{ color: T.dim, fontSize: 12, fontStyle: "italic" }}>No forms recorded</div>)}
          </div>
        )}

        {tab === "defs" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {data.definitions?.length > 0 ? data.definitions.map((d, i) => (
              <div key={i} style={{ borderBottom: `1px solid ${T.border}`, paddingBottom: 10 }}>
                <div style={{ fontSize: 10, color: T.goldDim, letterSpacing: 1, marginBottom: 4 }}>
                  {d.source?.toUpperCase()}</div>
                <div style={{ fontSize: 13, color: T.text, fontFamily: T.font, lineHeight: 1.6 }}>
                  {(d.short_def || d.definition || "").slice(0, 400)}</div>
              </div>
            )) : data.lsj_def ? (
              <div style={{ fontSize: 13, color: T.text, fontFamily: T.font, lineHeight: 1.6 }}>
                {data.lsj_def.slice(0, 600)}</div>
            ) : (
              <div style={{ color: T.dim, fontSize: 12, fontStyle: "italic" }}>No definitions loaded</div>
            )}
          </div>
        )}

        {tab === "family" && (
          data.family ? (
            <div>
              <div style={{ fontSize: 12, color: T.gold, marginBottom: 12 }}>
                {data.family.label} <span style={{ color: T.dim }}>
                  ({data.family.members.length} members)</span></div>
              {data.family.members.map((m, i) => (
                <div key={i} style={{
                  display: "flex", alignItems: "baseline", gap: 8, padding: "5px 0",
                  borderBottom: i < data.family.members.length - 1 ? `1px solid ${T.border}` : "none",
                }}>
                  <span style={{ fontFamily: T.font, fontSize: 14, minWidth: 110,
                    color: m.id === data.id ? T.gold : T.bright,
                    fontWeight: m.id === data.id ? 700 : 400 }}>{m.lemma}</span>
                  <span style={{ fontSize: 10, color: T.dim, minWidth: 55 }}>{m.pos}</span>
                  <span style={{ fontSize: 10, color: T.goldDim, fontFamily: T.mono,
                    minWidth: 75 }}>{m.relation}</span>
                  <span style={{ fontSize: 11, color: T.dim, fontStyle: "italic" }}>
                    {m.short_def?.slice(0, 50)}</span>
                </div>
              ))}
            </div>
          ) : <div style={{ color: T.dim, fontSize: 12, fontStyle: "italic" }}>
            No derivational family found</div>
        )}

        {tab === "works" && (
          <div>
            {(data.top_works || []).map((w, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "baseline", gap: 8, padding: "4px 0",
                borderBottom: i < data.top_works.length - 1 ? `1px solid ${T.border}` : "none",
              }}>
                <span style={{ fontFamily: T.mono, fontSize: 11, color: T.gold,
                  minWidth: 48, textAlign: "right" }}>x{w.count}</span>
                <span style={{ fontFamily: T.font, fontSize: 13, color: T.bright }}>{w.author}</span>
                <span style={{ fontFamily: T.font, fontSize: 12, color: T.dim,
                  fontStyle: "italic" }}>{w.title}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CorpusSelector({ authors, selected, onSelect }) {
  const [open, setOpen] = useState(false);
  const [hovered, setHovered] = useState(null);
  return (
    <div style={{ position: "relative" }}>
      <button onClick={() => setOpen(!open)} style={{
        background: T.surface, border: `1px solid ${T.borderL}`,
        borderRadius: 6, padding: "7px 14px", color: T.bright,
        fontSize: 13, fontFamily: T.font, cursor: "pointer",
        display: "flex", alignItems: "center", gap: 8, minWidth: 180,
      }}>
        <span style={{ flex: 1, textAlign: "left" }}>{selected || "All Corpora"}</span>
        <span style={{ fontSize: 10, color: T.dim }}>{open ? "\u25B2" : "\u25BC"}</span>
      </button>
      {open && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4,
          background: T.raised, border: `1px solid ${T.borderL}`,
          borderRadius: 8, padding: 4, minWidth: 260, maxHeight: 400,
          overflowY: "auto", zIndex: 200, boxShadow: "0 12px 40px rgba(0,0,0,.7)",
        }}>
          <div onClick={() => { onSelect(null); setOpen(false); }}
            onMouseEnter={() => setHovered("all")} onMouseLeave={() => setHovered(null)}
            style={{ padding: "6px 12px", borderRadius: 5, cursor: "pointer",
              color: !selected ? T.gold : T.text, fontSize: 13, fontFamily: T.font,
              background: hovered === "all" ? T.hover : (!selected ? T.goldGlow : "transparent"),
            }}>All Corpora</div>
          {(authors || []).map(a => (
            <div key={a.author}
              onClick={() => { onSelect(a.author); setOpen(false); }}
              onMouseEnter={() => setHovered(a.author)} onMouseLeave={() => setHovered(null)}
              style={{
                padding: "6px 12px", borderRadius: 5, cursor: "pointer",
                color: selected === a.author ? T.gold : T.text,
                fontSize: 13, fontFamily: T.font, display: "flex", justifyContent: "space-between",
                background: hovered === a.author ? T.hover :
                  (selected === a.author ? T.goldGlow : "transparent"),
              }}>
              <span>{a.author}</span>
              <span style={{ color: T.dim, fontSize: 11, fontFamily: T.mono }}>{a.work_count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SearchBar({ onSelect }) {
  const [q, setQ] = useState("");
  const [hovIdx, setHovIdx] = useState(null);
  const { data } = useApi(q.length >= 2 ? `${API}/search?q=${encodeURIComponent(q)}&limit=12` : null);

  return (
    <div style={{ position: "relative" }}>
      <input type="text" value={q} onChange={e => setQ(e.target.value)}
        placeholder="Search lemma or gloss..."
        style={{
          background: T.surface, border: `1px solid ${T.borderL}`,
          borderRadius: 6, padding: "7px 12px 7px 28px", color: T.text,
          fontSize: 13, fontFamily: T.font, width: 190, outline: "none",
        }} />
      <span style={{ position: "absolute", left: 9, top: "50%",
        transform: "translateY(-50%)", color: T.dim, fontSize: 13 }}>{"\u2315"}</span>
      {data?.results?.length > 0 && q.length >= 2 && (
        <div style={{
          position: "absolute", top: "100%", right: 0, marginTop: 4,
          background: T.raised, border: `1px solid ${T.borderL}`,
          borderRadius: 8, padding: 4, minWidth: 300, maxHeight: 350,
          overflowY: "auto", zIndex: 200, boxShadow: "0 12px 40px rgba(0,0,0,.7)",
        }}>
          {data.results.map((r, i) => (
            <div key={r.id} onClick={() => { onSelect(r); setQ(""); }}
              onMouseEnter={() => setHovIdx(i)} onMouseLeave={() => setHovIdx(null)}
              style={{
                padding: "6px 10px", borderRadius: 5, cursor: "pointer",
                display: "flex", alignItems: "baseline", gap: 8, fontSize: 13,
                background: hovIdx === i ? T.hover : "transparent",
              }}>
              <span style={{ fontFamily: T.font, color: POS_CLR[r.pos] || T.text,
                fontWeight: 600 }}>{r.lemma}</span>
              <span style={{ fontSize: 10, color: T.dim }}>{r.pos}</span>
              <span style={{ fontSize: 11, color: T.dim, fontStyle: "italic" }}>
                {r.short_def?.slice(0, 50)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function GreekVocabExplorer() {
  const [corpus, setCorpus] = useState(null);
  const [posFilter, setPosFilter] = useState(null);
  const [selected, setSelected] = useState(null);
  const [limit, setLimit] = useState(150);
  const containerRef = useRef(null);
  const [dims, setDims] = useState({ w: 560, h: 560 });

  const { data: authData } = useApi(`${API}/authors`);
  const authors = authData?.authors || [];

  const vocabUrl = useMemo(() => {
    let u = `${API}/vocab?limit=${limit}&sort=frequency&min_freq=2`;
    if (corpus) u += `&author=${encodeURIComponent(corpus)}`;
    if (posFilter) u += `&pos=${posFilter}`;
    return u;
  }, [corpus, posFilter, limit]);

  const { data: vocabData, loading } = useApi(vocabUrl);
  const vocab = vocabData?.vocab || [];

  useEffect(() => {
    const upd = () => {
      if (!containerRef.current) return;
      const r = containerRef.current.getBoundingClientRect();
      const vw = Math.min(Math.max(r.width * .58, 380), 660);
      setDims({ w: vw, h: Math.min(vw, Math.max(r.height - 100, 400)) });
    };
    upd();
    window.addEventListener("resize", upd);
    return () => window.removeEventListener("resize", upd);
  }, []);

  const handleSelect = useCallback(w => setSelected(w), []);

  const { data: statusData, error: statusErr } = useApi(`${API}/status`);
  const connected = !!statusData && !statusErr;

  const posOpts = ["noun", "verb", "adjective", "adverb", "pronoun", "preposition", "conjunction", "particle"];

  return (
    <div ref={containerRef} style={{
      background: T.bg, color: T.text, fontFamily: T.font,
      height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@300;400&display=swap" rel="stylesheet" />

      <header style={{
        borderBottom: `1px solid ${T.border}`, padding: "10px 20px",
        display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginRight: "auto" }}>
          <span style={{ fontSize: 20, fontWeight: 700, color: T.bright, letterSpacing: 1 }}>
            {"\u0393\u039B\u03A9\u03A3\u03A3\u0391"}</span>
          <span style={{ fontSize: 11, color: T.dim, letterSpacing: 1.5 }}>Vocabulary Explorer</span>
          <span style={{
            fontSize: 9, padding: "2px 7px", borderRadius: 3,
            background: connected ? "rgba(107,156,107,.15)" : "rgba(196,87,74,.15)",
            color: connected ? T.green : T.red,
            border: `1px solid ${connected ? "rgba(107,156,107,.3)" : "rgba(196,87,74,.3)"}`,
            letterSpacing: 1,
          }}>{connected ? "API CONNECTED" : "API OFFLINE"}</span>
        </div>
        <CorpusSelector authors={authors} selected={corpus} onSelect={setCorpus} />
        <select value={posFilter || ""} onChange={e => setPosFilter(e.target.value || null)}
          style={{ background: T.surface, border: `1px solid ${T.borderL}`,
            borderRadius: 6, padding: "7px 10px", color: T.text,
            fontSize: 13, fontFamily: T.font, cursor: "pointer" }}>
          <option value="">All POS</option>
          {posOpts.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={limit} onChange={e => setLimit(Number(e.target.value))}
          style={{ background: T.surface, border: `1px solid ${T.borderL}`,
            borderRadius: 6, padding: "7px 10px", color: T.text,
            fontSize: 13, fontFamily: T.font, cursor: "pointer" }}>
          {[50, 100, 150, 250, 400, 600].map(n =>
            <option key={n} value={n}>Top {n}</option>)}
        </select>
        <SearchBar onSelect={w => setSelected(w)} />
      </header>

      {!connected && (
        <div style={{
          background: "rgba(196,87,74,.08)", borderBottom: `1px solid rgba(196,87,74,.2)`,
          padding: "10px 20px", fontSize: 12, color: T.red, flexShrink: 0,
        }}>
          Cannot reach API at {API}. Start with:{" "}
          <code style={{ fontFamily: T.mono, background: T.surface,
            padding: "1px 5px", borderRadius: 3 }}>python3 serve_api.py</code>
        </div>
      )}

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <div style={{
          flex: "0 0 58%", display: "flex", alignItems: "center",
          justifyContent: "center", borderRight: `1px solid ${T.border}`, position: "relative",
        }}>
          {loading && (
            <div style={{
              position: "absolute", inset: 0, display: "flex",
              alignItems: "center", justifyContent: "center",
              background: "rgba(14,13,11,.7)", zIndex: 10, color: T.dim, fontSize: 14,
            }}>Loading vocabulary...</div>
          )}
          <RadialViz vocab={vocab} onSelect={handleSelect}
            selectedId={selected?.id} width={dims.w} height={dims.h} />
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <DetailPanel lemmaId={selected?.id} />
        </div>
      </div>

      <footer style={{
        borderTop: `1px solid ${T.border}`, padding: "6px 20px",
        display: "flex", justifyContent: "space-between", flexShrink: 0,
        fontSize: 10, color: T.dim,
      }}>
        <span>
          {vocab.length} lemmas loaded
          {corpus && <span> &middot; Corpus: <strong style={{ color: T.text }}>{corpus}</strong></span>}
        </span>
        <span>Data: PerseusDL &middot; gcelano/LemmatizedAncientGreekXML &middot; LSJ</span>
      </footer>
    </div>
  );
}
