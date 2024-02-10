#!/bin/bash

echo Pruning Catalogs that have no associated Time Schedule .. 

for f in *; do
    if [[ "$f" == *.html ]]; then
        if [[ $(find * -name "$f.1" | wc -l) == 0 ]]; then
            rm -rf $f
        fi
    fi
done

echo Done!