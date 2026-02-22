#!/usr/bin/env python3
"""
Commits of Your Life - MVP Backend
Processes journal entries and converts them to git repositories
"""

import os
import json
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

        return jsonify({
            'success': True,
            'events': events,
            'branches': branch_structure,
            'commits': commits,
            'graph': graph_data,
            'repo_path': repo_path,
            'repo_name': repo_name,
            'download_url': f'/api/download/{repo_name}'
        })

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