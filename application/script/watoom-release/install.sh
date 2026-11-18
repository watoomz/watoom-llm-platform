#!/bin/sh
# Install only into an explicitly selected prefix; production service cutover is separate.
prefix=
profiles=minimal
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) prefix=$2; shift 2 ;;
    --profiles) profiles=$2; shift 2 ;;
    *) printf '%s\n' 'Usage: install.sh --prefix /absolute/path [--profiles minimal,developer]'; exit 2 ;;
  esac
done
case "$prefix" in /*) ;; *) printf '%s\n' 'An absolute --prefix is required'; exit 2 ;; esac
[ "$prefix" != / ] || exit 2
package=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
(cd "$package" && sha256sum -c SHA256SUMS) || exit 1
release=$(cat "$package/RELEASE_ID") || exit 1
case "$release" in *[!a-zA-Z0-9._-]*|'') exit 2 ;; esac
target=$prefix/releases/$release
mkdir -p "$target" "$prefix/bin" || exit 1
if [ -f "$target/watoom-code" ]; then
  cmp "$package/bin/opencode" "$target/watoom-code" || exit 1
else
  cp "$package/bin/opencode" "$target/watoom-code" || exit 1
  chmod 755 "$target/watoom-code" || exit 1
fi
if [ -e "$prefix/bin/watoom-code" ] && [ ! -L "$prefix/bin/watoom-code" ]; then
  printf '%s\n' 'Refusing to replace an existing regular executable'; exit 1
fi
# Complete configuration before publishing the executable link.
"$target/watoom-code" profiles install --scope user --select "$profiles" > "$target/profile-install.json" || exit 1
if [ -L "$prefix/bin/watoom-code" ]; then
  readlink "$prefix/bin/watoom-code" > "$target/previous-executable.txt" || exit 1
fi
ln -s "$target/watoom-code" "$prefix/bin/watoom-code.pending.$$" || exit 1
mv -Tf "$prefix/bin/watoom-code.pending.$$" "$prefix/bin/watoom-code" || exit 1
printf 'Installed %s\nProfile transaction: %s\n' "$prefix/bin/watoom-code" "$target/profile-install.json"
