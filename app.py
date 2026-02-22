#!/usr/bin/env python3
"""
Commits of Your Life - MVP Backend
Processes journal entries and converts them to git repositories
"""

import os
import json
import hashlib
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_file
from dotenv import load_dotenv
import anthropic
from git import Repo
from dateutil import parser as date_parser
import zipfile
from agents import parse_journal_with_agents, CLAUDE_MODEL
from visualize import extract_graph_data

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize Anthropic client
client = anthropic.Anthropic(
    api_key=os.getenv('ANTHROPIC_API_KEY')
)

# ---------------------------------------------------------------------------
# Response caching — avoid re-running ~50s agent pipeline on repeated inputs
# ---------------------------------------------------------------------------

CACHE_DIR = Path("generated_repos/.cache")

def _cache_key(journal_text: str, user_name: str) -> str:
    raw = f"{user_name}::{journal_text}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _load_cache(key: str):
    """Return cached response dict if cache hit and repo+zip still exist."""
    cache_file = CACHE_DIR / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
        repo_path = Path(data.get("repo_path", ""))
        repo_name = data.get("repo_name", "")
        zip_path = Path("generated_repos") / f"{repo_name}.zip"
        if repo_path.exists() and zip_path.exists():
            return data
    except Exception:
        pass
    return None

def _save_cache(key: str, data: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(data))


def parse_journal_with_ai(journal_text):
    """Use Claude to parse journal text into structured life events with dates"""

    prompt = f"""
    Please analyze this journal entry and extract life events that could be represented as git commits.
    For each event, provide:
    1. A commit message (concise, meaningful)
    2. A date (infer from context, use format YYYY-MM-DD)
    3. A brief description
    4. Whether this represents a major life change (branch worthy)

    Return as JSON in this format:
    {{
        "events": [
            {{
                "commit_message": "Started new job at tech company",
                "date": "2024-01-15",
                "description": "Brief description of the change",
                "is_major_change": false
            }}
        ]
    }}

    Journal text:
    {journal_text}
    """

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        # Parse the response
        response_text = response.content[0].text

        # Find JSON in response (Claude might add explanation before/after)
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        json_text = response_text[start:end]

        return json.loads(json_text)

    except Exception as e:
        print(f"AI parsing error: {e}")
        # Fallback: create simple event from entire text
        return {
            "events": [{
                "commit_message": "Life update",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "description": journal_text[:100] + "..." if len(journal_text) > 100 else journal_text,
                "is_major_change": False
            }]
        }

def create_life_repo(events, branch_structure=None, user_name="Life Author"):
    """Create a git repository representing life events with narrative branches that merge back."""

    if branch_structure is None:
        branch_structure = []

    # Create persistent directory for the repo
    output_dir = Path("generated_repos")
    output_dir.mkdir(exist_ok=True)

    # Create unique repo name with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = user_name.replace(" ", "_").lower()
    repo_name = f"{safe_name}_life_{timestamp}"
    repo_path = output_dir / repo_name

    try:
        # Create directory and initialize git repo
        repo_path.mkdir(parents=True, exist_ok=True)
        repo = Repo.init(str(repo_path))

        # Configure git user
        repo.config_writer().set_value("user", "name", user_name).release()
        repo.config_writer().set_value("user", "email", "life@commits.local").release()

        # Sort events by date, preserving original indices
        indexed_events = [(i, e) for i, e in enumerate(events)]
        if not indexed_events:
            raise ValueError("No events to create repository from")
        indexed_events.sort(key=lambda x: date_parser.parse(x[1]['date']))

        # Build lookup: original_index -> branch info
        event_to_branch = {}  # original_index -> branch dict
        for branch in branch_structure:
            for idx in branch.get("events_on_branch", []):
                event_to_branch[idx] = branch

        # Track which branches have been created and which events remain on each
        created_branches = set()
        branch_remaining = {}  # branch_name -> set of remaining event indices
        for branch in branch_structure:
            branch_remaining[branch["name"]] = set(branch.get("events_on_branch", []))

        # Branch metadata: track which commit belongs to which branch
        branch_map = {}      # commit SHA -> branch name
        merge_commits = {}   # merge commit SHA -> merged branch name
        keyword_map = {}     # commit SHA -> keyword (for story visualization)
        branch_order = ["main"]

        # Need an initial commit on main before we can create branches
        readme = repo_path / "README.md"
        with open(readme, 'w') as f:
            f.write("# Life Story\n\nA git repository of life events.\n")
        repo.index.add(["README.md"])
        # Use the earliest event date for the initial commit
        first_date = date_parser.parse(indexed_events[0][1]['date'])
        if first_date.tzinfo is None:
            first_date = first_date.replace(tzinfo=timezone.utc)
        init_commit = repo.index.commit("Initialize life story", author_date=first_date, commit_date=first_date)
        branch_map[init_commit.hexsha] = "main"

        file_counter = 0
        for orig_idx, event in indexed_events:
            file_counter += 1
            branch_info = event_to_branch.get(orig_idx)

            commit_date = date_parser.parse(event['date'])
            if commit_date.tzinfo is None:
                commit_date = commit_date.replace(tzinfo=timezone.utc)

            if branch_info:
                branch_name = branch_info["name"]

                # Create branch if it doesn't exist yet
                if branch_name not in created_branches:
                    repo.git.checkout("main")
                    repo.git.checkout("-b", branch_name)
                    created_branches.add(branch_name)
                    if branch_name not in branch_order:
                        branch_order.append(branch_name)
                else:
                    repo.git.checkout(branch_name)

                # Write and commit the event file
                event_file = repo_path / f"event_{file_counter:03d}.md"
                with open(event_file, 'w') as f:
                    f.write(f"# {event['commit_message']}\n\n")
                    f.write(f"Date: {event['date']}\n\n")
                    f.write(f"{event['description']}\n")
                repo.index.add([str(event_file.relative_to(repo_path))])
                c = repo.index.commit(
                    event['commit_message'],
                    author_date=commit_date,
                    commit_date=commit_date
                )
                branch_map[c.hexsha] = branch_name
                if event.get('keyword'):
                    keyword_map[c.hexsha] = event['keyword']

                # Track remaining events on this branch
                branch_remaining[branch_name].discard(orig_idx)

                # If no events remain on this branch, merge back to main
                # (unless the branch is marked as non-merging)
                should_merge = branch_info.get("merges", True)
                if not branch_remaining[branch_name] and should_merge:
                    repo.git.checkout("main")
                    merge_msg = branch_info.get("merge_message", f"Merge branch '{branch_name}'")
                    date_str = commit_date.isoformat()
                    repo.git.merge(
                        branch_name, "--no-ff", m=merge_msg,
                        env={"GIT_AUTHOR_DATE": date_str, "GIT_COMMITTER_DATE": date_str}
                    )
                    merge_sha = repo.head.commit.hexsha
                    branch_map[merge_sha] = "main"
                    merge_commits[merge_sha] = branch_name
            else:
                # Event stays on main
                repo.git.checkout("main")

                event_file = repo_path / f"event_{file_counter:03d}.md"
                with open(event_file, 'w') as f:
                    f.write(f"# {event['commit_message']}\n\n")
                    f.write(f"Date: {event['date']}\n\n")
                    f.write(f"{event['description']}\n")
                repo.index.add([str(event_file.relative_to(repo_path))])
                c = repo.index.commit(
                    event['commit_message'],
                    author_date=commit_date,
                    commit_date=commit_date
                )
                branch_map[c.hexsha] = "main"
                if event.get('keyword'):
                    keyword_map[c.hexsha] = event['keyword']

        # Ensure we end on main
        repo.git.checkout("main")

        # Write branch metadata for visualization
        meta = {
            "branch_map": {sha: name for sha, name in branch_map.items()},
            "branch_order": branch_order,
            "merge_commits": {sha: name for sha, name in merge_commits.items()},
            "keyword_map": keyword_map,
        }
        with open(repo_path / ".branch_meta.json", "w") as f:
            json.dump(meta, f, indent=2)

        return str(repo_path)

    except Exception as e:
        print(f"Git repo creation error: {e}")
        # Clean up on error
        if repo_path.exists():
            shutil.rmtree(repo_path, ignore_errors=True)
        raise

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/process', methods=['POST'])
def process_journal():
    """Process journal text and create life repo"""
    try:
        data = request.get_json()
        journal_text = data.get('journal_text', '')
        user_name = data.get('user_name', 'Life Author')

        if not journal_text.strip():
            return jsonify({'error': 'Journal text is required'}), 400

        # Check cache first
        ckey = _cache_key(journal_text, user_name)
        cached = _load_cache(ckey)
        if cached:
            return jsonify(cached)

        # Parse journal with multi-agent system
        events, branch_structure = parse_journal_with_agents(client, journal_text)

        if not events:
            return jsonify({'error': 'No life events could be extracted'}), 400

        # Create git repository
        repo_path = create_life_repo(events, branch_structure, user_name)

        # Get git log for visualization (all branches)
        repo = Repo(repo_path)
        commits = []

        for commit in repo.iter_commits("--all"):
            commits.append({
                'hash': commit.hexsha[:8],
                'message': commit.message.strip(),
                'date': commit.committed_datetime.isoformat(),
                'author': str(commit.author)
            })

        # Extract graph data for Story visualization
        graph_data = extract_graph_data(repo_path)

        # Create zip file for download
        zip_path = create_repo_zip(repo_path)
        repo_name = Path(repo_path).name

        result = {
            'success': True,
            'events': events,
            'branches': branch_structure,
            'commits': commits,
            'graph': graph_data,
            'repo_path': repo_path,
            'repo_name': repo_name,
            'download_url': f'/api/download/{repo_name}'
        }

        _save_cache(ckey, result)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def create_repo_zip(repo_path):
    """Create a zip file of the git repository"""
    repo_path = Path(repo_path)
    zip_path = repo_path.parent / f"{repo_path.name}.zip"

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in repo_path.rglob('*'):
            if file_path.is_file():
                # Add file to zip with relative path
                arcname = file_path.relative_to(repo_path)
                zipf.write(file_path, arcname)

    return zip_path

@app.route('/api/download/<repo_name>')
def download_repo(repo_name):
    """Download git repository as zip file"""
    try:
        zip_path = Path("generated_repos") / f"{repo_name}.zip"
        if not zip_path.exists():
            return jsonify({'error': 'Repository not found'}), 404

        return send_file(
            zip_path,
            as_attachment=True,
            download_name=f"{repo_name}.zip",
            mimetype='application/zip'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------------------------------------------------------------------
# Commit embedding + semantic search
# ---------------------------------------------------------------------------

_commits_collection = None

def _get_commits_collection():
    global _commits_collection
    if _commits_collection is None:
        import chromadb
        from discover import _get_embed_fn
        db_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
        chroma_client = chromadb.PersistentClient(path=db_path)
        _commits_collection = chroma_client.get_or_create_collection(
            name="life_commits", embedding_function=_get_embed_fn()
        )
    return _commits_collection

@app.route('/api/embed-commits', methods=['POST'])
def embed_commits():
    """Embed commit events into ChromaDB for semantic search."""
    try:
        data = request.get_json()
        repo_name = data.get('repo_name', '')
        events = data.get('events', [])

        if not repo_name or not events:
            return jsonify({'error': 'repo_name and events required'}), 400

        collection = _get_commits_collection()

        ids = []
        docs = []
        metas = []
        for i, event in enumerate(events):
            msg = event.get('commit_message', '')
            desc = event.get('description', '')
            ids.append(f"{repo_name}::{i}")
            docs.append(f"{msg} — {desc}")
            metas.append({
                'repo_name': repo_name,
                'date': event.get('date', ''),
                'commit_message': msg,
                'keyword': event.get('keyword', ''),
            })

        collection.upsert(ids=ids, documents=docs, metadatas=metas)
        return jsonify({'success': True, 'count': len(ids)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search-commits', methods=['POST'])
def search_commits():
    """Semantic search over embedded commits."""
    try:
        data = request.get_json()
        query = data.get('query', '')
        repo_name = data.get('repo_name', '')

        if not query.strip() or not repo_name:
            return jsonify({'error': 'query and repo_name required'}), 400

        collection = _get_commits_collection()
        results = collection.query(
            query_texts=[query],
            n_results=10,
            where={"repo_name": repo_name},
        )

        matches = []
        for i in range(len(results['ids'][0])):
            meta = results['metadatas'][0][i]
            matches.append({
                'commit_message': meta.get('commit_message', ''),
                'date': meta.get('date', ''),
                'keyword': meta.get('keyword', ''),
                'distance': results['distances'][0][i] if results.get('distances') else None,
            })

        return jsonify({'matches': matches})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

HAIKU_MODEL = "claude-haiku-4-5-20251001"


@app.route('/api/reflect', methods=['POST'])
def reflect():
    """Generate a reflective question based on the user's life events."""
    try:
        data = request.get_json()
        events = data.get('events', [])

        if not events:
            return jsonify({'error': 'No events provided'}), 400

        timeline = "\n".join(
            f"- {e.get('date', '?')}: {e.get('commit_message', '')} — {e.get('description', '')}"
            for e in events
        )

        prompt = f"""Here is a timeline of someone's life events:

{timeline}

Ask ONE short, curious question about this person's life. Reference specific events from their timeline. Keep it simple — one sentence, like something you'd actually ask someone over coffee.

Bad: "What was it like to navigate the tension between your creative aspirations and professional obligations during that transitional period?" (too much)
Good: "Did you know you were going to leave when you started painting again?"
Good: "What was in Berlin?"
Good: "Were you looking for something in 2019 or running from something?"

Return ONLY the question, nothing else."""

        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        question = response.content[0].text.strip()
        return jsonify({'question': question})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _filter_with_haiku(candidates, query, commit_date):
    """Use Haiku to filter candidates for relevance, time-period fit, and non-fiction."""
    numbered = "\n".join(
        f"[{i}] ({c['date']}) {c['file']}: {c['text'][:300]}"
        for i, c in enumerate(candidates)
    )
    prompt = f"""You are filtering personal notes for relevance to a life event.

Life event: "{query}"
Event date: {commit_date}

Here are candidate note fragments:

{numbered}

For each fragment, decide: is it (a) real personal writing (not fiction, not a quote from a book/article), (b) plausibly from the same time period as the event, and (c) meaningfully related to the life event — not just surface keyword overlap?

Return ONLY a JSON array of the indices that pass all three checks. Example: [0, 2, 5]
If none pass, return [].
"""
    try:
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Extract first JSON array from response
        import re
        m = re.search(r'\[[\d,\s]*\]', text)
        if m:
            keep = json.loads(m.group())
            filtered = [candidates[i] for i in keep if isinstance(i, int) and 0 <= i < len(candidates)]
            return filtered if filtered else candidates[:4]
        return candidates[:4]
    except Exception as e:
        print(f"Haiku filter error: {e}")
        return candidates[:8]


def _days_between(date_a, date_b):
    """Absolute day difference between two YYYY-MM-DD strings. Returns None on parse failure."""
    try:
        from datetime import date
        da = date.fromisoformat(date_a[:10])
        db = date.fromisoformat(date_b[:10])
        return abs((da - db).days)
    except Exception:
        return None


@app.route('/api/search-vault', methods=['POST'])
def search_vault():
    """Search the real notes vault: date-first (±1mo), then semantic ranking, optional Haiku."""
    try:
        data = request.get_json()
        query = data.get('query', '')
        commit_date = data.get('date', '')       # YYYY-MM-DD
        use_haiku = data.get('use_haiku', False)  # toggle from frontend

        if not query.strip():
            return jsonify({'error': 'query required'}), 400

        from discover import _get_collection
        collection = _get_collection()

        # Fetch a large semantic pool
        results = collection.query(query_texts=[query], n_results=200)

        # Bucket by date proximity: ±1 month, then ±3 months fallback
        bucket_tight = []   # within ±30 days
        bucket_wide = []    # within ±90 days
        bucket_rest = []    # everything else

        for i in range(len(results['ids'][0])):
            meta = results['metadatas'][0][i]
            text = results['documents'][0][i]
            note_date = meta.get('date', '')
            distance = results['distances'][0][i] if results.get('distances') else 999

            entry = {
                'text': text,
                'file': meta.get('file_name', ''),
                'date': note_date,
                'distance': distance,
            }

            if commit_date and note_date:
                gap = _days_between(commit_date, note_date)
                if gap is not None:
                    if gap <= 30:
                        bucket_tight.append(entry)
                    elif gap <= 90:
                        bucket_wide.append(entry)
                    else:
                        bucket_rest.append(entry)
                    continue

            bucket_rest.append(entry)

        # Sort each bucket by semantic distance (lower = more related)
        for b in (bucket_tight, bucket_wide, bucket_rest):
            b.sort(key=lambda c: c['distance'])

        # Prefer tight window; widen only to ±90 days — never use undated noise
        if len(bucket_tight) >= 3:
            candidates = bucket_tight
        else:
            candidates = bucket_tight + bucket_wide

        top = candidates[:20]

        # Optional Haiku filter
        if use_haiku and top:
            top = _filter_with_haiku(top, query, commit_date)

        notes = top[:8]
        return jsonify({'notes': notes})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------------------------------------------------------------------
# Discovery pipeline routes
# ---------------------------------------------------------------------------

@app.route('/discover')
def discover():
    """Serve the discovery page"""
    return render_template('discover.html')

@app.route('/api/probe', methods=['POST'])
def probe():
    """Probe the vault and return echoes + candidate events"""
    try:
        from discover import get_prober
        data = request.get_json()
        query = data.get('query', '')
        if not query.strip():
            return jsonify({'error': 'Query is required'}), 400

        prober = get_prober()
        result = prober.probe(query)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/discover-generate', methods=['POST'])
def discover_generate():
    """Generate a git repo from discovery-accumulated events"""
    try:
        data = request.get_json()
        events = data.get('events', [])
        user_name = data.get('user_name', 'Life Author')

        if not events:
            return jsonify({'error': 'No events provided'}), 400

        repo_path = create_life_repo(events, branch_structure=[], user_name=user_name)

        repo = Repo(repo_path)
        commits = []
        for commit in repo.iter_commits("--all"):
            commits.append({
                'hash': commit.hexsha[:8],
                'message': commit.message.strip(),
                'date': commit.committed_datetime.isoformat(),
                'author': str(commit.author)
            })

        zip_path = create_repo_zip(repo_path)
        repo_name = Path(repo_path).name

        return jsonify({
            'success': True,
            'events': events,
            'commits': commits,
            'repo_path': repo_path,
            'repo_name': repo_name,
            'download_url': f'/api/download/{repo_name}'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)