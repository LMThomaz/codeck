import type { Commit } from "./types";

// Layout do graph (estilo GitKraken): cada commit ganha uma faixa (lane) e cada linha desenha os trechos
// que entram (topo → nó) e saem (nó → base) da linha. Cores seguem a faixa, não a branch.
export const LANE_COLORS = ["#6f8cff", "#3ccf91", "#f5b84f", "#ff7a9a", "#b48cff", "#4fc3f7", "#ff9d5c", "#7ad6c0", "#e6d36a", "#9aa9ff"];

export interface Seg { from: number; to: number; color: string }
export interface Row { lane: number; color: string; top: Seg[]; bottom: Seg[]; width: number; merge: boolean }

export function layout(commits: Commit[]): { rows: Row[]; maxLanes: number } {
  const lanes: (string | null)[] = [];
  const colors: string[] = [];
  let colorSeq = 0;
  const rows: Row[] = [];
  let maxLanes = 1;
  const newColor = () => LANE_COLORS[colorSeq++ % LANE_COLORS.length];

  for (const c of commits) {
    let lane = lanes.indexOf(c.sha);
    if (lane === -1) {
      lane = lanes.indexOf(null);
      if (lane === -1) { lane = lanes.length; lanes.push(null); }
      colors[lane] = newColor();
    }
    const color = colors[lane];
    const top: Seg[] = [];
    // trechos que chegam de cima: toda faixa ocupada continua; as que esperavam este commit convergem no nó
    lanes.forEach((sha, i) => {
      if (sha === null) return;
      top.push({ from: i, to: sha === c.sha ? lane : i, color: colors[i] });
    });
    // faixas que esperavam este commit (filhos em faixas diferentes) se fecham aqui
    lanes.forEach((sha, i) => { if (sha === c.sha && i !== lane) lanes[i] = null; });

    const [first, ...rest] = c.parents;
    lanes[lane] = first ?? null;
    const bottom: Seg[] = [];
    if (first) bottom.push({ from: lane, to: lane, color });
    for (const p of rest) {
      let j = lanes.indexOf(p);
      if (j === -1) {
        j = lanes.indexOf(null);
        if (j === -1) { j = lanes.length; lanes.push(null); }
        lanes[j] = p;
        colors[j] = newColor();
      }
      bottom.push({ from: lane, to: j, color: colors[j] });
    }
    lanes.forEach((sha, i) => {
      if (sha !== null && i !== lane && !rest.includes(sha)) bottom.push({ from: i, to: i, color: colors[i] });
    });
    // compacta faixas vazias no fim
    while (lanes.length && lanes[lanes.length - 1] === null) lanes.pop();
    const width = Math.max(lane + 1, ...top.map(s => Math.max(s.from, s.to) + 1), ...bottom.map(s => Math.max(s.from, s.to) + 1));
    maxLanes = Math.max(maxLanes, width);
    rows.push({ lane, color, top, bottom, width, merge: c.parents.length > 1 });
  }
  return { rows, maxLanes };
}

export interface RefLabel { kind: "head" | "local" | "remote" | "tag"; name: string; current?: boolean; synced?: boolean }

const REMOTES = ["origin", "upstream"];

export function parseRefs(refs: string[]): RefLabel[] {
  const out: RefLabel[] = [];
  for (const r of refs) {
    if (r.startsWith("HEAD -> ")) out.push({ kind: "local", name: r.slice(8), current: true });
    else if (r === "HEAD") out.push({ kind: "head", name: "HEAD" });
    else if (r.startsWith("tag: ")) out.push({ kind: "tag", name: r.slice(5) });
    else if (REMOTES.includes(r.split("/")[0]) && r.includes("/")) out.push({ kind: "remote", name: r });
    else out.push({ kind: "local", name: r });
  }
  // a branch local e a remota no mesmo commit viram uma etiqueta só, marcada como sincronizada
  for (const l of out) {
    if (l.kind === "local" && out.some(o => o.kind === "remote" && o.name.split("/").slice(1).join("/") === l.name)) l.synced = true;
  }
  return out.filter(l => !(l.kind === "remote" && out.some(o => o.kind === "local" && o.synced && l.name.split("/").slice(1).join("/") === o.name)));
}
