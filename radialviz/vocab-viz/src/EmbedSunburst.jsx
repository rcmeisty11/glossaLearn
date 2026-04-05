import { useState, useEffect, useRef, useCallback } from "react";
import * as d3 from "d3";
import { T, POS_CLR } from "./embed-theme.js";

const API = "https://apiaws.glossalearn.com/api";

/* ═══════════════════════════════════════════════════════════
   Shared helpers
   ═══════════════════════════════════════════════════════════ */

function findRoot(members) {
  let rootIdx = members.findIndex(
    (m) =>
      m.relation === "root" &&
      m.total_occurrences ===
        Math.max(...members.filter((x) => x.relation === "root").map((x) => x.total_occurrences))
  );
  if (rootIdx < 0) rootIdx = 0;
  return rootIdx;
}

function buildChildMap(members, rootMember) {
  const memberById = new Map(members.map((m) => [m.id, m]));
  const childrenOf = new Map();
  members.forEach((m) => {
    if (m.id === rootMember.id) return;
    const pid =
      m.parent_lemma_id && memberById.has(m.parent_lemma_id)
        ? m.parent_lemma_id
        : rootMember.id;
    if (!childrenOf.has(pid)) childrenOf.set(pid, []);
    childrenOf.get(pid).push(m);
  });
  return { memberById, childrenOf };
}

/* ═══════════════════════════════════════════════════════════
   drawSunburst — D3 radial partition layout for a derivational
   family.  Adapted from FamilyTreeSunburst.jsx with light theme.
   ═══════════════════════════════════════════════════════════ */

function drawSunburst(parentG, familyMembers, cx, cy, opts) {
  const { selectedWord, onSelectRef, tooltip, isLinked } = opts;

  const members = [...familyMembers];
  const rootIdx = findRoot(members);
  const rootMember = members[rootIdx];
  const others = members.filter((_, i) => i !== rootIdx);

  const { childrenOf } = buildChildMap(members, rootMember);

  const buildTree = (member) => {
    const node = {
      lemma: member.lemma, pos: member.pos || "",
      def: (member.short_def || "").replace(/,\s*$/, ""),
      relation: member.relation || "", member,
    };
    const kids = childrenOf.get(member.id);
    if (kids && kids.length > 0) {
      node.children = [...kids]
        .sort((a, b) => (a.pos || "").localeCompare(b.pos || ""))
        .map((k) => buildTree(k));
    }
    return node;
  };
  const treeData = buildTree(rootMember);

  const root = d3.hierarchy(treeData).sum((d) => (d.children ? 0 : 1));
  const leafCount = root.leaves().length;
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
    .startAngle((d) => d.x0).endAngle((d) => d.x1)
    .innerRadius((d) => innerR(d)).outerRadius((d) => outerR(d))
    .padAngle(0.008).padRadius(R1_INNER);

  let maxOuterR = R2_OUTER;
  root.descendants().forEach((d) => { const oR = outerR(d); if (oR > maxOuterR) maxOuterR = oR; });

  const sunburstG = parentG.append("g").attr("transform", `translate(${cx},${cy})`);
  const spinG = sunburstG.append("g");

  const slices = spinG.selectAll(".slice")
    .data(root.descendants()).join("g")
    .attr("class", "slice").style("cursor", "pointer");

  // Root circle
  slices.filter((d) => d.depth === 0)
    .append("circle").attr("r", R_ROOT)
    .attr("fill", T.raised).attr("stroke", T.gold)
    .attr("stroke-width", 2).attr("stroke-opacity", 0.8);
  slices.filter((d) => d.depth === 0)
    .append("circle").attr("r", R_ROOT + 6)
    .attr("fill", "none").attr("stroke", T.gold)
    .attr("stroke-width", 1).attr("stroke-opacity", 0.15);

  // Non-root arcs
  slices.filter((d) => d.depth > 0)
    .append("path").attr("d", arc)
    .attr("fill", (d) => {
      const clr = POS_CLR[d.data.pos] || T.dim;
      return d.depth >= 2 ? d3.color(clr).brighter(0.3) : d3.color(clr).brighter(0.1);
    })
    .attr("stroke", T.bg).attr("stroke-width", 1.5).attr("opacity", 0.85);

  // Highlight ring
  slices.filter((d) => d.depth > 0)
    .append("path").attr("class", "highlight-ring").attr("d", arc)
    .attr("fill", "none").attr("stroke", T.gold).attr("stroke-width", 3)
    .attr("opacity", 0).style("pointer-events", "none");

  slices.filter((d) => d.depth > 0 && d.data.member?.id === selectedWord?.id)
    .select(".highlight-ring").attr("opacity", 0.9);

  let focusedId = selectedWord?.id || null;

  // Hover + tooltip
  slices.filter((d) => d.depth > 0)
    .on("mouseenter", function (e, d) {
      if (d.data.member?.id === focusedId) return;
      d3.select(this).select("path").transition().duration(100)
        .attr("opacity", 1).attr("stroke", T.gold).attr("stroke-width", 2);
    })
    .on("mousemove", function (e, d) {
      const posColor = POS_CLR[d.data.pos] || T.dim;
      tooltip.style("display", "block")
        .style("left", e.clientX + 15 + "px").style("top", e.clientY - 10 + "px")
        .html(`<strong>${d.data.lemma}</strong><br>
          <span style="color:${posColor};font-weight:600">${d.data.pos}</span><br>
          <em style="color:${T.dim};font-size:11px">${d.data.def || ""}</em>
          ${d.data.relation ? `<br><span style="color:${T.goldDim};font-size:10px;font-family:${T.mono}">${d.data.relation}</span>` : ""}`);
    })
    .on("mouseleave", function (e, d) {
      if (d.data.member?.id !== focusedId) {
        d3.select(this).select("path").transition().duration(150)
          .attr("opacity", 0.85).attr("stroke", T.bg).attr("stroke-width", 1.5);
      }
      tooltip.style("display", "none");
    });

  // Click — highlight, rotate, notify parent
  slices.filter((d) => d.depth > 0)
    .on("click", function (e, d) {
      e.stopPropagation();
      spinG.selectAll(".highlight-ring").attr("opacity", 0);
      spinG.selectAll(".slice").select("path")
        .attr("stroke", T.bg).attr("stroke-width", 1.5).attr("opacity", 0.85);
      d3.select(this).select(".highlight-ring").attr("opacity", 0.9);
      focusedId = d.data.member?.id || null;
      if (d.data.member) onSelectRef.current(d.data.member);

      const midAngle = (d.x0 + d.x1) / 2;
      const targetRotation = -(midAngle * 180) / Math.PI + 90;

      spinG.transition().duration(600).ease(d3.easeCubicInOut)
        .attr("transform", `rotate(${targetRotation})`);
      spinG.selectAll(".root-text").transition().duration(600).ease(d3.easeCubicInOut)
        .attr("transform", `rotate(${-targetRotation})`);
      spinG.selectAll(".arc-label").each(function () {
        const labelD = d3.select(this).datum();
        const lMid = (labelD.x0 + labelD.x1) / 2;
        const lMidR = (innerR(labelD) + outerR(labelD)) / 2;
        const worldAngle = lMid + (targetRotation * Math.PI) / 180;
        const lx = lMidR * Math.sin(lMid);
        const ly = -lMidR * Math.cos(lMid);
        const wa = ((worldAngle % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
        const textRot = (lMid * 180) / Math.PI - 90 + (wa > Math.PI ? 180 : 0);
        d3.select(this).transition().duration(600).ease(d3.easeCubicInOut)
          .attr("transform", `translate(${lx},${ly}) rotate(${textRot})`);
      });
    });

  // Root text
  const rootG = slices.filter((d) => d.depth === 0);
  const rootTextG = rootG.append("g").attr("class", "root-text");
  const rFS = Math.min(20, Math.round(R_ROOT * 0.28));
  rootTextG.append("text").attr("text-anchor", "middle").attr("y", -rFS)
    .attr("fill", T.goldDim).attr("font-size", "9px").attr("font-family", T.mono)
    .attr("letter-spacing", "2px").text("ROOT");
  rootTextG.append("text").attr("text-anchor", "middle").attr("y", rFS * 0.3)
    .attr("fill", T.bright).attr("font-size", rFS + "px").attr("font-weight", 700)
    .attr("font-family", T.font).text(rootMember.lemma);
  rootTextG.append("text").attr("text-anchor", "middle").attr("y", rFS * 1.2)
    .attr("fill", POS_CLR[rootMember.pos] || T.dim).attr("font-size", "11px").attr("font-weight", 600)
    .attr("font-family", T.font).text(rootMember.pos || "");
  rootTextG.append("text").attr("text-anchor", "middle").attr("y", rFS * 2)
    .attr("fill", T.dim).attr("font-size", "9px").attr("font-style", "italic")
    .attr("font-family", T.font)
    .text((rootMember.short_def || "").length > 20
      ? (rootMember.short_def || "").slice(0, 20) + "\u2026" : rootMember.short_def || "");

  rootG.on("click", (e) => { e.stopPropagation(); onSelectRef.current(rootMember); });

  // Arc labels
  slices.filter((d) => d.depth > 0).each(function (d) {
    const el = d3.select(this);
    const midAngle = (d.x0 + d.x1) / 2;
    const midR = (innerR(d) + outerR(d)) / 2;
    const arcSpan = d.x1 - d.x0;
    if (arcSpan < 0.04) return;

    const x = midR * Math.sin(midAngle);
    const y = -midR * Math.cos(midAngle);
    const rotation = (midAngle * 180) / Math.PI - 90 + (midAngle > Math.PI ? 180 : 0);

    const textG = el.append("g").attr("class", "arc-label").datum(d)
      .attr("transform", `translate(${x},${y}) rotate(${rotation})`);

    const fontSize = arcSpan > 0.2 ? "13px" : arcSpan > 0.1 ? "11px" : "9px";
    const showDetails = arcSpan > 0.12;

    textG.append("text").attr("text-anchor", "middle")
      .attr("dy", showDetails ? "-0.3em" : "0.1em")
      .attr("fill", T.bright).attr("font-size", fontSize).attr("font-weight", 500)
      .attr("font-family", T.font).text(d.data.lemma);

    if (showDetails) {
      textG.append("text").attr("text-anchor", "middle").attr("dy", "1em")
        .attr("fill", POS_CLR[d.data.pos] || T.dim)
        .attr("font-size", "9px").attr("font-weight", 600)
        .attr("font-family", T.font).text(d.data.pos);
    }
    if (d.data.relation && arcSpan > 0.15) {
      textG.append("text").attr("text-anchor", "middle").attr("dy", "2.2em")
        .attr("fill", T.goldDim).attr("font-size", "7px").attr("font-family", T.mono)
        .attr("opacity", 0.7).text(d.data.relation);
    }
  });

  return { maxOuterR, cx, cy };
}

/* ═══════════════════════════════════════════════════════════
   drawTree — Orthogonal node-link tree layout for a
   derivational family.  Adapted from App.jsx FamilyTree
   with light theme, no superuser features.
   ═══════════════════════════════════════════════════════════ */

function drawTree(g, family, opts) {
  const { selectedWord, onSelectRef, linkedFamilies, expandedCrossIds, showExplicitLinked,
          setExpandedCrossIds, setShowExplicitLinked } = opts;

  const members = [...family.members];
  const rootIdx = findRoot(members);
  const root = members[rootIdx];
  const others = members.filter((_, i) => i !== rootIdx);

  const nW = 145, nH = 58, gap = 150;

  const { memberById, childrenOf } = buildChildMap(members, root);

  // Ring 1: direct children of root
  const ring1 = childrenOf.get(root.id) || [];
  const ring1Radius = Math.max(ring1.length * (nW * 0.3 + gap) / (2 * Math.PI), 170);

  const ring1Angles = new Map();
  ring1.forEach((m, i) => {
    ring1Angles.set(m.id, (i / ring1.length) * 2 * Math.PI - Math.PI / 2);
  });

  // Position map
  const posMap = new Map();
  posMap.set(root.id, { x: 0, y: 0 });

  ring1.forEach((m) => {
    const angle = ring1Angles.get(m.id);
    posMap.set(m.id, { x: Math.cos(angle) * ring1Radius, y: Math.sin(angle) * ring1Radius });
  });

  // Place deeper nodes
  const placeChildren = (parentId, parentAngle, parentR, depth) => {
    const kids = childrenOf.get(parentId) || [];
    if (kids.length === 0) return;
    const childR = parentR + (nH + gap * 0.8);
    const arcSpan = Math.min(kids.length * 0.25, 1.2);
    kids.forEach((m, i) => {
      const offset = kids.length === 1 ? 0 : (i / (kids.length - 1) - 0.5) * arcSpan;
      const angle = parentAngle + offset;
      posMap.set(m.id, { x: Math.cos(angle) * childR, y: Math.sin(angle) * childR });
      placeChildren(m.id, angle, childR, depth + 1);
    });
  };
  ring1.forEach((m) => {
    placeChildren(m.id, ring1Angles.get(m.id), ring1Radius, 2);
  });

  // Cross-family member IDs
  const crossFamilyIds = new Set();
  (linkedFamilies || []).forEach((lf) => {
    (lf.shared_members || []).forEach((id) => crossFamilyIds.add(id));
  });

  // Draw a node
  const drawNode = (parent, x, y, m, isRoot, scale, fId) => {
    if (scale <= 0) return;
    if (!fId) fId = family.id;

    const ng = parent.append("g")
      .attr("transform", `translate(${x},${y})`).style("cursor", "pointer");

    const clr = POS_CLR[m.pos] || T.dim;
    const isSel = m.id === selectedWord?.id;
    const baseW = isRoot ? 155 : nW;
    const baseH = isRoot ? 62 : nH;
    const w = baseW * scale;
    const h = baseH * scale;

    // Tiny dot for very small nodes
    if (scale < 0.5) {
      const dotR = Math.max(6 * scale, 3);
      ng.append("circle").attr("r", dotR).attr("fill", clr).attr("opacity", 0.5);
      if (scale >= 0.25) {
        ng.append("text").attr("text-anchor", "middle").attr("y", dotR + 10)
          .attr("fill", T.dim).attr("font-size", `${Math.max(7 * scale / 0.3, 5)}px`)
          .attr("font-family", T.font).attr("opacity", 0.6).text(m.lemma);
      }
      ng.on("click", (event) => { event.stopPropagation(); onSelectRef.current(m); });
      return;
    }

    // Selection glow
    if (isSel) {
      ng.append("rect").attr("x", -w / 2 - 6).attr("y", -h / 2 - 6)
        .attr("width", w + 12).attr("height", h + 12).attr("rx", 14 * scale)
        .attr("fill", T.gold).attr("opacity", 0.12);
    }

    // Node rect
    ng.append("rect").attr("x", -w / 2).attr("y", -h / 2)
      .attr("width", w).attr("height", h).attr("rx", 8 * scale)
      .attr("fill", isRoot ? T.raised : T.surface)
      .attr("stroke", isSel ? T.gold : (isRoot ? T.gold : clr))
      .attr("stroke-width", isSel ? 2 : (isRoot ? 1.5 : 0.8))
      .attr("stroke-opacity", isSel ? 1 : (isRoot ? 0.7 : 0.25));

    if (isRoot) {
      ng.append("text").attr("text-anchor", "middle").attr("y", -h / 2 - 4 * scale)
        .attr("fill", T.goldDim).attr("font-size", `${10 * scale}px`).attr("font-family", T.mono)
        .attr("letter-spacing", "1.5px").text("ROOT");
    }

    const fontSize = (isRoot ? 18 : 15) * scale;
    ng.append("text").attr("text-anchor", "middle").attr("y", (isRoot ? -10 : -12) * scale)
      .attr("fill", isSel ? T.gold : T.bright)
      .attr("font-size", `${fontSize}px`).attr("font-weight", (isRoot || isSel) ? 700 : 500)
      .attr("font-family", T.font).text(m.lemma);

    ng.append("text").attr("text-anchor", "middle").attr("y", (isRoot ? 5 : 1) * scale)
      .attr("fill", clr).attr("font-size", `${11 * scale}px`).attr("font-weight", 600)
      .attr("font-family", T.font).text(m.pos || "");

    if (scale >= 0.5) {
      const def = (m.short_def || "").replace(/,\s*$/, "");
      const maxChars = isRoot ? 35 : 25;
      const defText = def.length > maxChars ? def.slice(0, maxChars) + "\u2026" : def;
      ng.append("text").attr("text-anchor", "middle").attr("y", (isRoot ? 18 : 14) * scale)
        .attr("fill", T.dim).attr("font-size", `${11 * scale}px`).attr("font-style", "italic")
        .attr("font-family", T.font).text(defText);
    }

    // Child count badge
    const kidCount = (childrenOf.get(m.id) || []).length;
    if (kidCount > 0 && !isRoot) {
      ng.append("circle").attr("cx", w / 2 + 2).attr("cy", -h / 2 - 2)
        .attr("r", 7).attr("fill", T.gold).attr("opacity", 0.8);
      ng.append("text").attr("x", w / 2 + 2).attr("y", -h / 2 + 1)
        .attr("text-anchor", "middle").attr("fill", T.bg)
        .attr("font-size", "9px").attr("font-weight", 700)
        .attr("font-family", T.mono).text(kidCount);
    }

    // Cross-family badge
    if (crossFamilyIds.has(m.id) && fId === family.id) {
      const isExpanded = expandedCrossIds.has(m.id);
      const badge = ng.append("g").style("cursor", "pointer");
      badge.append("circle").attr("cx", -w / 2 - 2).attr("cy", -h / 2 - 2)
        .attr("r", 8).attr("fill", isExpanded ? T.gold : T.blue).attr("opacity", 0.9);
      badge.append("text").attr("x", -w / 2 - 2).attr("y", -h / 2 + 2)
        .attr("text-anchor", "middle").attr("fill", "#fff")
        .attr("font-size", "10px").attr("font-weight", 700)
        .attr("font-family", T.mono).text("\u27F7");
      badge.on("click", (event) => {
        event.stopPropagation();
        setExpandedCrossIds((prev) => {
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
    if (isRoot && (linkedFamilies || []).some((lf) => !lf.shared_members || lf.shared_members.length === 0)) {
      const badge = ng.append("g").style("cursor", "pointer");
      badge.append("circle").attr("cx", -w / 2 - 2).attr("cy", -h / 2 - 2)
        .attr("r", 8).attr("fill", showExplicitLinked ? T.gold : T.blue).attr("opacity", 0.9);
      badge.append("text").attr("x", -w / 2 - 2).attr("y", -h / 2 + 2)
        .attr("text-anchor", "middle").attr("fill", "#fff")
        .attr("font-size", "10px").attr("font-weight", 700)
        .attr("font-family", T.mono).text("\u27F7");
      badge.on("click", (event) => {
        event.stopPropagation();
        setShowExplicitLinked((prev) => !prev);
      });
      badge.on("mouseenter", function () {
        d3.select(this).select("circle").transition().duration(100).attr("r", 10);
      }).on("mouseleave", function () {
        d3.select(this).select("circle").transition().duration(100).attr("r", 8);
      });
    }

    // Hover
    ng.on("mouseenter", function () {
      d3.select(this).select("rect").transition().duration(80)
        .attr("stroke", T.gold).attr("stroke-opacity", 1);
    }).on("mouseleave", function () {
      if (m.id !== selectedWord?.id) {
        d3.select(this).select("rect").transition().duration(80)
          .attr("stroke", isRoot ? T.gold : clr)
          .attr("stroke-opacity", isRoot ? 0.7 : 0.25);
      }
    }).on("click", (event) => { event.stopPropagation(); onSelectRef.current(m); });
  };

  // Draw connections
  others.forEach((m) => {
    const pos = posMap.get(m.id);
    if (!pos) return;
    const pid = (m.parent_lemma_id && memberById.has(m.parent_lemma_id)) ? m.parent_lemma_id : root.id;
    const parentPos = posMap.get(pid) || { x: 0, y: 0 };

    g.append("line")
      .attr("x1", parentPos.x).attr("y1", parentPos.y)
      .attr("x2", pos.x).attr("y2", pos.y)
      .attr("stroke", T.border).attr("stroke-width", 1)
      .attr("stroke-dasharray", "4,4").attr("opacity", 0.5);

    if (m.relation && m.relation !== "root") {
      const lbl = m.relation.replace("prefix ", "").slice(0, 12);
      const mx = (parentPos.x + pos.x) * 0.5, my = (parentPos.y + pos.y) * 0.5;
      g.append("text").attr("x", mx).attr("y", my - 4)
        .attr("text-anchor", "middle").attr("fill", T.goldDim)
        .attr("font-size", "9px").attr("font-family", T.mono)
        .attr("opacity", 0.7).text(lbl);
    }
  });

  // Draw all nodes
  others.forEach((m) => {
    const pos = posMap.get(m.id);
    if (pos) drawNode(g, pos.x, pos.y, m, false, 1.0);
  });
  drawNode(g, 0, 0, root, true, 1.0);

  // Render linked families
  const linkedOffsets = [];
  const activeLinked = (linkedFamilies || []).filter((lf) => {
    if (lf.shared_members && lf.shared_members.length > 0) {
      return lf.shared_members.some((sid) => expandedCrossIds.has(sid));
    }
    return showExplicitLinked;
  });

  if (activeLinked.length > 0) {
    let mainMaxR = ring1Radius + nW / 2 + 30;
    posMap.forEach((pos) => {
      const dist = Math.sqrt(pos.x * pos.x + pos.y * pos.y) + nW;
      if (dist > mainMaxR) mainMaxR = dist;
    });

    activeLinked.forEach((lf, li) => {
      if (!lf.members || lf.members.length === 0) return;

      const lMembers = [...lf.members];
      const lRootIdx = findRoot(lMembers);
      const lRoot = lMembers[lRootIdx];
      const lOthers = lMembers.filter((_, i) => i !== lRootIdx);

      const { memberById: lMemberById, childrenOf: lChildrenOf } = buildChildMap(lMembers, lRoot);

      const lRing1 = lChildrenOf.get(lRoot.id) || [];
      const lRing1Radius = Math.max(lRing1.length * (nW * 0.3 + gap * 0.6) / (2 * Math.PI), 130);
      const linkedR = lRing1Radius + nW + 60;
      const separation = mainMaxR + linkedR + 100;

      let dirAngle = li * (Math.PI * 0.4) - ((activeLinked.length - 1) * Math.PI * 0.2);
      if (lf.shared_members && lf.shared_members.length > 0) {
        for (const sid of lf.shared_members) {
          const sp = posMap.get(sid);
          if (sp && (sp.x !== 0 || sp.y !== 0)) { dirAngle = Math.atan2(sp.y, sp.x); break; }
        }
      }
      const offsetX = Math.cos(dirAngle) * separation;
      const offsetY = Math.sin(dirAngle) * separation;

      const lPosMap = new Map();
      lPosMap.set(lRoot.id, { x: offsetX, y: offsetY });
      lRing1.forEach((m, i) => {
        const angle = (i / lRing1.length) * 2 * Math.PI - Math.PI / 2;
        lPosMap.set(m.id, {
          x: offsetX + Math.cos(angle) * lRing1Radius,
          y: offsetY + Math.sin(angle) * lRing1Radius,
        });
      });

      // Bridge lines
      const mainMemberIds = new Set((family.members || []).map((m) => m.id));
      const linkedMemberIds = new Set(lMembers.map((m) => m.id));
      const sharedIds = (lf.shared_members && lf.shared_members.length > 0)
        ? lf.shared_members.filter((sid) => mainMemberIds.has(sid) && linkedMemberIds.has(sid))
        : lMembers.filter((m) => mainMemberIds.has(m.id)).map((m) => m.id);

      if (sharedIds.length > 0) {
        sharedIds.forEach((sid) => {
          const mainPos = posMap.get(sid);
          const linkedPos = lPosMap.get(sid);
          if (!mainPos || !linkedPos) return;
          g.append("line")
            .attr("x1", mainPos.x).attr("y1", mainPos.y)
            .attr("x2", linkedPos.x).attr("y2", linkedPos.y)
            .attr("stroke", T.gold).attr("stroke-width", 2.5)
            .attr("stroke-dasharray", "8,6").attr("opacity", 0.6);
          const mx = (mainPos.x + linkedPos.x) / 2, my = (mainPos.y + linkedPos.y) / 2;
          const sharedMember = lMembers.find((m) => m.id === sid);
          g.append("text").attr("x", mx).attr("y", my - 8)
            .attr("text-anchor", "middle").attr("fill", T.gold)
            .attr("font-size", "10px").attr("font-family", T.mono)
            .attr("font-weight", 700).attr("opacity", 0.8)
            .text(sharedMember ? sharedMember.lemma : "shared");
        });
      } else {
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

      // Draw linked connections + nodes
      lOthers.forEach((m) => {
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
      lOthers.forEach((m) => {
        const pos = lPosMap.get(m.id);
        if (pos) drawNode(g, pos.x, pos.y, m, false, 0.75, lf.id);
      });
      drawNode(g, offsetX, offsetY, lRoot, true, 0.85, lf.id);

      lPosMap.forEach((pos) => linkedOffsets.push(pos));
    });
  }

  // Return bounding info for auto-fit
  let maxR = ring1Radius + nW / 2 + 30;
  posMap.forEach((pos) => {
    const dist = Math.sqrt(pos.x * pos.x + pos.y * pos.y);
    if (dist + nW / 2 + 30 > maxR) maxR = dist + nW / 2 + 30;
  });
  let minX = -maxR, maxX = maxR, minY = -maxR, maxY = maxR;
  linkedOffsets.forEach((pos) => {
    minX = Math.min(minX, pos.x - nW);
    maxX = Math.max(maxX, pos.x + nW);
    minY = Math.min(minY, pos.y - nH);
    maxY = Math.max(maxY, pos.y + nH);
  });
  return { minX, maxX, minY, maxY };
}

/* ═══════════════════════════════════════════════════════════
   EmbedSunburst — main widget component
   ═══════════════════════════════════════════════════════════ */

export default function EmbedSunburst() {
  const [lemmaText, setLemmaText] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("lemma") || "";
  });
  const [family, setFamily] = useState(null);
  const [linkedFamilies, setLinkedFamilies] = useState([]);
  const [selectedWord, setSelectedWord] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [size, setSize] = useState({ width: window.innerWidth, height: window.innerHeight });
  const [vizMode, setVizMode] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("mode") || "tree";
  });
  const [expandedCrossIds, setExpandedCrossIds] = useState(new Set());
  const [showExplicitLinked, setShowExplicitLinked] = useState(false);

  const containerRef = useRef(null);
  const svgRef = useRef(null);
  const zoomRef = useRef(null);
  const onSelectRef = useRef(() => {});

  // Notify parent that widget is ready
  useEffect(() => {
    window.parent.postMessage({ type: "glossalearn:ready" }, "*");
  }, []);

  // Listen for postMessage from Scaife parent
  useEffect(() => {
    function handler(e) {
      if (e.data?.type === "glossalearn:setLemma" && e.data.lemma) {
        setLemmaText(e.data.lemma);
      }
    }
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  // Track container size
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ width, height });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Handle node selection — notify parent
  onSelectRef.current = useCallback(
    (member) => {
      setSelectedWord(member);
      window.parent.postMessage(
        { type: "glossalearn:selectWord", lemma: member.lemma, id: member.id, pos: member.pos },
        "*"
      );
    },
    []
  );

  // Fetch lemma data when lemmaText changes
  useEffect(() => {
    if (!lemmaText) {
      setFamily(null);
      setLinkedFamilies([]);
      setSelectedWord(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`${API}/lemma/by-name/${encodeURIComponent(lemmaText)}`)
      .then((r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "not_found" : "api_error");
        return r.json();
      })
      .then((data) => {
        if (cancelled) return;
        if (data.family) {
          setFamily(data.family);
          const match = data.family.members?.find(
            (m) => m.lemma === lemmaText || m.id === data.id
          );
          setSelectedWord(match || null);

          // Fetch linked families
          fetch(`${API}/family/${data.family.id}/linked`)
            .then((r) => (r.ok ? r.json() : { linked_families: [] }))
            .then((ld) => {
              if (!cancelled) setLinkedFamilies(ld.linked_families || []);
            })
            .catch(() => { if (!cancelled) setLinkedFamilies([]); });
        } else {
          setFamily(null);
          setLinkedFamilies([]);
          setError("no_family");
        }
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoading(false);
        setFamily(null);
        setLinkedFamilies([]);
        if (err.message === "not_found") {
          setError("not_found");
          window.parent.postMessage(
            { type: "glossalearn:error", message: `Lemma "${lemmaText}" not found` }, "*"
          );
        } else {
          setError("api_error");
          window.parent.postMessage({ type: "glossalearn:error", message: "API error" }, "*");
        }
      });

    return () => { cancelled = true; };
  }, [lemmaText]);

  // D3 rendering
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    let g = svg.select("g.family-content");
    if (g.empty()) g = svg.append("g").attr("class", "family-content");

    // Setup zoom once
    if (!zoomRef.current) {
      const zoom = d3.zoom()
        .scaleExtent([0.05, 3])
        .on("zoom", (event) => g.attr("transform", event.transform));
      svg.call(zoom);
      svg.style("cursor", "grab");
      svg.on("mousedown.cursor", () => svg.style("cursor", "grabbing"));
      svg.on("mouseup.cursor", () => svg.style("cursor", "grab"));
      zoomRef.current = zoom;
    }

    g.selectAll("*").remove();
    d3.select("body").selectAll(".widget-tooltip").remove();

    if (!family?.members?.length) {
      if (zoomRef.current) {
        svg.call(zoomRef.current.transform, d3.zoomIdentity.translate(size.width / 2, size.height / 2));
      }
      return;
    }

    if (vizMode === "sunburst") {
      // Sunburst mode
      const tooltip = d3.select("body").selectAll(".widget-tooltip").data([0]).join("div")
        .attr("class", "widget-tooltip")
        .style("position", "fixed").style("pointer-events", "none")
        .style("background", T.surface).style("border", `1px solid ${T.border}`)
        .style("border-radius", "6px").style("padding", "8px 12px")
        .style("font-size", "13px").style("color", T.bright)
        .style("display", "none").style("z-index", "999")
        .style("font-family", T.font).style("box-shadow", "0 2px 8px rgba(0,0,0,0.12)");

      const opts = { selectedWord, onSelectRef, tooltip, isLinked: false };
      const main = drawSunburst(g, family.members, 0, 0, opts);

      const allBursts = [main];
      if (linkedFamilies && linkedFamilies.length > 0) {
        let nextX = main.maxOuterR;
        linkedFamilies.forEach((lf) => {
          if (!lf.members || lf.members.length === 0) return;
          const leafCount = lf.members.length;
          const rScale = Math.max(1, leafCount / 14) * 0.7;
          const estMaxR = Math.round(320 * rScale);
          const gapX = 120;
          const cx = nextX + gapX + estMaxR;
          const cy = 0;

          g.append("line")
            .attr("x1", main.cx).attr("y1", main.cy)
            .attr("x2", cx).attr("y2", cy)
            .attr("stroke", T.gold).attr("stroke-width", 2.5)
            .attr("stroke-dasharray", "10,8").attr("opacity", 0.4);

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

      // Auto-fit
      if (zoomRef.current) {
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        allBursts.forEach((b) => {
          minX = Math.min(minX, b.cx - b.maxOuterR);
          maxX = Math.max(maxX, b.cx + b.maxOuterR);
          minY = Math.min(minY, b.cy - b.maxOuterR);
          maxY = Math.max(maxY, b.cy + b.maxOuterR);
        });
        const totalW = maxX - minX + 80;
        const totalH = maxY - minY + 80;
        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;
        const fitScale = Math.min(size.width / totalW, size.height / totalH);
        svg.call(zoomRef.current.transform, d3.zoomIdentity
          .translate(size.width / 2 - centerX * fitScale, size.height / 2 - centerY * fitScale)
          .scale(fitScale));
      }
    } else {
      // Tree mode
      const treeOpts = {
        selectedWord, onSelectRef, linkedFamilies,
        expandedCrossIds, showExplicitLinked,
        setExpandedCrossIds, setShowExplicitLinked,
      };
      const bounds = drawTree(g, family, treeOpts);

      // Auto-fit
      if (zoomRef.current) {
        const totalW = bounds.maxX - bounds.minX + 80;
        const totalH = bounds.maxY - bounds.minY + 80;
        const cx = (bounds.minX + bounds.maxX) / 2;
        const cy = (bounds.minY + bounds.maxY) / 2;
        const fitScale = Math.min(size.width / totalW, size.height / totalH, 1);
        svg.call(zoomRef.current.transform, d3.zoomIdentity
          .translate(size.width / 2 - cx * fitScale, size.height / 2 - cy * fitScale)
          .scale(fitScale));
      }
    }
  }, [family, selectedWord, linkedFamilies, size, vizMode, expandedCrossIds, showExplicitLinked]);

  // Status overlays
  const overlay = (content) => (
    <div style={{
      position: "absolute", inset: 0, display: "flex", alignItems: "center",
      justifyContent: "center", flexDirection: "column", gap: 8,
      pointerEvents: "none", fontFamily: T.font, color: T.dim,
    }}>
      {content}
    </div>
  );

  return (
    <div ref={containerRef} style={{
      width: "100vw", height: "100vh", position: "relative",
      background: T.bg, overflow: "hidden",
    }}>
      <svg ref={svgRef} width={size.width} height={size.height}
        style={{ position: "absolute", top: 0, left: 0, display: "block", background: T.bg }} />

      {/* View mode toggle */}
      {family && !loading && !error && (
        <div style={{
          position: "absolute", top: 8, right: 8, display: "flex", gap: 2,
          background: "rgba(255,255,255,0.85)", borderRadius: 4, padding: 2,
          border: `1px solid ${T.border}`, zIndex: 10,
          backdropFilter: "blur(4px)",
        }}>
          <span style={{ fontSize: 11, color: T.dim, padding: "2px 6px", fontFamily: T.font }}>View:</span>
          {["tree", "sunburst"].map((m) => (
            <button key={m} onClick={() => setVizMode(m)} style={{
              background: vizMode === m ? T.bright : "transparent",
              color: vizMode === m ? T.bg : T.dim,
              border: `1px solid ${vizMode === m ? T.bright : T.borderL}`,
              borderRadius: 3, padding: "2px 8px", fontSize: 11, fontWeight: 600,
              cursor: "pointer", fontFamily: T.font,
            }}>
              {m === "tree" ? "Tree" : "Sunburst"}
            </button>
          ))}
        </div>
      )}

      {loading && overlay(
        <><div style={{ fontSize: 16, color: T.gold }}>Loading...</div>
          <div style={{ fontSize: 13 }}>{lemmaText}</div></>
      )}

      {!loading && error === "not_found" && overlay(
        <><div style={{ fontSize: 18, color: T.text }}>Word not found</div>
          <div style={{ fontSize: 14 }}><strong>{lemmaText}</strong> is not in the database</div></>
      )}

      {!loading && error === "no_family" && overlay(
        <><div style={{ fontSize: 18, color: T.text }}>No derivational family</div>
          <div style={{ fontSize: 14 }}><strong>{lemmaText}</strong> has no recorded derivational connections</div></>
      )}

      {!loading && error === "api_error" && overlay(
        <div style={{ fontSize: 16, color: T.red }}>Unable to reach GlossaLearn API</div>
      )}

      {!loading && !error && !lemmaText && overlay(
        <><div style={{ fontSize: 32, opacity: 0.15 }}>&#x27E1;</div>
          <div style={{ fontSize: 15 }}>Select a word to see its derivational family</div></>
      )}
    </div>
  );
}
