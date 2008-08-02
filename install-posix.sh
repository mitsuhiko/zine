#!/bin/bash
# This script copies textpress into PREFIX and compiles the python
# files with PYTHON.  If PREFIX is not defined /usr is assumed.

SRC="`dirname '$0'`/textpress"
PACKAGES="_dynamic _ext importers parsers utils views websetup"

if [ x$PREFIX == x ]; then
  PREFIX=/usr
fi
if [ x$PYTHON == x ]; then
  PYTHON=`which python`
fi

echo "Installing to $PREFIX"
echo "Using $PYTHON"

# make sure the target folders exist
mkdir -p $PREFIX/lib/textpress/textpress
mkdir -p $PREFIX/share/{textpress,locale}

# the packages to copy
cp $SRC/*.py $PREFIX/lib/textpress/textpress
for package in $PACKAGES; do
  mkdir -p $PREFIX/lib/textpress/textpress/$package
  cp -R $SRC/$package $PREFIX/lib/textpress/textpress/
done

# the i18n package is special.  it becomes a module!
cp $SRC/i18n/__init__.py $PREFIX/lib/textpress/textpress/i18n.py

# all the plugins
cp -R $SRC/{experimental_,}plugins $PREFIX/lib/textpress

# compile all files
$PYTHON -O -mcompileall -qf $PREFIX/lib/textpress/{textpress,plugins}

# translations
for folder in $SRC/i18n/*; do
  if [ -d "$folder/LC_MESSAGES" ]; then
    target="$PREFIX/share/locale/`basename $folder`/LC_MESSAGES"
    mkdir -p $target
    cp $folder/LC_MESSAGES/messages.mo $target/textpress.mo
    cp $folder/LC_MESSAGES/messages.js $target/textpress.js
  fi
done

# templates and shared data
cp -R $SRC/shared $PREFIX/share/textpress/htdocs
cp -R $SRC/templates $PREFIX/share/textpress/templates

echo "All done."
