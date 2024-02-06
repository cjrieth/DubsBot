#!/bin/sh

echo Downloading Course Catalog for all Majors ...

lynx -listonly -nonumbers -dump https://www.washington.edu/students/crscat/ | grep .html | grep crscat | grep -v \# | grep -v glossary | sort -u | xargs -l1 wget -q -P /workspaces/azure-search-openai-demo/data

echo Done!