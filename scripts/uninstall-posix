#!/bin/bash
# This script uninstalls textpress from PREFIX which defaults
# to /usr.

if [ x$PREFIX == x ]; then
  PREFIX=/usr
fi

echo "Uninstalling TextPress from $PREFIX"
rm -rf $PREFIX/lib/textpress
rm -rf $PREFIX/share/textpress
rm $PREFIX/share/locale/*/LC_MESSAGES/textpress.*
echo "All done."
