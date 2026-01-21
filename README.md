# Ascendo Conference Agent

> **Automated B2B prospect discovery from conference websites using a multi-agent AI framework**

A conversational AI system that scrapes conference websites, extracts company information, and automatically scores prospects for ICP (Ideal Customer Profile) fit—reducing manual research from hours to minutes.

---

## 🎯 Business Value

| Metric | Value |
|--------|-------|
| **Manual time saved** | ~4 hours → 5 minutes |
| **Companies extracted** | 100+ per conference |
| **ICP fit accuracy** | High (domain-specific scoring) |
| **Cost** | Free tier (Gemini 2.5 Flash Lite) |
| **Reproducibility** | Full CSV audit trail |

### Target Use Case
Automates prospect qualification for **field service operations** companies attending industry conferences. Ideal for identifying high-value leads in sectors like utilities, telecom, HVAC, and FSM platforms (SAP FSM, ServiceNow, IFS).

---

## 🏗️ Multi-Agent Architecture

The system uses a **conversational orchestrator pattern** where specialized agents collaborate through message passing:

```
┌──────────┐    ┌──────────┐    ┌───────────┐    ┌────────────┐
│ Planner  │ -> │ Fetcher  │ -> │ Extractor │ -> │ Normalizer │
└──────────┘    └──────────┘    └───────────┘    └────────────┘
                                                         │
                                                         v
                                                  stage1_extracted_companies.csv
                                                         │
        ┌────────────────────────────────────────────────┘
        v
┌──────────────┐    borderline_companies    ┌────────────────┐
│  Fit Agent   │ ─────────────────────────> │  Enrichment    │
│              │                             │  Agent         │
└──────────────┘                             └────────────────┘
        │                                            │
        v                                            v
 stage2_icp_initial.csv              enriched_companies (no new scraping)
                                                     │
                                                     v
                                            ┌─────────────────┐
                                            │ Fit Rescore     │
                                            │ Agent           │
                                            └─────────────────┘
                                                     │
                                                     v
                                            stage2_icp_final.csv
                                                     │
                                                     v
                                            ┌──────────────┐
                                            │ Export Agent │
                                            └──────────────┘
                                                     │
                                                     v
                                          conference_companies.xlsx
```

### Agent Responsibilities

| Agent | Purpose | Technology |
|-------|---------|------------|
| **Planner** | Creates target URLs to scrape (speakers, sponsors, agenda) | Rule-based |
| **Fetcher** | Renders JavaScript-heavy pages, handles lazy-loading | Playwright |
| **Extractor** | Parses HTML for company names from logos/speaker tags | BeautifulSoup |
| **Normalizer** | Deduplicates companies, writes stage 1 CSV | Pandas |
| **Fit Agent** | Scores ICP fit (Yes/Maybe/No), identifies borderline cases | Gemini LLM |
| **Enrichment** | Searches cached HTML for additional evidence | Text search |
| **Fit Rescore** | Re-evaluates borderline companies with enriched data | Gemini LLM |
| **Export** | Generates final Excel report | openpyxl |

---

## 🔄 Knowledge Reuse & Conversation Loop

### The Enrichment Feedback Loop

**Problem**: Initial LLM scoring may mark companies as "Maybe" due to insufficient evidence.

**Solution**: Instead of scraping new pages (expensive + slow), the system:

1. **Fit Agent** identifies low-confidence "Maybe" companies
2. **Enrichment Agent** searches *already-fetched HTML* (`state.raw_pages`) for additional mentions
3. **Fit Rescore Agent** re-evaluates with enriched evidence

**Key Benefits**:
- ✅ **Zero redundant web requests** (all data already in memory)
- ✅ **Selective LLM calls** (only borderline cases get re-scored)
- ✅ **Evidence layering** (new findings append to existing records)
- ✅ **Full audit trail** (CSV artifacts at each stage)

```python
# From EnrichmentAgent.handle() - searches cached HTML
for rp in state.raw_pages:  # No new HTTP requests!
    if company_name.lower() in rp.html.lower():
        evidence_found.append(Evidence(
            source_url=rp.url,
            snippet=text_context,
            source_type="enrichment"
        ))
```

---

## ⚡ API Rate Limit Handling

### Challenge
Gemini free tier: **15 requests per minute (RPM)**

### Solution: Multi-Layer Rate Limiting

The `LLMClient` implements a robust rate limiting system:

#### 1. Minimum Interval Throttle
```python
# Enforces 3+ second gap between requests
gemini_min_interval_s = 3.0  # Configurable in config.py
```

#### 2. Rolling 60-Second Window
```python
# Tracks all calls in last 60 seconds
_CALL_HISTORY: deque = deque(maxlen=100)
_RPM_LIMIT = 15

# Blocks request if at capacity, waits for oldest call to expire
if len(_CALL_HISTORY) >= 15:
    wait_until = oldest_call_timestamp + 60.0
    time.sleep(wait_until - now)
```

#### 3. Exponential Backoff on 429 Errors
```python
# Retries with exponential delay: 5s, 10s, 20s...
if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
    delay = 5 * (2 ** attempt)
    time.sleep(delay)
```

#### 4. Batch Processing
```python
# Processes 20 companies per LLM call
batch_size = 20
for i in range(0, len(companies), batch_size):
    batch = companies[i : i + batch_size]
    results = client.json_chat(system_prompt, batch)
```

**Result**: System handles 100+ companies while staying under 15 RPM limit.

---

## 📊 Artifact Trail & Reproducibility

### CSV Outputs

1. **`stage1_extracted_companies.csv`** (Normalizer Agent)
   - Raw extraction results
   - Columns: `company_name`, `evidence_urls`, `evidence_count`

2. **`stage2_icp_initial.csv`** (Fit Agent)
   - Initial LLM scoring
   - Columns: `company_name`, `fit`, `reasoning`, `confidence`

3. **`stage2_icp_final.csv`** (Fit Rescore Agent)
   - Final scores after enrichment loop
   - Includes updated `enriched_evidence`

4. **`{conference}_companies.xlsx`** (Export Agent)
   - Deliverable with all metadata

### Conversation Logging

```python
# Tracks inter-agent communication
state.notes["conversation_log"] = [
    {"iteration": 1, "from": "fit", "to": "enrichment", "content": "enrich_request"},
    {"iteration": 2, "from": "enrichment", "to": "fit_rescore", "content": "rescore_request"}
]
```

---

## 🚀 Installation

```bash
# Install dependencies
pip install -e .

# Set up API key
echo 'GEMINI_API_KEY=your_key_here' > .env
echo 'GEMINI_MODEL=models/gemini-2.5-flash-lite' >> .env
```

### Prerequisites
- Python 3.10+
- Playwright browsers: `playwright install`

---

## 💻 Usage

### Basic Command
```bash
python -m ascendo_conf_agent.cli \
  --url https://fieldserviceusa.iqpc.com/ \
  --headless true \
  --max-pages 15
```

### Parameters
- `--url`: Conference website URL
- `--headless`: Run browser in headless mode (`true`/`false`)
- `--max-pages`: Maximum pages to scrape (default: 10)

### Output
```
outputs/
├── stage1_extracted_companies.csv
├── stage2_icp_initial.csv
├── stage2_icp_final.csv
└── fieldserviceusa_companies.xlsx
```

---

## ⚙️ Configuration

Edit `src/ascendo_conf_agent/config.py` or `.env`:

```python
# Rate limiting
GEMINI_MIN_INTERVAL_S = 3.0      # Min seconds between API calls
GEMINI_RPM_LIMIT = 15            # Requests per minute

# Scraping
NAV_TIMEOUT_MS = 45000           # Playwright page load timeout
SCROLL_PAUSE_SEC = 1.5           # Wait for lazy-loaded images

# Batch processing
FIT_BATCH_SIZE = 20              # Companies per LLM call
```

---

## 🧪 Technical Stack

| Component | Technology |
|-----------|------------|
| LLM | Google Gemini 2.5 Flash Lite |
| Web Scraping | Playwright (async) |
| HTML Parsing | BeautifulSoup4 |
| Data Processing | Pandas |
| Orchestration | Custom state machine |
| Output Format | Excel (openpyxl) |

---

## 📁 Project Structure

```
ascendo-ai-task/
├── src/ascendo_conf_agent/
│   ├── cli.py                    # Entry point
│   ├── conversational.py         # Agent orchestrator & conversation loop
│   ├── config.py                 # Configuration
│   ├── types.py                  # Data models (CompanyRecord, Evidence, etc.)
│   ├── graph/nodes/              # Agent implementations
│   │   ├── planner.py
│   │   ├── fetcher.py
│   │   ├── extractor.py
│   │   ├── normalizer.py
│   │   ├── enrich.py
│   │   ├── qa.py
│   │   └── export.py
│   ├── llm/
│   │   ├── client.py             # Rate-limited LLM client
│   │   └── prompts/              # System prompts
│   ├── scraping/
│   │   └── playwright_fetch.py   # Browser automation
│   └── utils/
│       ├── text.py
│       └── urls.py
├── outputs/                      # Generated artifacts
└── pyproject.toml
```

---

## 🎯 ICP Scoring Logic

The **Fit Agent** evaluates companies against Ascendo's target profile:

### Target Industries
- Utilities (electric, gas, water, waste management)
- Telecommunications
- HVAC/facilities maintenance
- Field Service Management platforms (SAP FSM, ServiceNow, IFS)

### Scoring Criteria
- **Yes**: Clear field service operations, large workforce
- **Maybe**: Borderline fit or insufficient evidence (triggers enrichment)
- **No**: B2C only, no field operations, wrong industry

Example prompt excerpt from `prospect_fit_batch.md`:
```
Score each company as:
- "Yes" if they manage distributed field technicians or assets
- "Maybe" if unclear (will trigger additional research)
- "No" if purely B2C or no field operations
```

---

## 🔒 Error Handling

- **429 Rate Limits**: Exponential backoff with parsed retry-after headers
- **Playwright Timeouts**: Configurable navigation timeout (45s default)
- **LLM Failures**: Retry logic with max 3 attempts
- **Invalid JSON**: Graceful fallback to text parsing

---

## 📈 Future Enhancements

- [ ] Support for multiple LLM providers (Anthropic, OpenAI)
- [ ] Parallel scraping with worker pool
- [ ] Real-time progress dashboard
- [ ] Contact enrichment (LinkedIn, Apollo.io integration)
- [ ] Automated CRM export (HubSpot, Salesforce)

---

## 📄 License

MIT

---

## 👥 Contributing

Contributions welcome! Key areas for improvement:
- Additional conference website parsers
- Enhanced entity extraction (logos with OCR)
- Multi-language support
- Custom ICP profiles

---

## 🙏 Acknowledgments

Built with Google Gemini 2.5 Flash Lite for cost-effective LLM inference.
