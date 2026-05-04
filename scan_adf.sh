#!/bin/bash
set -x
# set -e

SCAN_DIRECTORY=${SCAN_DIRECTORY:-/scans}
PROCESSING_LOCKFILE=${SCAN_DIRECTORY}/.scanlock
touch "$PROCESSING_LOCKFILE"

# Acquire lock for scanning and processing
exec 4<"$PROCESSING_LOCKFILE"
flock 4

# Create the directory for the scan
pushd $SCAN_DIRECTORY
mkdir -p "$FILENAME"
pushd "$FILENAME"

SCAN_DEVICE_FLAG=""
if [ -n "$SCANNER_DEVICE" ]; then
    SCAN_DEVICE_FLAG=("-d" "$SCANNER_DEVICE")
fi

case "$SOURCE" in
    Flatbed|Slide|Negative)
        scanimage "${SCAN_DEVICE_FLAG[@]}" --mode "$MODE" --source "$SOURCE" --resolution "$RESOLUTION" \
            --format png -o "image-001.png" 2>>stderr.log 1>>stdout.log || true
        ;;
    *)
        scanadf "${SCAN_DEVICE_FLAG[@]}" --mode "$MODE" --source "$SOURCE" --resolution "$RESOLUTION" \
            2>>stderr.log 1>>stdout.log || true
        ;;
esac

# Convert to pdf and apply OCR
convert image* "$FILENAME.pdf" 2>>stderr.log 1>>stdout.log
ocrmypdf -r -d -c --rotate-pages-threshold 0 "$FILENAME.pdf" "$FILENAME.ocr.pdf" 2>>stderr.log 1>>stdout.log
# Sometimes ocrmypdf still has these files locked after, wait until they're done
until ! lsof "stdout.log" >/dev/null 2>&1; do sleep 1s; done
until ! lsof "stderr.log" >/dev/null 2>&1; do sleep 1s; done

# Replace non-ocr with ocr document and cleanup files and locks
mv "$FILENAME.ocr.pdf" "$FILENAME.pdf" 2>>stderr.log 1>>stdout.log
rm image* 2>>stderr.log 1>>stdout.log

# Ensure permissions allow users to access the scans
chmod -R u+rwX,g+rwX,o+rwX  "$FILENAME"

# Give a break between scan jobs of 15 seconds to allow loading a queued job
sleep 15s

exec 4<&- 
popd # FILENAME

popd # SCAN_DIRECTORY
