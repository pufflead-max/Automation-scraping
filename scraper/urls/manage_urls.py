#!/usr/bin/env python3
"""
CLI tool to manage scraper URL files.
Usage: python manage_urls.py [scraper] [action] [url]
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.url_loader import URLLoader


def get_url_file(scraper_type: str) -> str:
    """Get the URL file path for a scraper."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, f"{scraper_type}_urls.txt")


def list_urls(scraper_type: str):
    """List all URLs for a scraper."""
    file_path = get_url_file(scraper_type)
    
    if not os.path.exists(file_path):
        print(f"No URL file found for {scraper_type}")
        print(f"Expected: {file_path}")
        return
    
    try:
        urls = URLLoader.load_urls_from_file(file_path)
        print(f"\n{scraper_type.upper()} URLs ({len(urls)} total):")
        print("=" * 60)
        for idx, url in enumerate(urls, 1):
            print(f"{idx}. {url}")
        print("=" * 60)
    except Exception as e:
        print(f"Error reading URLs: {e}")


def add_url(scraper_type: str, url: str):
    """Add a URL to the scraper's file."""
    file_path = get_url_file(scraper_type)
    
    # Create file if it doesn't exist
    if not os.path.exists(file_path):
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            f.write(f"# {scraper_type.upper()} URLs\n\n")
    
    # Check if URL already exists
    try:
        existing_urls = URLLoader.load_urls_from_file(file_path)
        if url in existing_urls:
            print(f"URL already exists in {scraper_type}_urls.txt")
            return
    except:
        pass
    
    # Add URL
    with open(file_path, 'a') as f:
        f.write(f"{url}\n")
    
    print(f"✓ Added URL to {scraper_type}_urls.txt")
    print(f"  {url}")


def remove_url(scraper_type: str, url: str):
    """Remove a URL from the scraper's file."""
    file_path = get_url_file(scraper_type)
    
    if not os.path.exists(file_path):
        print(f"No URL file found for {scraper_type}")
        return
    
    # Read all lines
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Filter out the URL
    new_lines = [line for line in lines if line.strip() != url]
    
    if len(new_lines) == len(lines):
        print(f"URL not found in {scraper_type}_urls.txt")
        return
    
    # Write back
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    
    print(f"✓ Removed URL from {scraper_type}_urls.txt")
    print(f"  {url}")


def clear_urls(scraper_type: str):
    """Clear all URLs from the scraper's file."""
    file_path = get_url_file(scraper_type)
    
    if not os.path.exists(file_path):
        print(f"No URL file found for {scraper_type}")
        return
    
    # Keep only comment lines
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    comment_lines = [line for line in lines if line.strip().startswith('#') or not line.strip()]
    
    with open(file_path, 'w') as f:
        f.writelines(comment_lines)
    
    print(f"✓ Cleared all URLs from {scraper_type}_urls.txt")


def show_help():
    """Show usage information."""
    print("""
Scraper URL Management Tool

Usage:
    python manage_urls.py <scraper> <action> [url]

Scrapers:
    facebook    - Facebook groups/pages
    craigslist  - Craigslist categories
    nextdoor    - Nextdoor neighborhoods

Actions:
    list                    - List all URLs
    add <url>              - Add a new URL
    remove <url>           - Remove a URL
    clear                  - Clear all URLs (keeps comments)

Examples:
    python manage_urls.py facebook list
    python manage_urls.py facebook add "https://www.facebook.com/groups/123"
    python manage_urls.py craigslist remove "https://boston.craigslist.org/search/aos"
    python manage_urls.py nextdoor clear
    """)


def main():
    if len(sys.argv) < 3:
        show_help()
        sys.exit(1)
    
    scraper_type = sys.argv[1].lower()
    action = sys.argv[2].lower()
    
    if scraper_type not in ['facebook', 'craigslist', 'nextdoor']:
        print(f"Invalid scraper type: {scraper_type}")
        print("Valid options: facebook, craigslist, nextdoor")
        sys.exit(1)
    
    if action == 'list':
        list_urls(scraper_type)
    elif action == 'add':
        if len(sys.argv) < 4:
            print("Error: URL required for 'add' action")
            sys.exit(1)
        add_url(scraper_type, sys.argv[3])
    elif action == 'remove':
        if len(sys.argv) < 4:
            print("Error: URL required for 'remove' action")
            sys.exit(1)
        remove_url(scraper_type, sys.argv[3])
    elif action == 'clear':
        clear_urls(scraper_type)
    else:
        print(f"Invalid action: {action}")
        print("Valid actions: list, add, remove, clear")
        sys.exit(1)


if __name__ == '__main__':
    main()
