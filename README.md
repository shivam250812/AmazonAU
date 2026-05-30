# Amazon Pipeline Automation

This is a one-click automation pipeline that uses AI to suggest product categories, scrapes Amazon data (including Helium 10 revenue metrics), checks Seller Central for gating status, and generates a merged final report.

## Prerequisites

1. **Python 3.9+**
2. **Google Chrome** installed on your system.
3. An **OpenAI API Key** (for generating keyword suggestions).
4. A **Helium 10** account (free or paid) for extracting revenue.
5. An **Amazon Seller Central** account.

## Setup Instructions

### 1. Clone & Install Dependencies

```bash
# Clone the repository
git clone <your-repo-url>
cd <repo-name>

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

### 2. Add API Keys
Create a `.env` file in the root of the project and add your OpenAI key:
```bash
OPENAI_API_KEY=sk-...
```

### 3. Initialize Browser Profile (One-Time Setup)

Because Playwright uses an isolated Chrome profile by default, you need to configure it with the Helium 10 extension and your Amazon login before you can run the pipeline automatically.

Run the pipeline in setup mode:
```bash
python run_pipeline.py --setup
```

This will launch a blank Chrome window. You have ~5 minutes to:
1. Navigate to the **Chrome Web Store** and install the **Helium 10** extension.
2. Click the Helium 10 puzzle icon and **Log in**.
3. Go to **sellercentral.amazon.com.au** and **Log in**.
4. Allow the browser to close automatically when the timer expires. Your session is now saved in the `chrome-data/` folder.

> **Note:** Do NOT delete the `chrome-data/` folder, or you will have to repeat this setup process.

---

## Usage

### Run the Full Pipeline

```bash
# Provide a topic, and the AI will suggest keywords and scrape them
python run_pipeline.py --topic "copper water bottles" --count 5
```

### Test Mode

To verify everything is working without running a long scrape, use test mode (uses only 1 keyword and scrapes only 1 page):
```bash
python run_pipeline.py --test
```

### Run with Specific Keywords (Skip AI)

If you already know the exact keywords you want to scrape:
```bash
python run_pipeline.py --keywords "copper bottle,standing desk"
```

## How It Works

The orchestrator (`run_pipeline.py`) chains 5 scripts together:
1. `suggest_amazon_categories.py`: Uses OpenAI to generate Amazon search keywords based on a topic.
2. `script.py`: Scrapes Amazon product details and Helium 10 revenue for those keywords. Saves to `output.csv`.
3. `extract_asins.py`: Pulls unique ASINs from `output.csv`. Saves to `input.csv`.
4. `sellercentral.py`: Logs into Seller Central and checks the gating status for each ASIN. Saves to `gated_output.csv`.
5. `merge_results.py`: Combines the scraped product data and gating status into `final_report.csv`.
