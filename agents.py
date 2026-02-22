#!/usr/bin/env python3
"""
Multi-agent orchestration for journal parsing
Each agent has a focused, specialized task
"""

import asyncio
import json
import re
import time
from typing import List, Dict, Any
import anthropic
from dataclasses import dataclass
from datetime import datetime

# Model configuration
CLAUDE_MODEL = "claude-sonnet-4-6"


@dataclass
class LifeEvent:
    description: str
    raw_date: str = None
    parsed_date: str = None
    commit_message: str = None
    keyword: str = None


class JournalParsingOrchestrator:
    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    async def parse_journal(self, journal_text: str) -> tuple:
        """Orchestrate multi-agent journal parsing pipeline with timing and parallelization"""

        start_time = time.time()
        print(f"🚀 Starting multi-agent journal parsing...")

        # Step 1: Extract events (must be sequential - foundation for others)
        step_start = time.time()
        events = await self.extract_events(journal_text)
        print(f"✅ Event extraction: {len(events)} events in {time.time() - step_start:.2f}s")

        # Step 2: Resolve dates + generate commits in parallel
        step_start = time.time()
        date_task = self.resolve_dates(journal_text, events)
        commit_task = self.generate_commits([LifeEvent(description=e.description) for e in events])

        events, commit_events = await asyncio.gather(date_task, commit_task)

        # Merge commit messages + keywords into dated events
        for i, event in enumerate(events):
            if i < len(commit_events):
                event.commit_message = commit_events[i].commit_message
                event.keyword = commit_events[i].keyword

        print(f"✅ Date resolution + commit generation (parallel): {time.time() - step_start:.2f}s")

        # Step 3: Design branch structure (needs dated timeline)
        step_start = time.time()
        branch_structure = await self.design_branch_structure(events)
        print(f"✅ Branch structure design: {len(branch_structure)} branches in {time.time() - step_start:.2f}s")

        # Step 4: Validate and refine
        step_start = time.time()
        events = await self.validate_output(events)
        print(f"✅ Validation: {time.time() - step_start:.2f}s")

        total_time = time.time() - start_time
        print(f"🎉 Total processing time: {total_time:.2f}s")

        return self.format_for_git_creation(events, branch_structure)

    async def extract_events(self, journal_text: str) -> List[LifeEvent]:
        """Agent 1: Extract significant life events"""

        prompt = """
        Read this journal and identify significant life events - moments that changed or shaped this person's life.

        Return ONLY a simple JSON list of event descriptions, nothing else:
        ["event 1 description", "event 2 description", ...]

        Focus on:
        - Major life changes (jobs, moves, relationships)
        - Personal growth moments
        - Significant experiences or realizations
        - Important milestones

        Journal:
        """ + journal_text

        response = await self._call_claude(prompt)

        try:
            event_descriptions = json.loads(response)
            return [LifeEvent(description=desc) for desc in event_descriptions]
        except Exception as e:
            print(f"Event extraction failed: {e}")  # Debug
            print(f"Response was: {response}")  # Debug
            # Fallback: parse as text and create single event
            return [LifeEvent(description=journal_text[:200] + "...")]

    async def resolve_dates(self, original_text: str, events: List[LifeEvent]) -> List[LifeEvent]:
        """Agent 2: Resolve dates for each event"""

        events_json = [event.description for event in events]

        prompt = """
        For each life event below, extract or infer the exact date when it happened using the original journal text.

        IMPORTANT: The journal contains specific dates and years - extract them precisely!
        Look for patterns like:
        - "1999/7/12" -> 1999-07-12
        - "in 2013" -> 2013-01-01 (estimate month/day)
        - "January of 2021" -> 2021-01-01
        - "spring 2022" -> 2022-04-01
        - "fall 2023" -> 2023-09-01

        Return JSON in this exact format:
        [
            {"event": "event description", "date": "YYYY-MM-DD"}
        ]

        Guidelines:
        - Extract exact dates from journal when available
        - For "when I was X years old", calculate from birth year 1999
        - Use specific years mentioned in the journal
        - Only use current date as absolute last resort

        Original journal (contains many specific dates):
        """ + original_text + """

        Events to date:
        """ + json.dumps(events_json)

        response = await self._call_claude(prompt, max_tokens=5000)  # More tokens for date resolution

        try:
            # Save full response to log
            with open("logs/date_resolution.log", "w") as f:
                f.write(f"Date Resolution Response:\n{response}\n")

            dated_events = json.loads(response)
            print(f"✅ Parsed {len(dated_events)} dated events")
            for i, event in enumerate(events):
                if i < len(dated_events):
                    event.parsed_date = dated_events[i].get('date')
        except Exception as e:
            print(f"❌ Date resolution error: {e}")
            with open("logs/date_error.log", "w") as f:
                f.write(f"Error: {e}\nResponse: {response}\n")
            # Fallback: assign current date
            current_date = datetime.now().strftime("%Y-%m-%d")
            for event in events:
                event.parsed_date = current_date

        return events

    async def generate_commits(self, events: List[LifeEvent]) -> List[LifeEvent]:
        """Agent 3: Generate git commit messages"""

        events_data = [{"desc": e.description, "date": e.parsed_date} for e in events]

        prompt = """
        Convert these life events into git commit messages.

        Follow git conventions:
        - Present tense, imperative mood
        - Concise but meaningful
        - Start with action verb when possible
        - Use plain, human language — NOT developer jargon
          BAD:  "Provision first solo environment; remove all shared dependencies"
          GOOD: "Move into first apartment alone"
          BAD:  "Force disconnect from China pipeline; suspend cultural sync"
          GOOD: "Lose ability to visit China due to COVID"

        For each event also provide a "keyword": 2-3 evocative words that capture the
        emotional essence of the moment. This is for a minimal visualization where each
        life event is represented by just these few words.
        Examples: "Shanghai", "first love", "father lost", "PhD quit", "Brooklyn art",
                  "San Francisco", "citizenship", "solo travel", "grief"

        Return JSON:
        [
            {"event": "original description", "commit": "git commit message", "keyword": "2-3 word label"},
            ...
        ]

        Events:
        """ + json.dumps(events_data)

        response = await self._call_claude(prompt)

        try:
            commit_data = json.loads(response)
            for i, event in enumerate(events):
                if i < len(commit_data):
                    event.commit_message = commit_data[i].get('commit', event.description)
                    event.keyword = commit_data[i].get('keyword', '')
        except:
            # Fallback: use description as commit
            for event in events:
                event.commit_message = event.description

        return events

    async def design_branch_structure(self, events: List[LifeEvent]) -> List[Dict]:
        """Agent 4: Design narrative branch structure over the full timeline"""

        events_data = [
            {"index": i, "description": e.description, "date": e.parsed_date}
            for i, e in enumerate(events)
        ]

        prompt = """
        You are designing the git branch structure for a person's life story.

        The MAIN branch is the continuous thread of life — most events belong here.
        BRANCHES represent parallel life threads (education, a relationship, travel, a career arc)
        that run alongside main for a while.

        Branch merging rules:
        - Most branches merge back to main when the chapter DEFINITIVELY closes:
          a death, a graduation, a breakup, leaving a program — these close branches.
        - Some threads are ONGOING and never close. An art practice, a spiritual path,
          a lifelong friendship — these stay open. Set "merges": false for these.
        - For branches that merge, the merge_message describes the closure.

        Rules:
        - Target 3-6 branches maximum
        - Each branch must span at least 2 events
        - Every event index can appear on at most one branch (or stay on main)
        - Events NOT listed in any branch stay on main
        - Branch names should be short, kebab-case, narrative labels (e.g. "education", "first-love", "career-pivot", "travel-year")
        - opens_at_event is the index of the first event on that branch
        - events_on_branch must be sorted and the first element must equal opens_at_event

        Temporal guidance (important for readable graphs):
        - Branches should represent focused chapters, not span the entire timeline
        - Prefer branches occupying distinct time periods (1-4 years each)
        - Minimize temporal overlap between branches — heavily overlapping branches create tangled, unreadable graphs
        - For branches that merge, the last event should be the narrative closing moment

        Return ONLY JSON in this exact format:
        {
          "branches": [
            {
              "name": "education",
              "opens_at_event": 3,
              "merges": true,
              "merge_message": "Graduate and enter the workforce",
              "events_on_branch": [3, 5, 8, 12]
            },
            {
              "name": "art-practice",
              "opens_at_event": 7,
              "merges": false,
              "merge_message": "",
              "events_on_branch": [7, 15, 22]
            }
          ]
        }

        Events (with indices and dates):
        """ + json.dumps(events_data, indent=2)

        response = await self._call_claude(prompt, max_tokens=3000)

        try:
            result = json.loads(response)
            branches = result.get("branches", [])

            # Validate: no event assigned to multiple branches
            seen_events = set()
            valid_branches = []
            for branch in branches:
                event_indices = branch.get("events_on_branch", [])
                if len(event_indices) < 2:
                    continue
                if any(idx in seen_events for idx in event_indices):
                    continue
                if not all(0 <= idx < len(events) for idx in event_indices):
                    continue
                seen_events.update(event_indices)
                valid_branches.append(branch)

            return valid_branches
        except Exception as e:
            print(f"Branch structure design failed: {e}")
            return []

    async def validate_output(self, events: List[LifeEvent]) -> List[LifeEvent]:
        """Agent 5: Validate and suggest improvements"""

        # For now, just ensure we have minimum required data
        filtered_events = []
        for event in events:
            if event.commit_message and event.parsed_date:
                filtered_events.append(event)

        return filtered_events or events  # Return original if filtering removes everything

    def format_for_git_creation(self, events: List[LifeEvent], branch_structure: List[Dict]) -> tuple:
        """Convert to format expected by git creation function.
        Returns (events_list, branch_structure)."""
        formatted_events = [
            {
                "commit_message": event.commit_message,
                "date": event.parsed_date,
                "description": event.description,
                "keyword": event.keyword or "",
            }
            for event in events
        ]
        return formatted_events, branch_structure

    async def _call_claude(self, prompt: str, max_tokens: int = 2000) -> str:
        """Make API call to Claude"""
        try:
            response = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = response.content[0].text

            # Strip markdown code blocks if present (handle all variants)
            response_text = response_text.strip()
            # Match ```json or ``` at start, and ``` at end
            response_text = re.sub(r'^```(?:json)?\s*\n?', '', response_text)
            response_text = re.sub(r'\n?```\s*$', '', response_text)
            response_text = response_text.strip()

            return response_text
        except Exception as e:
            print(f"Claude API error: {e}")
            return "{}"  # Return empty JSON on error


# Async wrapper for use in Flask
def parse_journal_with_agents(client: anthropic.Anthropic, journal_text: str) -> tuple:
    """Synchronous wrapper for Flask app. Returns (events, branch_structure)."""
    orchestrator = JournalParsingOrchestrator(client)

    # Run async function in event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(orchestrator.parse_journal(journal_text))