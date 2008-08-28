#!/bin/bash
# This script uninstalls zine from PREFIX which defaults
# to /usr.

if [ x$PREFIX == x ]; then
  PREFIX=/usr
fi

echo "Uninstalling Zine from $PREFIX"
rm -rf $PREFIX/lib/zine
rm -rf $PREFIX/share/zine
echo "All done."
