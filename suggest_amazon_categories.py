#!/usr/bin/env python3
"""
Suggest Amazon search category / keyword ideas using the OpenAI API.

Usage:
  # Option A: put OPENAI_API_KEY in a .env file in this folder (see .env.example)
  python suggest_amazon_categories.py
  # Option B: export OPENAI_API_KEY="sk-..."
  python suggest_amazon_categories.py

Requires: pip install -r requirements-suggest.txt
  python suggest_amazon_categories.py --topic "handmade terracotta planters"
  python suggest_amazon_categories.py --count 15 --marketplace india
  python suggest_amazon_categories.py --extra "focus on handmade design; keyword ideas only"

"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional


def load_env_file(env_path: Optional[Path]) -> None:
    """Load OPENAI_API_KEY from .env if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if env_path and env_path.is_file():
        load_dotenv(env_path)
    else:
        load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Suggest Amazon search ideas via OpenAI.")
    parser.add_argument(
        "--topic",
        default="handmade / artisan home and lifestyle products",
        help="What you want to sell or explore (e.g. handmade ceramics, block print textiles).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=12,
        help="How many keyword/category suggestions to request.",
    )
    parser.add_argument(
        "--marketplace",
        default="amazon.com.au",
        help="Target marketplace hint for the model (default: amazon.com.au).",
    )
    parser.add_argument(
        "--extra",
        default="",
        help="Optional extra context appended to the prompt (e.g. niche constraints).",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model name.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Path to .env (default: .env in current directory).",
    )
    args = parser.parse_args()

    load_env_file(args.env_file)

    raw_key = os.environ.get("OPENAI_API_KEY", "")
    api_key = raw_key.strip().strip('"').strip("'")
    if not api_key:
        print(
            "Set OPENAI_API_KEY in a .env file next to this script, or export it. "
            "Install python-dotenv to load .env: pip install python-dotenv",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from openai import OpenAI
        from openai import AuthenticationError as OpenAIAuthError
    except ImportError:
        print("Install: pip install openai", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    system = """You help sellers choose practical Amazon search keywords and category-style phrases.
Output must be JSON only, no markdown. Do not give legal advice; focus on shopping and discovery keywords."""

    extra_block = f"\nAdditional context from user: {args.extra}\n" if args.extra.strip() else ""

    user = f"""Suggest {args.count} distinct Amazon search strings for marketplace {args.marketplace}.

Topic / focus: {args.topic}
{extra_block}
Constraints:
- Phrases should be things a buyer would type in Amazon search (2–6 words each).
- Mix broad category-style terms and specific product terms.
- Prefer terms suitable for handmade, artisan, or design-led products where applicable.
- Return JSON object with key "suggestions" whose value is an array of objects, each with:
  "phrase" (string), "intent" (short string: e.g. gift, daily use, premium), "notes" (one line, optional).

Example shape:
{{"suggestions": [{{"phrase": "handmade ceramic mugs","intent": "gift","notes": "..."}}]}}"""

    try:
        resp = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
    except OpenAIAuthError as e:
        print(
            "OpenAI rejected your API key (401).\n"
            "- Create or copy a valid secret key from: https://platform.openai.com/api-keys\n"
            "- In .env use exactly: OPENAI_API_KEY=sk-...  (no spaces around =, no extra quotes)\n"
            "- If you rotated the key, update .env and run again.",
            file=sys.stderr,
        )
        raise SystemExit(1) from e

    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        print(content)
        sys.exit(0)

    suggestions = data.get("suggestions", data) if isinstance(data, dict) else data
    if isinstance(suggestions, dict):
        suggestions = suggestions.get("suggestions", [])

    print(json.dumps({"suggestions": suggestions}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
