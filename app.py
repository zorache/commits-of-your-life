#!/usr/bin/env python3
"""
Commits of Your Life - MVP Backend
Processes journal entries and converts them to git repositories
"""

import os
import json
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_file
from dotenv import load_dotenv
import anthropic
from git import Repo
from dateutil import parser as date_parser
import zipfile
from agents import parse_journal_with_agents

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
            model="claude-3-sonnet-20240229",
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

def create_life_repo(events, user_name="Life Author"):
    """Create a git repository representing life events"""

    # Create persistent directory for the repo
    output_dir = Path("generated_repos")
    output_dir.mkdir(exist_ok=True)

    # Create unique repo name with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = user_name.replace(" ", "_").lower()
    repo_name = f"{safe_name}_life_{timestamp}"
    repo_path = output_dir / repo_name

    try:
        # Initialize git repo
        repo = Repo.init(repo_path)

        # Configure git user
        repo.config_writer().set_value("user", "name", user_name).release()
        repo.config_writer().set_value("user", "email", "life@commits.local").release()

        # Sort events by date
        sorted_events = sorted(events, key=lambda x: date_parser.parse(x['date']))

        current_branch = "main"

        for i, event in enumerate(sorted_events):
            # Create/switch branch for major life changes
            if event.get('is_major_change') and i > 0:
                branch_name = f"life_chapter_{i+1}"
                repo.git.checkout('-b', branch_name)
                current_branch = branch_name

            # Create a file for this life event
            event_file = repo_path / f"event_{i+1:03d}.md"
            with open(event_file, 'w') as f:
                f.write(f"# {event['commit_message']}\n\n")
                f.write(f"Date: {event['date']}\n\n")
                f.write(f"{event['description']}\n")

            # Add and commit
            repo.index.add([str(event_file)])

            # Create commit with specific date
            commit_date = date_parser.parse(event['date'])

            repo.index.commit(
                event['commit_message'],
                author_date=commit_date,
                commit_date=commit_date
            )

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
        events = parse_journal_with_agents(client, journal_text)

        if not events:
            return jsonify({'error': 'No life events could be extracted'}), 400

        # Create git repository
        repo_path = create_life_repo(events, user_name)

        # Get git log for visualization
        repo = Repo(repo_path)
        commits = []

        for commit in repo.iter_commits():
            commits.append({
                'hash': commit.hexsha[:8],
                'message': commit.message.strip(),
                'date': commit.committed_datetime.isoformat(),
                'author': str(commit.author)
            })

        # Create zip file for download
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)