#!/usr/bin/env python3
"""
Multi-agent orchestration for journal parsing
Each agent has a focused, specialized task
"""

import asyncio
import json
from typing import List, Dict, Any
import anthropic
from dataclasses import dataclass
from datetime import datetime


@dataclass
class LifeEvent:
    description: str
    raw_date: str = None
    parsed_date: str = None
    commit_message: str = None
    is_major_change: bool = False


class JournalParsingOrchestrator:
    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    async def parse_journal(self, journal_text: str) -> List[Dict]:
        """Orchestrate multi-agent journal parsing pipeline"""

        # Step 1: Extract events
        events = await self.extract_events(journal_text)

        # Step 2: Resolve dates
        events = await self.resolve_dates(journal_text, events)

        # Step 3: Generate commit messages
        events = await self.generate_commits(events)

        # Step 4: Classify major changes
        events = await self.classify_branches(events)

        # Step 5: Validate and refine
        events = await self.validate_output(events)

        return self.format_for_git_creation(events)

    async def extract_events(self, journal_text: str) -> List[LifeEvent]:
        """Agent 1: Extract significant life events"""

        prompt = f"""
        Read this journal and identify significant life events - moments that changed or shaped this person's life.

        Return ONLY a simple JSON list of event descriptions, nothing else:
        ["event 1 description", "event 2 description", ...]

        Focus on:
        - Major life changes (jobs, moves, relationships)
        - Personal growth moments
        - Significant experiences or realizations
        - Important milestones

        Journal:
        {journal_text}
        """

        response = await self._call_claude(prompt)

        try:
            event_descriptions = json.loads(response)
            return [LifeEvent(description=desc) for desc in event_descriptions]
        except:
            # Fallback: parse as text and create single event
            return [LifeEvent(description=journal_text[:200] + "...")]

    async def resolve_dates(self, original_text: str, events: List[LifeEvent]) -> List[LifeEvent]:
        """Agent 2: Resolve dates for each event"""

        events_json = [event.description for event in events]

        prompt = f"""
        For each life event below, infer the most likely date when it happened.
        Use context from the original journal to help with date inference.

        Return JSON in this exact format:
        [
            {"event": "event description", "date": "YYYY-MM-DD"},
            ...
        ]

        Guidelines:
        - Use YYYY-MM-DD format
        - If unsure, make educated guess based on context
        - For relative dates like "last summer", infer based on when journal was written
        - Use 2023-01-01 as default if completely unclear

        Original journal:
        {original_text}

        Events to date:
        {json.dumps(events_json)}
        """

        response = await self._call_claude(prompt)

        try:
            dated_events = json.loads(response)
            for i, event in enumerate(events):
                if i < len(dated_events):
                    event.parsed_date = dated_events[i].get('date')
        except:
            # Fallback: assign current date
            current_date = datetime.now().strftime("%Y-%m-%d")
            for event in events:
                event.parsed_date = current_date

        return events

    async def generate_commits(self, events: List[LifeEvent]) -> List[LifeEvent]:
        """Agent 3: Generate git commit messages"""

        events_data = [{"desc": e.description, "date": e.parsed_date} for e in events]

        prompt = f"""
        Convert these life events into git commit messages.

        Follow git conventions:
        - Present tense, imperative mood
        - Concise but meaningful
        - Start with action verb when possible

        Examples:
        - "Start new job at tech startup"
        - "Move to San Francisco"
        - "Learn to surf"
        - "End relationship with Sarah"
        - "Graduate from university"

        Return JSON:
        [
            {"event": "original description", "commit": "git commit message"},
            ...
        ]

        Events:
        {json.dumps(events_data)}
        """

        response = await self._call_claude(prompt)

        try:
            commit_data = json.loads(response)
            for i, event in enumerate(events):
                if i < len(commit_data):
                    event.commit_message = commit_data[i].get('commit', event.description)
        except:
            # Fallback: use description as commit
            for event in events:
                event.commit_message = event.description

        return events

    async def classify_branches(self, events: List[LifeEvent]) -> List[LifeEvent]:
        """Agent 4: Identify major life changes for branching"""

        events_data = [{"commit": e.commit_message, "date": e.parsed_date} for e in events]

        prompt = f"""
        Which of these life events represent major life changes that would warrant creating a new git branch?

        Major life changes typically include:
        - Career changes (new job, school, major promotion)
        - Location changes (moves to new cities/countries)
        - Relationship changes (marriage, divorce, major relationships)
        - Life stage transitions (graduation, parenthood, retirement)

        Return JSON list of indices (0-based) that should be branches:
        [0, 3, 7]  // meaning events 0, 3, and 7 are major changes

        Events:
        {json.dumps(events_data, indent=2)}
        """

        response = await self._call_claude(prompt)

        try:
            branch_indices = json.loads(response)
            for i in branch_indices:
                if 0 <= i < len(events):
                    events[i].is_major_change = True
        except:
            # Fallback: no branches
            pass

        return events

    async def validate_output(self, events: List[LifeEvent]) -> List[LifeEvent]:
        """Agent 5: Validate and suggest improvements"""

        # For now, just ensure we have minimum required data
        filtered_events = []
        for event in events:
            if event.commit_message and event.parsed_date:
                filtered_events.append(event)

        return filtered_events or events  # Return original if filtering removes everything

    def format_for_git_creation(self, events: List[LifeEvent]) -> List[Dict]:
        """Convert to format expected by git creation function"""
        return [
            {
                "commit_message": event.commit_message,
                "date": event.parsed_date,
                "description": event.description,
                "is_major_change": event.is_major_change
            }
            for event in events
        ]

    async def _call_claude(self, prompt: str) -> str:
        """Make API call to Claude"""
        try:
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            print(f"Claude API error: {e}")
            return "{}"  # Return empty JSON on error


# Async wrapper for use in Flask
def parse_journal_with_agents(client: anthropic.Anthropic, journal_text: str) -> List[Dict]:
    """Synchronous wrapper for Flask app"""
    orchestrator = JournalParsingOrchestrator(client)

    # Run async function in event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(orchestrator.parse_journal(journal_text))