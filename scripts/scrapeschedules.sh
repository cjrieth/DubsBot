#!/bin/sh

echo Dowloading HTML Schedules for all classes ...

lynx -listonly -nonumbers -dump https://www.washington.edu/students/timeschd/SPR2024/ | grep .html | grep SPR2024 | grep -v \# |sort -u | xargs -l1 wget -q -P /workspaces/azure-search-openai-demo/data

echo Done!