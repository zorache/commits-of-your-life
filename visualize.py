#!/usr/bin/env python3
"""
Generate multi-library git visualizations from generated life repos.
Produces an HTML page comparing Sonnet vs Opus side-by-side
with three renderers: Mermaid gitgraph, custom SVG metro map, and ASCII git log.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional
from git import Repo


def _extract_keyword(msg: str) -> str:
    """Pull one evocative word from a commit message."""
    SKIP = {"start", "begin", "add", "end", "move", "complete", "return",
            "get", "make", "update", "merge", "initialize", "close",
            "open", "set", "run", "the", "a", "an", "to", "in", "of",
            "and", "for", "from", "with", "at", "on", "into", "after",
            "branch", "commit", "first", "new", "back"}
    # Short capitalized words that typically prefix a place name
    PREFIXES = {"san", "new", "north", "south", "east", "west", "los", "el", "st"}
    words = msg.split()

    def _clean(w):
        w = w.strip(".,;:!?'\"()")
        if w.endswith("'s"):
            w = w[:-2]
        return w

    # Prefer capitalized words that aren't sentence-initial
    for idx, w in enumerate(words[1:], 1):
        clean = _clean(w)
        if not clean or not clean[0].isupper():
            continue
        if clean.lower() in SKIP:
            continue
        # Skip standalone place-name prefixes — they'll be picked up as part of next word
        if clean.lower() in PREFIXES:
            if idx + 1 < len(words) and _clean(words[idx + 1])[0:1].isupper():
                continue  # let the next word pick it up
        # If previous word is a place-name prefix, combine them
        if idx > 0 and _clean(words[idx - 1]).lower() in PREFIXES:
            combined = _clean(words[idx - 1]) + " " + clean
            return combined[:12]
        return clean[:12]
    # Fallback: last non-skip word
    for w in reversed(words):
        clean = _clean(w)
        if clean.lower() not in SKIP:
            return clean[:12]
    return words[-1][:12] if words else "?"


def load_branch_meta(repo_path: str) -> Optional[dict]:
    """Load .branch_meta.json if it exists, else return None."""
    meta_path = Path(repo_path) / ".branch_meta.json"
    if meta_path.exists():
        with open(meta_path) as f:
            return json.load(f)
    return None


def _infer_commit_branch(all_commits, repo) -> dict:
    """Fallback heuristic: map commit -> branch by smallest branch set."""
    branch_commits = {}
    for branch in repo.branches:
        branch_commits[branch.name] = set(c.hexsha for c in repo.iter_commits(branch))

    commit_branch = {}
    for commit in all_commits:
        best_branch = "main"
        best_size = float("inf")
        for bname, bset in branch_commits.items():
            if commit.hexsha in bset and len(bset) < best_size:
                best_branch = bname
                best_size = len(bset)
        commit_branch[commit.hexsha] = best_branch
    return commit_branch


def extract_graph_data(repo_path: str) -> dict:
    """Extract structured git graph data from a repo for JS-based renderers."""
    repo = Repo(repo_path)

    all_commits = list(repo.iter_commits("--all"))
    all_commits.reverse()  # chronological

    meta = load_branch_meta(repo_path)
    if meta:
        branch_map = meta["branch_map"]
        commit_branch = {}
        for c in all_commits:
            commit_branch[c.hexsha] = branch_map.get(c.hexsha, "main")
        merge_meta = meta.get("merge_commits", {})
        keyword_meta = meta.get("keyword_map", {})
    else:
        commit_branch = _infer_commit_branch(all_commits, repo)
        merge_meta = {}
        keyword_meta = {}

    # Detect merges
    merge_shas = set()
    for c in all_commits:
        if len(c.parents) > 1:
            merge_shas.add(c.hexsha)

    # Build JSON-serializable structure
    commits = []
    branches_seen = set()
    for c in all_commits:
        branch = commit_branch[c.hexsha]
        branches_seen.add(branch)
        msg = c.message.strip().split("\n")[0]
        # Prefer LLM-generated keyword from metadata, fall back to heuristic
        keyword = keyword_meta.get(c.hexsha, "") or _extract_keyword(msg)
        commits.append({
            "hash": c.hexsha[:8],
            "message": msg,
            "keyword": keyword,
            "branch": branch,
            "is_merge": c.hexsha in merge_shas,
            "parents": [p.hexsha[:8] for p in c.parents],
            "date": c.committed_datetime.isoformat(),
        })

    # Ordered branch list
    if meta:
        branch_order = meta["branch_order"]
    else:
        branch_order = ["main"]
        for c in commits:
            if c["branch"] not in branch_order:
                branch_order.append(c["branch"])

    return {
        "commits": commits,
        "branches": branch_order,
        "num_commits": len(commits),
        "num_branches": len(branch_order),
    }


def repo_to_mermaid(repo_path: str) -> str:
    """Convert repo to Mermaid gitgraph syntax."""
    repo = Repo(repo_path)
    all_commits = list(repo.iter_commits("--all"))
    all_commits.reverse()

    meta = load_branch_meta(repo_path)
    if meta:
        branch_map = meta["branch_map"]
        commit_branch = {}
        for c in all_commits:
            commit_branch[c.hexsha] = branch_map.get(c.hexsha, "main")
        merge_meta = meta.get("merge_commits", {})
    else:
        commit_branch = _infer_commit_branch(all_commits, repo)
        merge_meta = {}

    lines = ["gitGraph LR:"]
    active_branch = "main"
    seen_branches = set(["main"])

    for commit in all_commits:
        branch = commit_branch[commit.hexsha]
        date_str = commit.committed_datetime.strftime("%Y-%m-%d")
        msg = commit.message.strip().replace('"', "'").replace("\n", " ")
        if len(msg) > 40:
            msg = msg[:37] + "..."
        label = f"{date_str} {msg}"

        is_merge = len(commit.parents) > 1

        if branch != active_branch:
            if branch not in seen_branches:
                lines.append(f'    branch "{branch}"')
                seen_branches.add(branch)
            else:
                lines.append(f'    checkout "{branch}"')
            active_branch = branch

        if is_merge:
            merged_branch = merge_meta.get(commit.hexsha)
            if branch == "main" and merged_branch:
                lines.append(f'    merge "{merged_branch}" id: "{label}"')
            else:
                lines.append(f'    commit id: "{label}" type: HIGHLIGHT')
        else:
            lines.append(f'    commit id: "{label}"')

    return "\n".join(lines)


def get_ascii_graph(repo_path: str) -> str:
    """Get ASCII git log --graph output with dates."""
    result = subprocess.run(
        ["git", "log", "--all", "--graph", "--decorate",
         "--format=%C(auto)%h %C(dim)%ad%C(reset) %s%C(auto)%d",
         "--date=short"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.stdout


def generate_html(repos: list) -> str:
    """Generate HTML page with three visualization libraries, side by side."""

    # Extract data for each repo
    repo_data = []
    for repo_path, label in repos:
        graph = extract_graph_data(repo_path)
        mermaid = repo_to_mermaid(repo_path)
        ascii_graph = get_ascii_graph(repo_path)
        repo_data.append({
            "label": label,
            "path": repo_path,
            "graph": graph,
            "mermaid": mermaid,
            "ascii": ascii_graph,
        })

    graph_json = json.dumps([r["graph"] for r in repo_data])

    # Build the side-by-side panels
    mermaid_panels = ""
    ascii_panels = ""
    metro_panels = ""
    story_panels = ""

    for i, rd in enumerate(repo_data):
        stats = f"{rd['graph']['num_commits']} commits &middot; {rd['graph']['num_branches']} branches"
        mermaid_panels += f"""
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">{rd['label']}</span>
                    <span class="panel-stats">{stats}</span>
                </div>
                <pre class="mermaid">
{rd['mermaid']}
                </pre>
            </div>"""

        ascii_panels += f"""
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">{rd['label']}</span>
                    <span class="panel-stats">{stats}</span>
                </div>
                <pre class="ascii-graph">{rd['ascii']}</pre>
            </div>"""

        metro_panels += f"""
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">{rd['label']}</span>
                    <span class="panel-stats">{stats}</span>
                </div>
                <div class="metro-container" id="metro-{i}"></div>
            </div>"""

        story_panels += f"""
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">{rd['label']}</span>
                    <span class="panel-stats">{stats}</span>
                </div>
                <div class="story-outer">
                    <div class="story-intro" id="story-intro-{i}">
                        <div class="story-intro-title">commits of your life<span class="story-intro-cursor"></span></div>
                    </div>
                    <div class="story-fade-left" id="story-fade-{i}"></div>
                    <div class="story-container" id="story-{i}"></div>
                </div>
            </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Life Repository Visualization</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: "Times New Roman", Times, serif;
            background: #f5f5f0;
            color: #333;
        }}
        .page-header {{
            text-align: center;
            padding: 50px 40px 30px;
        }}
        h1 {{
            font-size: 2.4em;
            font-weight: normal;
            margin-bottom: 8px;
        }}
        .subtitle {{
            color: #999;
            font-style: italic;
        }}

        /* Tab navigation */
        .tab-nav {{
            display: flex;
            justify-content: center;
            gap: 0;
            margin: 30px auto 0;
            border-bottom: 1px solid #ccc;
            max-width: 600px;
        }}
        .tab-btn {{
            font-family: "Courier New", monospace;
            font-size: 0.95em;
            padding: 12px 28px;
            border: 1px solid #ccc;
            border-bottom: none;
            background: #eee;
            cursor: pointer;
            color: #666;
            transition: all 0.2s;
        }}
        .tab-btn:first-child {{ border-radius: 6px 0 0 0; }}
        .tab-btn:last-child {{ border-radius: 0 6px 0 0; }}
        .tab-btn.active {{
            background: #fff;
            color: #333;
            border-bottom: 1px solid #fff;
            margin-bottom: -1px;
            font-weight: bold;
        }}

        /* Tab content */
        .tab-content {{
            display: none;
            padding: 40px;
        }}
        .tab-content.active {{
            display: block;
        }}

        /* Side-by-side layout */
        .side-by-side {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }}
        @media (max-width: 1200px) {{
            .side-by-side {{
                grid-template-columns: 1fr;
            }}
        }}

        .panel {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 4px;
            overflow: hidden;
        }}
        .panel-header {{
            display: flex;
            align-items: baseline;
            gap: 16px;
            padding: 16px 20px;
            border-bottom: 1px solid #eee;
            background: #fafafa;
        }}
        .panel-title {{
            font-size: 1.3em;
            font-weight: normal;
        }}
        .panel-stats {{
            font-family: "Courier New", monospace;
            font-size: 0.8em;
            color: #999;
        }}

        .mermaid {{
            padding: 20px;
            overflow-x: auto;
            min-height: 150px;
        }}
        .ascii-graph {{
            font-family: "Courier New", "SF Mono", monospace;
            font-size: 12px;
            line-height: 1.5;
            padding: 20px;
            overflow-x: auto;
            white-space: pre;
            background: #1a1a2e;
            color: #e0e0e0;
            min-height: 200px;
            max-height: 600px;
            overflow-y: auto;
        }}
        .metro-container {{
            padding: 20px;
            overflow-x: auto;
            min-height: 300px;
        }}

        /* Story view */
        .story-outer {{
            position: relative;
            overflow: hidden;
        }}
        .story-container {{
            position: relative;
            overflow-x: auto;
            overflow-y: hidden;
            min-height: 340px;
            padding: 0;
            scrollbar-width: none;
        }}
        .story-container::-webkit-scrollbar {{ display: none; }}
        .story-svg-wrap {{
            transform-origin: left center;
            transition: transform 0.05s linear;
            will-change: transform;
        }}
        .story-fade-left {{
            position: absolute;
            top: 0; left: 0; bottom: 0;
            width: 120px;
            background: linear-gradient(to right, #fff 0%, #fff 10%, transparent 100%);
            z-index: 5;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.3s;
        }}
        .story-fade-left.visible {{ opacity: 1; }}
        .story-intro {{
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            z-index: 8;
            background: #fff;
            transition: opacity 1s ease-out;
            pointer-events: none;
        }}
        .story-intro.faded {{ opacity: 0; }}
        .story-intro-title {{
            font-family: Georgia, "Times New Roman", serif;
            font-size: 22px;
            font-weight: normal;
            color: #222;
            letter-spacing: 0.01em;
        }}
        .story-intro-cursor {{
            display: inline-block;
            width: 1.5px;
            height: 22px;
            background: #222;
            margin-left: 3px;
            vertical-align: text-bottom;
            animation: story-blink 1s step-end infinite;
        }}
        @keyframes story-blink {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0; }}
        }}
        .story-popover {{
            position: absolute;
            pointer-events: none;
            background: #fff;
            border: 1px solid #e0e0e0;
            border-radius: 3px;
            padding: 10px 14px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.08);
            font-family: Georgia, "Times New Roman", serif;
            font-size: 13px;
            line-height: 1.5;
            z-index: 10;
            max-width: 280px;
            display: none;
        }}
        .story-popover .date {{ color: #aaa; font-family: "Courier New", monospace; font-size: 11px; }}
        .story-popover .msg {{ margin-top: 4px; font-style: italic; color: #444; }}
        .story-popover .branch-tag {{ color: #bbb; font-size: 10px; margin-top: 6px; font-family: "Courier New", monospace; }}
        .story-dot {{ cursor: pointer; }}
        .story-dot text {{ transition: opacity 0.2s; }}
        .story-dot:hover text {{ opacity: 0.5; }}

        /* Viz type description */
        .viz-description {{
            text-align: center;
            color: #888;
            font-style: italic;
            font-size: 0.9em;
            margin-bottom: 25px;
        }}

        /* Metro map styles */
        .metro-commit {{
            cursor: default;
        }}
        .metro-commit:hover .metro-label {{
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="page-header">
        <h1>Commits of Your Life</h1>
        <p class="subtitle">Sonnet 4.6 vs Opus 4.6 &mdash; four ways to see a life</p>
    </div>

    <nav class="tab-nav">
        <button class="tab-btn active" data-tab="story">Story</button>
        <button class="tab-btn" data-tab="mermaid">Mermaid Gitgraph</button>
        <button class="tab-btn" data-tab="metro">Metro Map</button>
        <button class="tab-btn" data-tab="ascii">ASCII Log</button>
    </nav>

    <div class="tab-content active" id="tab-story">
        <p class="viz-description">One word per moment &mdash; hover for the full story</p>
        <div class="side-by-side">{story_panels}
        </div>
    </div>

    <div class="tab-content" id="tab-mermaid">
        <p class="viz-description">Mermaid.js &mdash; declarative branch diagrams, left-to-right flow</p>
        <div class="side-by-side">{mermaid_panels}
        </div>
    </div>

    <div class="tab-content" id="tab-metro">
        <p class="viz-description">Custom SVG &mdash; main is the spine, branches curve away and merge back</p>
        <div class="side-by-side">{metro_panels}
        </div>
    </div>

    <div class="tab-content" id="tab-ascii">
        <p class="viz-description">git log --all --graph --oneline &mdash; the classic terminal view</p>
        <div class="side-by-side">{ascii_panels}
        </div>
    </div>

    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            gitGraph: {{
                mainBranchName: 'main',
                showCommitLabel: true,
                rotateCommitLabel: true
            }},
            themeVariables: {{
                commitLabelFontSize: '10px'
            }}
        }});
    </script>

    <script>
        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
            }});
        }});

        // River renderer — main is a horizontal spine, branches curve away and merge back
        const GRAPHS = {graph_json};

        const BRANCH_COLORS = [
            '#2d2d2d',  // main - dark
            '#e63946',  // red
            '#457b9d',  // steel blue
            '#2a9d8f',  // teal
            '#e9c46a',  // gold
            '#f4a261',  // sandy
            '#264653',  // dark teal
            '#9b5de5',  // purple
        ];

        function renderMetro(containerId, graph) {{
            const container = document.getElementById(containerId);
            const commits = graph.commits;
            const branches = graph.branches;

            const COL_W = 46;
            const OFFSET_Y = 50;  // how far branches curve away from main
            const PADDING_X = 30;
            const PADDING_TOP = 120; // room for labels above
            const R = 5;

            // Main sits at center Y. Non-main branches alternate above/below.
            // Assign offsets: branch index 1 -> above, 2 -> below, 3 -> further above, etc.
            const branchOffset = {{}};
            branchOffset['main'] = 0;
            let slot = 1;
            for (const b of branches) {{
                if (b === 'main') continue;
                // Alternate: odd slots go above (negative), even go below (positive)
                const direction = (slot % 2 === 1) ? -1 : 1;
                const level = Math.ceil(slot / 2);
                branchOffset[b] = direction * level * OFFSET_Y;
                slot++;
            }}

            const maxAbove = Math.min(...Object.values(branchOffset));
            const maxBelow = Math.max(...Object.values(branchOffset));
            const centerY = PADDING_TOP + Math.abs(maxAbove);
            const width = commits.length * COL_W + PADDING_X * 2 + 100;
            const height = centerY + maxBelow + PADDING_TOP + 20;

            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('width', width);
            svg.setAttribute('height', height);
            svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
            svg.style.fontFamily = '"Courier New", monospace';

            // Faint main line across the full width
            const mainLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            mainLine.setAttribute('x1', PADDING_X);
            mainLine.setAttribute('y1', centerY);
            mainLine.setAttribute('x2', commits.length * COL_W + PADDING_X);
            mainLine.setAttribute('y2', centerY);
            mainLine.setAttribute('stroke', '#ddd');
            mainLine.setAttribute('stroke-width', '1');
            svg.appendChild(mainLine);

            // Position each commit
            const hashToPos = {{}};
            commits.forEach((c, i) => {{
                hashToPos[c.hash] = {{
                    x: PADDING_X + i * COL_W,
                    y: centerY + branchOffset[c.branch]
                }};
            }});

            // Collect segments per branch for drawing continuous branch lines
            const branchSegments = {{}};
            commits.forEach((c, i) => {{
                if (!branchSegments[c.branch]) branchSegments[c.branch] = [];
                branchSegments[c.branch].push(hashToPos[c.hash]);
            }});

            // Draw branch lines (continuous colored paths per branch)
            for (const [bname, points] of Object.entries(branchSegments)) {{
                if (points.length < 2) continue;
                const bIdx = branches.indexOf(bname);
                const color = BRANCH_COLORS[bIdx % BRANCH_COLORS.length];

                for (let j = 1; j < points.length; j++) {{
                    const p0 = points[j-1];
                    const p1 = points[j];
                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('x1', p0.x);
                    line.setAttribute('y1', p0.y);
                    line.setAttribute('x2', p1.x);
                    line.setAttribute('y2', p1.y);
                    line.setAttribute('stroke', color);
                    line.setAttribute('stroke-width', bname === 'main' ? '2.5' : '1.8');
                    line.setAttribute('stroke-opacity', bname === 'main' ? '0.8' : '0.5');
                    svg.appendChild(line);
                }}
            }}

            // Draw fork/merge curves connecting branches to main
            commits.forEach((c, i) => {{
                const pos = hashToPos[c.hash];
                c.parents.forEach(ph => {{
                    const parentPos = hashToPos[ph];
                    if (!parentPos) return;
                    // Only draw curves when crossing between branches
                    if (parentPos.y === pos.y) return;

                    const bIdx = branches.indexOf(c.branch);
                    const color = BRANCH_COLORS[bIdx % BRANCH_COLORS.length];
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    const dx = Math.abs(pos.x - parentPos.x) * 0.4;
                    path.setAttribute('d',
                        `M${{parentPos.x}},${{parentPos.y}} C${{parentPos.x + dx}},${{parentPos.y}} ${{pos.x - dx}},${{pos.y}} ${{pos.x}},${{pos.y}}`);
                    path.setAttribute('stroke', color);
                    path.setAttribute('stroke-width', '1.8');
                    path.setAttribute('fill', 'none');
                    path.setAttribute('stroke-opacity', '0.45');
                    svg.appendChild(path);
                }});
            }});

            // Draw year markers along the main axis
            let lastYear = null;
            commits.forEach((c, i) => {{
                const year = c.date.slice(0, 4);
                if (year !== lastYear) {{
                    lastYear = year;
                    const x = hashToPos[c.hash].x;
                    // Tick mark
                    const tick = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    tick.setAttribute('x1', x);
                    tick.setAttribute('y1', centerY - 4);
                    tick.setAttribute('x2', x);
                    tick.setAttribute('y2', centerY + 4);
                    tick.setAttribute('stroke', '#999');
                    tick.setAttribute('stroke-width', '1');
                    svg.appendChild(tick);
                    // Year label
                    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    label.setAttribute('x', x);
                    label.setAttribute('y', centerY + 16);
                    label.setAttribute('fill', '#999');
                    label.setAttribute('font-size', '9');
                    label.setAttribute('text-anchor', 'middle');
                    label.textContent = year;
                    svg.appendChild(label);
                }}
            }});

            // Draw commit dots and labels
            commits.forEach((c, i) => {{
                const x = hashToPos[c.hash].x;
                const y = hashToPos[c.hash].y;
                const bIdx = branches.indexOf(c.branch);
                const color = BRANCH_COLORS[bIdx % BRANCH_COLORS.length];
                const dateStr = c.date.slice(0, 10);

                const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                g.classList.add('metro-commit');

                // Dot
                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', x);
                circle.setAttribute('cy', y);
                circle.setAttribute('r', c.is_merge ? R + 2 : R);
                circle.setAttribute('fill', c.is_merge ? '#fff' : color);
                circle.setAttribute('stroke', color);
                circle.setAttribute('stroke-width', c.is_merge ? '2.5' : '1.5');
                g.appendChild(circle);

                // Label — above for branches above main, below for branches below
                const above = branchOffset[c.branch] <= 0;
                const msg = c.message.length > 38 ? c.message.slice(0, 35) + '...' : c.message;
                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.classList.add('metro-label');
                const labelY = above ? y - R - 6 : y + R + 12;
                text.setAttribute('x', x);
                text.setAttribute('y', labelY);
                text.setAttribute('fill', '#555');
                text.setAttribute('font-size', '8');
                text.setAttribute('text-anchor', 'start');
                text.setAttribute('transform', `rotate(-50, ${{x}}, ${{labelY}})`);
                text.textContent = msg;
                g.appendChild(text);

                // Branch label on first commit of each non-main branch
                if (c.branch !== 'main') {{
                    const branchCommits = commits.filter(cc => cc.branch === c.branch);
                    if (branchCommits[0].hash === c.hash) {{
                        const blabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                        const bLabelY = above ? y - R - 4 : y + R + 14;
                        blabel.setAttribute('x', x + 8);
                        blabel.setAttribute('y', above ? y + branchOffset[c.branch] * 0.1 - 2 : y + 22);
                        blabel.setAttribute('fill', color);
                        blabel.setAttribute('font-size', '10');
                        blabel.setAttribute('font-weight', 'bold');
                        blabel.textContent = c.branch;
                        g.appendChild(blabel);
                    }}
                }}

                // Tooltip with date
                const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
                title.textContent = `${{dateStr}} · ${{c.hash}} (${{c.branch}})\\n${{c.message}}`;
                g.appendChild(title);

                svg.appendChild(g);
            }});

            container.appendChild(svg);
        }}

        // Story renderer — zoom-out scroll, one keyword per dot
        function renderStory(containerId, graph) {{
            const container = document.getElementById(containerId);
            const idx = containerId.split('-')[1];
            const intro = document.getElementById('story-intro-' + idx);
            const fadeLeft = document.getElementById('story-fade-' + idx);
            const commits = graph.commits;
            const branches = graph.branches;

            const COL_W = 56;
            const OFFSET_Y = 44;
            const PADDING_X = 60;
            const PADDING_TOP = 70;
            const R = 3.5;

            const branchOffset = {{}};
            branchOffset['main'] = 0;
            let slot = 1;
            for (const b of branches) {{
                if (b === 'main') continue;
                const direction = (slot % 2 === 1) ? -1 : 1;
                const level = Math.ceil(slot / 2);
                branchOffset[b] = direction * level * OFFSET_Y;
                slot++;
            }}

            const maxAbove = Math.min(...Object.values(branchOffset));
            const maxBelow = Math.max(...Object.values(branchOffset));
            const centerY = PADDING_TOP + Math.abs(maxAbove);
            const width = commits.length * COL_W + PADDING_X * 2 + 80;
            const height = centerY + maxBelow + PADDING_TOP + 50;

            // Wrap SVG in a div for transform
            const svgWrap = document.createElement('div');
            svgWrap.className = 'story-svg-wrap';

            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('width', width);
            svg.setAttribute('height', height);
            svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
            svg.style.fontFamily = 'Georgia, "Times New Roman", serif';
            svg.style.display = 'block';

            // Faint main spine
            const mainLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            mainLine.setAttribute('x1', PADDING_X);
            mainLine.setAttribute('y1', centerY);
            mainLine.setAttribute('x2', commits.length * COL_W + PADDING_X);
            mainLine.setAttribute('y2', centerY);
            mainLine.setAttribute('stroke', '#ddd');
            mainLine.setAttribute('stroke-width', '0.5');
            svg.appendChild(mainLine);

            // Position each commit
            const hashToPos = {{}};
            commits.forEach((c, i) => {{
                hashToPos[c.hash] = {{
                    x: PADDING_X + i * COL_W,
                    y: centerY + branchOffset[c.branch]
                }};
            }});

            // Branch lines — very subtle
            const branchSegments = {{}};
            commits.forEach((c) => {{
                if (!branchSegments[c.branch]) branchSegments[c.branch] = [];
                branchSegments[c.branch].push(hashToPos[c.hash]);
            }});

            for (const [bname, points] of Object.entries(branchSegments)) {{
                if (points.length < 2) continue;
                const bIdx = branches.indexOf(bname);
                const color = BRANCH_COLORS[bIdx % BRANCH_COLORS.length];
                for (let j = 1; j < points.length; j++) {{
                    const p0 = points[j-1];
                    const p1 = points[j];
                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('x1', p0.x);
                    line.setAttribute('y1', p0.y);
                    line.setAttribute('x2', p1.x);
                    line.setAttribute('y2', p1.y);
                    line.setAttribute('stroke', color);
                    line.setAttribute('stroke-width', '0.8');
                    line.setAttribute('stroke-opacity', bname === 'main' ? '0.35' : '0.2');
                    svg.appendChild(line);
                }}
            }}

            // Fork/merge curves — hairline
            commits.forEach((c) => {{
                const pos = hashToPos[c.hash];
                c.parents.forEach(ph => {{
                    const parentPos = hashToPos[ph];
                    if (!parentPos) return;
                    if (parentPos.y === pos.y) return;
                    const bIdx = branches.indexOf(c.branch);
                    const color = BRANCH_COLORS[bIdx % BRANCH_COLORS.length];
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    const dx = Math.abs(pos.x - parentPos.x) * 0.4;
                    path.setAttribute('d',
                        `M${{parentPos.x}},${{parentPos.y}} C${{parentPos.x + dx}},${{parentPos.y}} ${{pos.x - dx}},${{pos.y}} ${{pos.x}},${{pos.y}}`);
                    path.setAttribute('stroke', color);
                    path.setAttribute('stroke-width', '0.8');
                    path.setAttribute('fill', 'none');
                    path.setAttribute('stroke-opacity', '0.2');
                    svg.appendChild(path);
                }});
            }});

            // Year markers — minimal
            let lastYear = null;
            commits.forEach((c) => {{
                const year = c.date.slice(0, 4);
                if (year !== lastYear) {{
                    lastYear = year;
                    const x = hashToPos[c.hash].x;
                    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    label.setAttribute('x', x);
                    label.setAttribute('y', centerY + 28);
                    label.setAttribute('fill', '#ccc');
                    label.setAttribute('font-size', '8');
                    label.setAttribute('text-anchor', 'middle');
                    label.setAttribute('font-family', '"Courier New", monospace');
                    label.textContent = year;
                    svg.appendChild(label);
                }}
            }});

            // Create popover element (HTML overlay, lives in outer)
            const popover = document.createElement('div');
            popover.className = 'story-popover';
            container.parentElement.appendChild(popover);

            // Dots + keywords
            commits.forEach((c, ci) => {{
                const x = hashToPos[c.hash].x;
                const y = hashToPos[c.hash].y;
                const bIdx = branches.indexOf(c.branch);
                const color = BRANCH_COLORS[bIdx % BRANCH_COLORS.length];

                const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                g.classList.add('story-dot');
                g.style.opacity = '0';

                // Dot
                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', x);
                circle.setAttribute('cy', y);
                circle.setAttribute('r', c.is_merge ? R + 1.5 : R);
                circle.setAttribute('fill', c.is_merge ? '#fff' : color);
                circle.setAttribute('stroke', color);
                circle.setAttribute('stroke-width', c.is_merge ? '1.5' : '0.8');
                g.appendChild(circle);

                // Keyword — italic serif, tilted
                const above = branchOffset[c.branch] < 0;
                const keyword = c.keyword || '?';
                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                const labelY = above ? y - R - 7 : y + R + 13;
                text.setAttribute('x', x);
                text.setAttribute('y', labelY);
                text.setAttribute('fill', '#555');
                text.setAttribute('font-size', '9');
                text.setAttribute('font-style', 'italic');
                text.setAttribute('text-anchor', 'start');
                text.setAttribute('transform', `rotate(-35, ${{x}}, ${{labelY}})`);
                text.textContent = keyword;
                g.appendChild(text);

                // Hit area
                const hitArea = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                hitArea.setAttribute('cx', x);
                hitArea.setAttribute('cy', y);
                hitArea.setAttribute('r', 16);
                hitArea.setAttribute('fill', 'transparent');
                g.appendChild(hitArea);

                // Hover
                g.addEventListener('mouseenter', () => {{
                    const dateStr = c.date.slice(0, 10);
                    popover.innerHTML = `<div class="date">${{dateStr}}</div><div class="msg">${{c.message}}</div><div class="branch-tag">${{c.branch}}</div>`;
                    popover.style.display = 'block';
                    const outerRect = container.parentElement.getBoundingClientRect();
                    const svgRect = svg.getBoundingClientRect();
                    const scaleX = svgRect.width / width;
                    const scaleY = svgRect.height / height;
                    const dotScreenX = svgRect.left + x * scaleX - outerRect.left;
                    const dotScreenY = svgRect.top + y * scaleY - outerRect.top;
                    popover.style.left = Math.max(0, dotScreenX - 60) + 'px';
                    popover.style.top = (dotScreenY - popover.offsetHeight - 14) + 'px';
                }});
                g.addEventListener('mouseleave', () => {{
                    popover.style.display = 'none';
                }});

                svg.appendChild(g);
            }});

            svgWrap.appendChild(svg);
            container.appendChild(svgWrap);

            // --- Scroll-driven animation ---
            let introFaded = false;

            // SVG at normal scale from the start — no zoom
            svgWrap.style.transform = 'scale(1)';

            // Reveal dots progressively based on scroll
            function updateOnScroll() {{
                const scrollX = container.scrollLeft;
                const containerW = container.clientWidth;

                // Fade intro overlay on first scroll
                if (!introFaded && scrollX > 5) {{
                    intro.classList.add('faded');
                    introFaded = true;
                }}

                // Show left fade when scrolled
                if (scrollX > 50) {{
                    fadeLeft.classList.add('visible');
                }} else {{
                    fadeLeft.classList.remove('visible');
                }}

                // Reveal dots as they enter the viewport from the right
                const dots = svg.querySelectorAll('.story-dot');
                dots.forEach((dot, i) => {{
                    const commit = commits[i];
                    const dotSvgX = hashToPos[commit.hash].x;
                    const dotScreenX = dotSvgX - scrollX;
                    const reveal = dotScreenX < containerW - 20;
                    if (reveal && dot.style.opacity === '0') {{
                        const delay = Math.max(0, (dotScreenX / containerW) * 0.25);
                        dot.style.transition = `opacity 0.6s ease-out ${{delay}}s`;
                        dot.style.opacity = '1';
                    }}
                }});
            }}

            container.addEventListener('scroll', updateOnScroll);
            // Initial reveal — show dots already in viewport
            requestAnimationFrame(updateOnScroll);
        }}

        // Render all
        GRAPHS.forEach((g, i) => {{
            renderMetro('metro-' + i, g);
            renderStory('story-' + i, g);
        }});
    </script>
</body>
</html>"""

    return html


if __name__ == "__main__":
    base = Path("generated_repos")

    # Find repos — prefer repos with .branch_meta.json, then most recent
    sonnet_repos = []
    opus_repos = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / ".git").exists():
            has_meta = (d / ".branch_meta.json").exists()
            if "sonnet" in d.name.lower():
                sonnet_repos.append((has_meta, str(d)))
            elif "opus" in d.name.lower():
                opus_repos.append((has_meta, str(d)))
    # Sort by (has_meta, path) so repos with metadata sort last (preferred)
    sonnet_repos.sort()
    opus_repos.sort()

    repos = []
    if sonnet_repos:
        repos.append((sonnet_repos[-1][1], "Sonnet 4.6"))
    if opus_repos:
        repos.append((opus_repos[-1][1], "Opus 4.6"))

    if not repos:
        print("No opus/sonnet repos found in generated_repos/")
        sys.exit(1)

    html = generate_html(repos)
    out_path = Path("visualize.html")
    out_path.write_text(html)
    print(f"Generated {out_path} with {len(repos)} repos")
    print(f"Open in browser: file://{out_path.resolve()}")
