#!/bin/sh
# Turn a pgBackRest git checkout into upstream's distribution layout (the
# release asset): generated sources, rendered man page and HTML docs, and the
# "dist" marker.  Mirrors upstream .github/workflows/test-dist.yml, calling
# build/dist.sh directly instead of going through "meson dist".
set -eu

# Upstream builds the distribution before the release is tagged.  With the tag
# of HEAD present the release-note history of that tag is empty and the doc
# build fails; hide it in this throwaway checkout.
for tag in $(git tag --points-at HEAD); do
    git tag -d "$tag" > /dev/null
done

# Render the man page, the HTML documentation and the distribution README
doc/release.py --dist --no-exe

# Export the committed tree, as "meson dist" does, and run upstream's dist hook
dist_root="$OUT_DIR/pgbackrest-$VERSION"
mkdir -p "$dist_root"
git archive HEAD | tar -x -C "$dist_root"
MESON_DIST_ROOT="$dist_root" MESON_SOURCE_ROOT="$SRC_DIR" sh build/dist.sh

# The doc build stamps the day it ran; use the commit date so the same commit
# always renders the same files (for a release that is the release date).
updated=$(date -u -d "@$SOURCE_DATE_EPOCH" '+%B %-d, %Y')
sed -i -E "s/Updated [A-Z][a-z]+ [0-9]{1,2}, [0-9]{4}/Updated $updated/" "$dist_root"/doc/html/*.html
