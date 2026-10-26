"""
OmniStream Pro - Interactive Rename Modes Tester
Allows testing the 3 Rename modes:
1. Netflix Rename
2. TMDB ID Rename
3. IMDb ID Rename
"""

import sys
import os

# Add desktop directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop"))

from netflix_resolver import (
    extract_netflix_id,
    extract_imdb_id,
    extract_tmdb_id,
    clean_show_title,
    resolve_media_details,
    resolve_media_id_rename
)

def test_single(input_value):
    print("\n" + "=" * 65)
    print(f"INPUT: {input_value}")
    print("=" * 65)
    
    nf_id = extract_netflix_id(input_value)
    imdb_id = extract_imdb_id(input_value)
    tmdb_id = extract_tmdb_id(input_value)
    clean_title, ep_tag = clean_show_title(input_value)
    
    print(f"[*] Extracted Netflix ID: {nf_id}")
    print(f"[*] Extracted IMDb ID:    {imdb_id}")
    print(f"[*] Extracted TMDB ID:    {tmdb_id}")
    print(f"[*] Clean Title:          '{clean_title}' | Ep Tag: '{ep_tag}'")
    print("-" * 65)
    print("[*] Fetching online metadata (IMDb & TMDB via Wikidata)...")
    
    details = resolve_media_details(
        netflix_id=nf_id,
        title=clean_title if not nf_id else None,
        raw_input=input_value,
        imdb_id=imdb_id,
        tmdb_id=tmdb_id
    )
    print(f"    Canonical Title : {details.get('title')}")
    print(f"    Release Year    : {details.get('year')}")
    print(f"    Media Type      : {details.get('type')}")
    print(f"    Netflix ID      : {details.get('netflix_id')}")
    print(f"    IMDb ID         : {details.get('imdb_id')}")
    print(f"    TMDB ID         : {details.get('tmdb_id')}")
    print("-" * 65)
    
    # 1. Netflix Rename
    name_nf = resolve_media_id_rename(
        mode="netflix_rename",
        netflix_id=details.get("netflix_id"),
        title=details.get("title") or input_value,
        raw_input=input_value,
        imdb_id=details.get("imdb_id"),
        tmdb_id=details.get("tmdb_id")
    )
    
    # 2. TMDB ID Rename
    name_tmdb = resolve_media_id_rename(
        mode="tmdb_rename",
        netflix_id=details.get("netflix_id"),
        title=details.get("title") or input_value,
        raw_input=input_value,
        imdb_id=details.get("imdb_id"),
        tmdb_id=details.get("tmdb_id")
    )
    
    # 3. IMDb ID Rename
    name_imdb = resolve_media_id_rename(
        mode="imdb_rename",
        netflix_id=details.get("netflix_id"),
        title=details.get("title") or input_value,
        raw_input=input_value,
        imdb_id=details.get("imdb_id"),
        tmdb_id=details.get("tmdb_id")
    )
    
    print("DOWNLOADED FILE OUTPUT NAMES:")
    print(f"  [1] Netflix Rename :  {name_nf}.mkv")
    print(f"  [2] TMDB ID Rename :  {name_tmdb}.mkv")
    print(f"  [3] IMDb ID Rename :  {name_imdb}.mkv")
    print("=" * 65)

def run_predefined_demos():
    print("\n>>> RUNNING PREDEFINED TEST CASES <<<\n")
    demos = [
        "https://netmirror.app/watch/81902147",                  # Sonic 3 (Movie via NetMirror URL)
        "81902147",                                             # Sonic 3 (Raw Netflix ID)
        "https://netmirror.app/watch/81948683?ep=S04E01",       # Stranger Things S04E01
        "Stranger Things S04E01",                               # Title + Episode
        "Red Notice",                                           # Movie Title
        "Squid Game S01E01",                                    # TV Series Episode
    ]
    for d in demos:
        test_single(d)

def main():
    print("=================================================================")
    print("  OmniStream Pro - Rename Modes Interactive Tester")
    print("  Tests: [1] Netflix Rename | [2] TMDB ID Rename | [3] IMDb ID Rename")
    print("=================================================================")
    
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        test_single(query)
        return

    while True:
        print("\nChoose an option:")
        print("  1. Run automatic sample tests (NetMirror URLs, IDs, Series)")
        print("  2. Enter a custom URL / Netflix ID / Movie Name to test")
        print("  3. Exit")
        choice = input("\nEnter choice (1/2/3): ").strip()
        
        if choice == "1":
            run_predefined_demos()
        elif choice == "2":
            user_input = input("\nEnter NetMirror URL, Netflix ID, or Movie/Show Title: ").strip()
            if user_input:
                test_single(user_input)
            else:
                print("No input provided.")
        elif choice in ("3", "q", "exit"):
            print("Exiting tester. Have a great day!")
            break
        else:
            print("Invalid option. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    main()
