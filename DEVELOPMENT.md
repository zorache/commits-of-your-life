# Development Notes - Commits of Your Life

## Project Overview
Hackathon art project that transforms personal journal entries into downloadable git repositories, representing life as version-controlled commits and branches.

## Core Functionalities Status

### ✅ **Journal Input Interface**
- Are.na-inspired minimal design
- Responsive form with poetic placeholder text
- Clean typography and spacing
- **Status**: Working well

### ❓ **AI Journal Parsing** (Critical Path)
- Anthropic Claude API extracts life events with dates
- Structured JSON output with commit messages
- Handles date inference and major life changes
- **Status**: Implemented but needs real-world testing
- **Risk**: Prompt engineering may need iteration for consistent results

### ✅ **Git Repository Generation**
- GitPython creates actual git repos with proper commit dates
- Chronological sorting regardless of input order
- Branch creation for major life changes
- **Status**: Solid implementation

### ✅ **Download Functionality**
- Persistent storage in `generated_repos/` folder
- ZIP file creation for easy download
- Unique timestamp-based naming
- **Status**: Working, users get real git repositories

### ✅ **Git Log Visualization**
- Terminal-style commit display
- Shows hash, message, date, author
- Clean monospace formatting
- **Status**: Working well

## Technical Architecture

### **Stateless Processing Model**
```
Input → AI Parse → Git Generate → Store Temporarily → Download → Cleanup
```
- No user accounts needed
- Privacy-friendly (no personal data stored)
- Tool/converter approach rather than service platform

### Backend (`app.py`)
- **Framework**: Flask web server
- **AI Processing**: Anthropic Claude API
- **Git Integration**: GitPython for repository creation
- **File Handling**: ZIP generation for downloads
- **Storage**: Local persistent storage with cleanup potential

### Frontend (`templates/index.html`)
- **Design**: Are.na-inspired minimal aesthetic
- **Typography**: Times New Roman + system fonts
- **Interaction**: AJAX form submission with download links
- **Responsive**: Mobile-friendly grid layout

## Dependencies
```
flask==2.3.3
anthropic==0.40.0  # Updated from 0.8.1 to fix compatibility
python-dotenv==1.0.0
GitPython==3.1.40
python-dateutil==2.8.2
```

## Environment Setup
- Python 3.9.6 in virtual environment (`venv/`)
- Anthropic API key in `.env` file
- Flask development server on port 5000

## Development Issues & Solutions

### Issue 1: Anthropic SDK Compatibility
**Problem**: `TypeError: __init__() got an unexpected keyword argument 'proxies'`
**Solution**: Updated from anthropic==0.8.1 to anthropic==0.40.0

### Issue 2: Permission Prompts
**Problem**: Claude Code still asking for tool execution permission
**Solution**: Updated `~/.claude/settings.json` with:
```json
{
  "permissions": {
    "defaultMode": "bypassPermissions",
    "allow": ["*", "Bash(*)", "Read(*)", "Write(*)", "Edit(*)", ...]
  }
}
```

## AI Prompt Engineering
The journal parsing uses a structured prompt that asks Claude to:
- Extract life events with dates
- Generate meaningful commit messages
- Identify major life changes (for git branches)
- Return structured JSON format

## Git Repository Structure
- Each life event becomes a commit with proper author date
- Major life changes create new branches
- Event files are created as markdown (`event_001.md`, etc.)
- Commits are sorted chronologically regardless of input order

## Hackathon Demo Features
- Real-time journal processing
- Actual git repository creation
- Terminal-style commit log visualization
- Responsive design for presentation screens

## Critical Technical Challenges

### 1. **AI Prompt Engineering** (Highest Priority)
The journal parsing quality determines the entire user experience:
- Date extraction reliability from natural language
- Consistent JSON output format
- Handling ambiguous or sparse information
- Identifying meaningful life events vs daily minutiae

### 2. **Error Handling & Fallbacks**
- Graceful degradation when AI parsing fails
- User feedback for unclear journal entries
- Timeout handling for API calls

### 3. **Repository Quality**
- Meaningful commit messages that feel authentic
- Proper git history that makes sense chronologically
- Branch logic for major life transitions

## Architecture Decisions

### **Why No User Accounts**
- Core use case is "convert and download"
- Privacy-friendly - no personal data retention
- Simpler infrastructure and demo
- More like an art installation than a platform

### **Why Local Storage**
- Hackathon simplicity
- Easy cleanup and management
- Can easily migrate to cloud storage later

## Extension Opportunities
- **Background Processing**: Queue system for longer AI processing
- **Export Formats**: Support .git, .tar, bare repos
- **Embeddable Widget**: For integration into other platforms
- **CLI Version**: Command-line tool for developers
- **API-First**: Enable third-party integrations
- **Multiple AI Models**: Compare different parsing approaches

## File Structure
```
commits-of-your-life/
├── venv/                 # Virtual environment
├── templates/
│   └── index.html       # Frontend interface
├── static/              # (empty, styles inline)
├── app.py              # Flask backend
├── requirements.txt    # Dependencies
├── .env               # API key (gitignored)
├── .gitignore        # Ignore sensitive files
├── README.md         # Project concept
└── DEVELOPMENT.md    # This file
```

## Running the Project
```bash
source venv/bin/activate
python app.py
# Visit http://127.0.0.1:5000
```

## Technical Priorities for Hackathon Success

### **High Priority** (Demo Blockers)
1. **AI parsing reliability** - The core differentiator
2. **Error handling** - Graceful failure modes
3. **Download functionality** - Users need to get their repos

### **Medium Priority** (Demo Enhancers)
1. **Frontend polish** - First impressions matter
2. **Example prompts** - Help users write effective journal entries
3. **Git history quality** - Meaningful commit messages

### **Low Priority** (Nice to Have)
1. **Performance optimization** - Works fine for demo scale
2. **Advanced git features** - Branches, merges, tags
3. **Multiple export formats** - ZIP is sufficient

## Key Technical Lessons
1. **Start with AI prompt engineering** - Everything depends on parsing quality
2. **Stateless is simpler** - Avoid user accounts unless essential
3. **Real git repos add authenticity** - Not just visualization
4. **Frontend aesthetics crucial** - Art project needs artistic presentation
5. **Error states matter** - AI can fail, plan for it

---

# MVP Development Log

## Commit `af007c3` - Multi-Agent System Implementation

### **What We Built:**

#### **Multi-Agent Architecture (`agents.py`)**
- **5 Specialized Agents** for journal parsing reliability:
  1. **Event Extractor** - Identifies significant life moments
  2. **Date Resolver** - Handles temporal reasoning and date inference
  3. **Commit Generator** - Creates git-style commit messages
  4. **Branch Classifier** - Identifies major life changes for branching
  5. **Validator** - Quality control and consistency checking

- **Benefits over single prompt:**
  - Higher accuracy through task specialization
  - Better error handling and fallbacks
  - Modular debugging and improvement
  - More extensible architecture

#### **Frontend Redesign**
- **Are.na-inspired aesthetic** - minimal, editorial typography
- **Times New Roman + system fonts** for artistic feel
- **Poetic UX copy** - "Archive your becoming..."
- **Clean spacing** and dotted dividers
- **Sticky input** section for better UX

#### **Infrastructure Improvements**
- **Persistent storage** - `generated_repos/` instead of temp files
- **ZIP download** - Users get real git repositories
- **Unique naming** - Timestamped repo names for multiple users
- **Error handling** - Graceful degradation when agents fail

### **Current Status:**
✅ **Working MVP** - All core features functional
✅ **Server running** - http://127.0.0.1:5000
✅ **Git history** - Proper version control
✅ **Documentation** - Comprehensive technical notes

### **Testing Priorities:**
1. **Multi-agent reliability** - Test with diverse journal styles
2. **Date inference accuracy** - Verify temporal reasoning works
3. **Git repository quality** - Check commit messages and branching
4. **Download functionality** - Ensure ZIP files contain valid repos
5. **Error handling** - Test graceful failures

### **Known Technical Debt:**
- **Async/await** - Current implementation uses sync wrapper for Flask
- **API error handling** - Limited retry logic for Anthropic API
- **Storage cleanup** - No automatic deletion of old repositories

### **Next Technical Iterations:**
- **DSPy integration** - Automatic prompt optimization framework
- **Background job processing** - Queue system for longer processing
- **Validation metrics** - Automated quality assessment
- **Agent communication** - Inter-agent feedback and refinement

---

## Pipeline Performance & Timing

### **Agent Pipeline (as of 2026-02-21)**

```
Step 1 (sequential):  Event extraction         ~12-13s
Step 2 (parallel):    Date resolution    ─┐
                      Commit generation   ├─  ~29-37s (3 API calls in parallel)
                      Branch classification─┘
Step 3 (local):       Validation               ~0s
                      Git repo + zip            ~1-2s
─────────────────────────────────────────────────
Total end-to-end:                              ~50-55s
```

### **Parallelization History:**
- **v1**: All 5 agents sequential → ~70s+
- **v2**: Dates + commits in parallel, branch classification sequential → ~51s
- **v3 (current)**: Dates + commits + branch classification all parallel → ~50s

### **Bottleneck Analysis:**
- Event extraction must run first (other agents depend on its output)
- The parallel step is bounded by the slowest API call (usually date resolution at ~29s due to higher max_tokens=5000)
- Validation is local-only (no API call), essentially free
- Git repo creation + zip packaging is ~1-2s

### **Bugs Fixed During Testing:**
1. **Markdown stripping** - Claude responses sometimes wrapped in ```json blocks; replaced fragile string slicing with regex
2. **Git add paths** - `repo.index.add()` needed repo-relative paths, not absolute
3. **Timezone-aware dates** - GitPython requires timezone-aware datetimes; added UTC fallback
4. **Duplicate branch names** - Added counter-based deduplication for semantic branch names

---

## Next Steps

### **Time Optimization**
- **Use a faster model for simpler agents** — Date resolution and commit generation don't need Opus; switching to Haiku or Sonnet could cut the parallel step from ~30s to ~5-10s
- **Batch API calls** — Combine date resolution + commit generation into a single prompt that returns both, reducing from 3 parallel calls to 2
- **Stream event extraction** — Start processing events as they're extracted rather than waiting for the full list
- **Cache prompts** — Use prompt caching for the system-level instructions that don't change between requests

### **Branch Classification Quality**
- The classifier often returns no branches — prompt needs tuning to be more aggressive about flagging major life changes
- Consider a threshold-based approach instead of binary classification

### **Frontend & UX**
- Add a progress indicator showing which agent is currently running
- Show estimated time remaining based on journal length
- Add example journal entries users can click to try
- Mobile layout improvements

### **Robustness**
- Add retry logic for failed API calls (currently fails silently with fallbacks)
- Better error messages surfaced to the user when parsing fails
- Rate limiting for the API endpoint
- Automatic cleanup of old generated repos

### **Features**
- Support multiple export formats (.tar, bare repo)
- Let users edit/refine extracted events before generating the repo
- Add git tags for decade markers or life phases
- Background job processing with polling for longer journals
- CLI version for developer users

---
*Built for hackathon demo - version-controlled life storytelling*