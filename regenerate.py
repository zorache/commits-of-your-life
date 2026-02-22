#!/usr/bin/env python3
"""Regenerate repos with both Sonnet and Opus, then rebuild visualize.html."""

import os, sys, importlib
from dotenv import load_dotenv
import anthropic

load_dotenv()

# Journal text (same as test_journal.py)
from test_journal import journal_text
from app import create_life_repo

client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

MODELS = [
    ("claude-sonnet-4-6", "Life (Sonnet)"),
    ("claude-opus-4-6",   "Life (Opus)"),
]

for model_id, label in MODELS:
    print(f"\n{'='*60}")
    print(f"Generating with {model_id}...")
    print(f"{'='*60}")

    # Patch the model used by agents
    import agents
    agents.CLAUDE_MODEL = model_id
    # Re-import to pick up model change
    importlib.reload(agents)
    from agents import parse_journal_with_agents

    events, branch_structure = parse_journal_with_agents(client, journal_text)

    print(f"\n{len(events)} events, {len(branch_structure)} branches")
    for e in events:
        kw = e.get('keyword', '')
        print(f"  [{kw:15s}] {e['commit_message']}")

    for b in branch_structure:
        merges = b.get('merges', True)
        print(f"  branch: {b['name']}  merges={merges}  events={b['events_on_branch']}")

    repo_path = create_life_repo(events, branch_structure, label)
    print(f"Repo created: {repo_path}")

# Now regenerate visualization
print(f"\n{'='*60}")
print("Regenerating visualize.html...")
print(f"{'='*60}")
os.system(f"{sys.executable} visualize.py")
