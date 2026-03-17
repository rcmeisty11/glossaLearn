import { useEffect, useRef } from "react";
import * as d3 from "d3";

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
  xs: 13, sm: 14, md: 16, lg: 18, xl: 26,
};
const POS_CLR = {
  noun:T.gold, verb:T.blue, adjective:T.green, adverb:T.purple,
  pronoun:T.teal, preposition:T.orange, conjunction:T.rose,
  particle:T.cyan, article:T.dim, "":T.dim,
};

/**
 * Draw a sunburst for a given family into parentG at (cx, cy).
 * Returns { maxOuterR } for bounding calculations.
 */
function drawSunburst(parentG, familyMembers, cx, cy, opts) {
  const { selectedWord, onSelectRef, onNodeActionRef, tooltip, isLinked } = opts;

  const members = [...familyMembers];
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

  const buildTree = (member) => {
    const node = {
      lemma: member.lemma, pos: member.pos || "",
      def: (member.short_def || "").replace(/,\s*$/, ""),
      relation: member.relation || "", member: member,
    };
    const kids = childrenOf.get(member.id);
    if (kids && kids.length > 0) {
      const sorted = [...kids].sort((a, b) => (a.pos || "").localeCompare(b.pos || ""));
      node.children = sorted.map(k => buildTree(k));
    }
    return node;
  };
  const treeData = buildTree(rootMember);

  const root = d3.hierarchy(treeData).sum(d => d.children ? 0 : 1);
  const leafCount = root.leaves().length;
  // Scale down linked families slightly
  const scaleFactor = isLinked ? 0.7 : 1;
  const rScale = Math.max(1, leafCount / 14) * scaleFactor;
  const R_ROOT = Math.round(70 * rScale);
  const R1_INNER = Math.round(90 * rScale);
  const R1_OUTER = Math.round(210 * rScale);
  const R2_INNER = Math.round(220 * rScale);
  const R2_OUTER = Math.round(320 * rScale);

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

  const partition = d3.partition().size([2 * Math.PI, 1]).padding(0.01);
  partition(root);

  const arc = d3.arc()
    .startAngle(d => d.x0).endAngle(d => d.x1)
    .innerRadius(d => innerR(d)).outerRadius(d => outerR(d))
    .padAngle(0.008).padRadius(R1_INNER);

  let maxOuterR = R2_OUTER;
  root.descendants().forEach(d => { const oR = outerR(d); if (oR > maxOuterR) maxOuterR = oR; });

  // Create a group at the offset position
  const sunburstG = parentG.append("g")
    .attr("transform", `translate(${cx},${cy})`);

  const spinG = sunburstG.append("g");

  const slices = spinG.selectAll(".slice")
    .data(root.descendants()).join("g")
    .attr("class", "slice").style("cursor", "pointer");

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

  // Highlight ring
  slices.filter(d => d.depth > 0)
    .append("path").attr("class", "highlight-ring").attr("d", arc)
    .attr("fill", "none").attr("stroke", T.gold).attr("stroke-width", 3)
    .attr("opacity", 0).style("pointer-events", "none");

  slices.filter(d => d.depth > 0 && d.data.member?.id === selectedWord?.id)
    .select(".highlight-ring").attr("opacity", 0.9);

  let focusedId = selectedWord?.id || null;

  // Hover + tooltip
  slices.filter(d => d.depth > 0)
    .on("mouseenter", function(e, d) {
      if (d.data.member?.id === focusedId) return;
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

  // Click — highlight, rotate, select
  slices.filter(d => d.depth > 0)
    .on("click", function(e, d) {
      e.stopPropagation();
      spinG.selectAll(".highlight-ring").attr("opacity", 0);
      spinG.selectAll(".slice").select("path")
        .attr("stroke", T.bg).attr("stroke-width", 1.5).attr("opacity", 0.85);
      d3.select(this).select(".highlight-ring").attr("opacity", 0.9);
      focusedId = d.data.member?.id || null;
      if (d.data.member) onSelectRef.current(d.data.member);

      const midAngle = (d.x0 + d.x1) / 2;
      const targetRotation = -(midAngle * 180 / Math.PI) + 90;

      spinG.transition().duration(600).ease(d3.easeCubicInOut)
        .attr("transform", `rotate(${targetRotation})`);
      spinG.selectAll(".root-text")
        .transition().duration(600).ease(d3.easeCubicInOut)
        .attr("transform", `rotate(${-targetRotation})`);
      spinG.selectAll(".arc-label").each(function() {
        const labelD = d3.select(this).datum();
        const lMid = (labelD.x0 + labelD.x1) / 2;
        const lMidR = (innerR(labelD) + outerR(labelD)) / 2;
        const worldAngle = lMid + targetRotation * Math.PI / 180;
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
      .attr("class", "arc-label").datum(d)
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

  return { maxOuterR, cx, cy };
}

export default function FamilyTreeSunburst({ family, selectedWord, detailWord, onSelectMember, onNodeAction, linkedFamilies, width, height }) {
  const svgRef = useRef(null);
  const zoomRef = useRef(null);
  const onSelectRef = useRef(onSelectMember);
  onSelectRef.current = onSelectMember;
  const onNodeActionRef = useRef(onNodeAction);
  onNodeActionRef.current = onNodeAction;

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    let g = svg.select("g.family-content");
    if (g.empty()) g = svg.append("g").attr("class", "family-content");
    const zoom = d3.zoom()
      .scaleExtent([0.05, 3])
      .on("zoom", (event) => { g.attr("transform", event.transform); });
    svg.call(zoom);
    svg.style("cursor", "grab");
    svg.on("mousedown.cursor", () => svg.style("cursor", "grabbing"));
    svg.on("mouseup.cursor", () => svg.style("cursor", "grab"));
    zoomRef.current = zoom;
    return () => { svg.on(".zoom", null); };
  }, []);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    let g = svg.select("g.family-content");
    if (g.empty()) g = svg.append("g").attr("class", "family-content");
    g.selectAll("*").remove();
    d3.select("body").selectAll(".family-tooltip").remove();

    if (!family?.members?.length) {
      if (zoomRef.current) {
        svg.call(zoomRef.current.transform, d3.zoomIdentity.translate(width / 2, height / 2));
      }
      return;
    }

    // Shared tooltip
    const tooltip = d3.select("body").selectAll(".family-tooltip").data([0]).join("div")
      .attr("class", "family-tooltip")
      .style("position", "fixed").style("pointer-events", "none")
      .style("background", T.surface).style("border", `1px solid ${T.border}`)
      .style("border-radius", "6px").style("padding", "8px 12px")
      .style("font-size", "13px").style("color", T.bright)
      .style("display", "none").style("z-index", "999")
      .style("font-family", T.font);

    const opts = { selectedWord, onSelectRef, onNodeActionRef, tooltip, isLinked: false };

    // Draw main sunburst at origin
    const main = drawSunburst(g, family.members, 0, 0, opts);

    // Draw linked families
    const allBursts = [main];
    if (linkedFamilies && linkedFamilies.length > 0) {
      let nextX = main.maxOuterR; // right edge of main

      linkedFamilies.forEach((lf, li) => {
        if (!lf.members || lf.members.length === 0) return;

        // First, compute the linked sunburst's size to know the offset
        const tempRoot = d3.hierarchy({ children: lf.members.map(m => ({ lemma: m.lemma })) }).sum(() => 1);
        const leafCount = lf.members.length;
        const rScale = Math.max(1, leafCount / 14) * 0.7;
        const estMaxR = Math.round(320 * rScale);

        const gap = 120;
        const cx = nextX + gap + estMaxR;
        const cy = 0;

        // Draw bridge line from main center to linked center
        g.append("line")
          .attr("x1", main.cx).attr("y1", main.cy)
          .attr("x2", cx).attr("y2", cy)
          .attr("stroke", T.gold).attr("stroke-width", 2.5)
          .attr("stroke-dasharray", "10,8").attr("opacity", 0.4);

        // Bridge label
        const mx = (main.cx + cx) / 2, my = (main.cy + cy) / 2;
        g.append("text").attr("x", mx).attr("y", my - 10)
          .attr("text-anchor", "middle").attr("fill", T.goldDim)
          .attr("font-size", "11px").attr("font-family", T.mono)
          .attr("font-weight", 600).attr("opacity", 0.7)
          .text(lf.link_type || "related");
        if (lf.note) {
          g.append("text").attr("x", mx).attr("y", my + 8)
            .attr("text-anchor", "middle").attr("fill", T.dim)
            .attr("font-size", "9px").attr("font-family", T.font)
            .attr("font-style", "italic").attr("opacity", 0.6)
            .text(lf.note);
        }

        const linked = drawSunburst(g, lf.members, cx, cy, { ...opts, isLinked: true });
        allBursts.push(linked);
        nextX = cx + linked.maxOuterR;
      });
    }

    // Auto-fit to show all sunbursts
    if (zoomRef.current) {
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      allBursts.forEach(b => {
        minX = Math.min(minX, b.cx - b.maxOuterR);
        maxX = Math.max(maxX, b.cx + b.maxOuterR);
        minY = Math.min(minY, b.cy - b.maxOuterR);
        maxY = Math.max(maxY, b.cy + b.maxOuterR);
      });
      const totalW = maxX - minX + 80;
      const totalH = maxY - minY + 80;
      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      const fitScale = Math.min(width / totalW, height / totalH);
      svg.call(zoomRef.current.transform, d3.zoomIdentity
        .translate(width / 2 - centerX * fitScale, height / 2 - centerY * fitScale)
        .scale(fitScale));
    }

  }, [family, selectedWord, linkedFamilies, width, height]);

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
