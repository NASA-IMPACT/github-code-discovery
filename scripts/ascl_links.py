import sys
import pandas as pd
from gcd.ascl_search import fetch_and_process_ascl_links
from config import GITHUB_TOKEN

def main():
    fetch_and_process_ascl_links(token=GITHUB_TOKEN)

if __name__ == "__main__":
    main()

