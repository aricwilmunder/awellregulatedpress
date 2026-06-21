#!/bin/bash
cd "$(dirname "$0")"
python3 build_sitemap.py
echo
echo "Press Return to close."
read
